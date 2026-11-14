"""Descoberta CMR e extração Harmony documentadas pelos provedores NASA."""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit

import netCDF4
import numpy as np

from .core import LOG, IngestionError, fingerprint, public_url, timestamps

CMR = "https://cmr.earthdata.nasa.gov/search"
HARMONY = "https://harmony.earthdata.nasa.gov"


def query_granules(http, params):
    with http.get(f"{CMR}/granules.json", params=params) as response:
        try:
            body = response.json()
            count = int(response.headers["CMR-Hits"])
            return body["feed"]["entry"], count
        except (ValueError, KeyError) as exc:
            raise IngestionError("Resposta CMR sem contagem ou lista de grânulos") from exc


def collection(http, dataset):
    body = http.json(
        f"{CMR}/collections.umm_json",
        params={
            "short_name": dataset["product"],
            "version": dataset["version"],
            "page_size": 100,
        },
    )
    items = [
        item
        for item in body["items"]
        if item["umm"]["ShortName"] == dataset["product"]
        and item["umm"]["Version"] == dataset["version"]
    ]
    if len(items) != 1:
        raise IngestionError("Coleção/versão ausente ou ambígua no CMR")
    item = items[0]
    cid = item["meta"]["concept-id"]
    caps = http.json(f"{HARMONY}/capabilities", params={"collectionId": cid})
    available = {v["name"] for v in caps.get("variables", [])}
    missing = set(dataset["variables"]) - available
    if missing:
        raise IngestionError(f"Variáveis não publicadas no Harmony: {sorted(missing)}")
    supported = False
    for service in caps.get("services", []):
        capabilities = service.get("capabilities", {})
        subset = capabilities.get("subsetting", {})
        formats = {f["mimeType"] for f in capabilities.get("outputFormats", [])}
        if all(subset.get(key) for key in ("bbox", "temporal", "variable")):
            supported |= "application/netcdf" in formats
    if not supported:
        raise IngestionError("Nenhum serviço anuncia recorte bbox/tempo/variáveis em NetCDF")
    params = {"collection_concept_id": cid, "page_size": 1}
    first, _ = query_granules(http, {**params, "sort_key": "start_date"})
    last, _ = query_granules(http, {**params, "sort_key": "-end_date"})
    if not first or not last:
        raise IngestionError("Coleção sem grânulos catalogados")
    return {
        "collection_id": cid,
        "doi": item["umm"].get("DOI", {}).get("DOI"),
        "available_period": {"start": first[0]["time_start"], "end": last[0]["time_end"]},
        "variables_available": sorted(available),
        "capabilities": caps,
        "collection_metadata": item["umm"],
        **timestamps(),
    }


def iso(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def make_plan(name, dataset, metadata, region, start, end, http):
    begin = max(iso(start), iso(metadata["available_period"]["start"]))
    finish = min(iso(end), iso(metadata["available_period"]["end"]))
    if begin > finish:
        raise IngestionError("Período solicitado não intersecta a disponibilidade da coleção")
    effective = {"start": begin.isoformat(), "end": finish.isoformat()}
    params = {
        "collection_concept_id": metadata["collection_id"],
        "temporal": f"{effective['start']},{effective['end']}",
        "bounding_box": ",".join(map(str, region["bbox"])),
        "page_size": 1,
        "sort_key": "start_date",
    }
    _, count = query_granules(http, params)
    return {
        "dataset": name,
        "product": dataset["product"],
        "version": dataset["version"],
        "collection_id": metadata["collection_id"],
        "doi": metadata["doi"],
        "variables_requested": dataset["variables"],
        "available_period": metadata["available_period"],
        "requested_period": {"start": start, "end": end},
        "effective_query_period": effective,
        "region": region,
        "matching_granules": count,
        "cmr_parameters": params,
        "access_method": "Harmony_provider_bbox_subset_without_aggregation",
        "temporal_selection": "CMR granule overlap; preserves full native time records",
        "authentication_required": True,
    }


def inspect_netcdf(path, variables, region):
    """Lê todos os blocos selecionados para detectar corrupção e contar ausências."""
    try:
        with netCDF4.Dataset(path) as root:
            root.set_auto_maskandscale(False)
            groups = [("", root)]
            for prefix, group in groups:
                groups.extend((f"{prefix}{key}/", child) for key, child in group.groups.items())
            fields = {
                f"{prefix}{name}": value
                for prefix, group in groups
                for name, value in group.variables.items()
            }
            info, total_missing, primary_valid = {}, 0, 0
            for requested in variables:
                matches = [key for key in fields if key == requested]
                if not matches:
                    # HOSS pode promover uma variável agrupada ao grupo raiz.
                    matches = [
                        key for key in fields if key.split("/")[-1] == requested.split("/")[-1]
                    ]
                if len(matches) != 1:
                    raise IngestionError(f"Variável solicitada ausente/ambígua: {requested}")
                name = matches[0]
                var = fields[name]
                missing, size = 0, 0
                # Recortes limitados espacialmente; até 1 fatia no primeiro eixo por leitura.
                indices = range(var.shape[0]) if var.ndim else [None]
                for index in indices:
                    values = np.asarray(var[index] if index is not None else var[...])
                    mask = np.zeros(values.shape, dtype=bool)
                    if np.issubdtype(values.dtype, np.floating):
                        mask |= ~np.isfinite(values)
                    for attr in ("_FillValue", "missing_value"):
                        for sentinel in np.asarray(getattr(var, attr, [])).reshape(-1):
                            mask |= values == sentinel
                    missing += int(mask.sum())
                    size += values.size
                primary_valid += size - missing
                total_missing += missing
                info[name] = {
                    "requested_name": requested,
                    "units": getattr(var, "units", None),
                    "dimensions": list(var.dimensions),
                    "shape": list(var.shape),
                    "dtype": str(var.dtype),
                    "missing_values": missing,
                    "attributes": {k: str(var.getncattr(k)) for k in var.ncattrs()},
                }
            coordinates, observation, temporal_records = {}, None, None
            for name, var in fields.items():
                short = name.split("/")[-1].lower()
                if short in ("lat", "latitude", "lon", "longitude"):
                    values = np.asarray(var[:], dtype=float).reshape(-1)
                    if values.size == 0 or not np.isfinite(values).all():
                        raise IngestionError("Coordenada espacial vazia ou inválida")
                    coordinates[name] = {
                        "min": float(values.min()),
                        "max": float(values.max()),
                        "count": int(values.size),
                        "units": getattr(var, "units", None),
                        "step": float(np.median(np.abs(np.diff(values))))
                        if values.size > 1
                        else None,
                    }
                    west, south, east, north = region["bbox"]
                    # Um centro de célula pode ficar até meio espaçamento além do recorte.
                    step = coordinates[name]["step"] or 0
                    low, high = (south, north) if short in ("lat", "latitude") else (west, east)
                    compare = values if short in ("lat", "latitude") else (values + 180) % 360 - 180
                    if (
                        compare.min() < low - step / 2 - 1e-6
                        or compare.max() > high + step / 2 + 1e-6
                    ):
                        raise IngestionError("Arquivo retornado excede o recorte espacial pedido")
                elif short == "time":
                    values = var[:]
                    dates = netCDF4.num2date(
                        values, var.units, calendar=getattr(var, "calendar", "standard")
                    )
                    dates = np.asarray(dates).reshape(-1)
                    temporal_records = len(dates)
                    if temporal_records:
                        observation = {"start": str(min(dates)), "end": str(max(dates))}
            spatial_axes = {name.split("/")[-1].lower() for name in coordinates}
            if not (
                {"lat", "latitude"} & spatial_axes
                and {"lon", "longitude"} & spatial_axes
                and temporal_records
                and primary_valid
            ):
                raise IngestionError(
                    "Recorte sem coordenadas, tempos ou valores científicos válidos"
                )
            return {
                "integrity": "all_requested_variable_blocks_read",
                "variables": info,
                "missing_values": total_missing,
                "dimensions": {
                    f"{prefix}{name}": len(dim)
                    for prefix, group in groups
                    for name, dim in group.dimensions.items()
                },
                "coordinates": coordinates,
                "temporal_records": temporal_records,
                "observation_period": observation,
                "quality": "attributes retained; no quality masking applied",
            }
    except (OSError, RuntimeError, ValueError, AttributeError, IndexError) as exc:
        raise IngestionError("NetCDF ilegível, corrompido ou sem metadados obrigatórios") from exc


def granules(http, plan):
    params = {**plan["cmr_parameters"], "page_size": 1000}
    count, page = 0, 1
    while True:
        items, total = query_granules(http, {**params, "page_num": page})
        if total != plan["matching_granules"]:
            raise IngestionError("Catálogo mudou durante a coleta; gere um novo plano")
        yield from items
        count += len(items)
        if count >= total:
            break
        if not items:
            raise IngestionError("Paginação CMR incompleta")
        page += 1


def harmony_parameters(plan, granule):
    west, south, east, north = plan["region"]["bbox"]
    return [
        ("subset", f"lat({south}:{north})"),
        ("subset", f"lon({west}:{east})"),
        ("granuleId", granule["id"]),
        ("format", "application/netcdf"),
        ("forceAsync", "true"),
        ("ignoreErrors", "false"),
        ("skipPreview", "true"),
        ("maxResults", "1"),
    ]


def fetch_nasa(
    dataset, plan, http, store, token, *, max_granules=50, wait_seconds=120, refresh=False
):
    if plan["matching_granules"] == 0:
        raise IngestionError("Nenhum grânulo intersecta período/região")
    if max_granules and plan["matching_granules"] > max_granules:
        raise IngestionError(
            f"{plan['matching_granules']} grânulos excedem --max-granules={max_granules}; "
            "restrinja o período ou aumente explicitamente o limite"
        )
    if not token:
        raise IngestionError("EARTHDATA_TOKEN ausente: configure localmente no .env")
    headers = {"Authorization": f"Bearer {token}"}
    entries = []
    for granule in granules(http, plan):
        key = fingerprint(
            {
                "collection_id": plan["collection_id"],
                "granule_id": granule["id"],
                "variables": plan["variables_requested"],
                "region": plan["region"],
                "effective_query_period": plan["effective_query_period"],
            }
        )
        if not refresh and (cached := store.cached(key)):
            entries.append(cached)
            continue
        params = harmony_parameters(plan, granule)
        variable_path = quote(",".join(plan["variables_requested"]), safe=",")
        endpoint = (
            f"{HARMONY}/{plan['collection_id']}/ogc-api-coverages/1.0.0/"
            f"collections/{variable_path}/coverage/rangeset"
        )
        job = store.data["jobs"].get(key)
        if not job or refresh:
            # Submissão não é repetida automaticamente após timeout: pode ter criado job.
            response = http.json(endpoint, params=params, headers=headers, attempts=1)
            job_id = response.get("jobID")
            if not job_id or not re.fullmatch(r"[a-fA-F0-9-]+", job_id):
                raise IngestionError("Harmony não retornou jobID válido")
            job = {"id": job_id, "status": response.get("status"), **timestamps()}
            store.data["jobs"][key] = job
            store.save()
        job_endpoint = f"{HARMONY}/jobs/{job['id']}"
        deadline = time.monotonic() + wait_seconds
        while True:
            response = http.json(job_endpoint, headers=headers)
            status = response.get("status")
            job["status"] = status
            store.save()
            LOG.info("Harmony job=%s status=%s", job["id"], status)
            if status == "successful":
                break
            if status in ("failed", "canceled", "successful_with_errors", "paused"):
                raise IngestionError(f"Harmony job={job['id']} status={status}; revise o job")
            if time.monotonic() >= deadline:
                raise IngestionError(f"Job pendente {job['id']}; reexecute para retomar o polling")
            time.sleep(min(5, max(0, deadline - time.monotonic())))
        links = [x for x in response.get("links", []) if x.get("rel") == "data"]
        if len(links) != 1:
            raise IngestionError(
                "Esperado um resultado por grânulo; revise links ou expiração do job"
            )
        for index, link in enumerate(links):
            url = link["href"]
            path = store.root / (
                f"raw/{plan['dataset']}/{dataset['product']}/{plan['region']['id']}/"
                f"{granule['id']}-{index}.nc4"
            )
            output, audit = http.download(
                url,
                path,
                lambda path: inspect_netcdf(path, plan["variables_requested"], plan["region"]),
            )
            source_urls = [
                public_url(x["href"])
                for x in granule.get("links", [])
                if not x.get("inherited")
                and x.get("rel", "").endswith("data#")
                and urlsplit(x["href"]).scheme == "https"
            ]
            metadata = {
                **{k: v for k, v in plan.items() if k != "cmr_parameters"},
                "organization": dataset["organization"],
                "spatial_resolution": dataset["spatial_resolution"],
                "temporal_resolution": dataset["temporal_resolution"],
                "source_url": source_urls,
                "endpoint": endpoint,
                "result_url_without_query": public_url(url),
                "harmony_job_id": job["id"],
                "request_parameters": params,
                "granule_id": granule["id"],
                "granule_observation_period": {
                    "start": granule["time_start"],
                    "end": granule["time_end"],
                },
                "transformations": [
                    "CMR temporal granule selection; provider bbox/variable subset"
                ],
                "quality": "model/reanalysis/analysis as specified by original product",
            }
            entries.append(store.record(key, output, audit, metadata))
    return entries
