"""Bounded public archive acquisition. MPC identifiers/orbits are not image URLs."""

from __future__ import annotations

import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.table import Table

from .infrared_bands import DETECTOR_BANDS, balanced_candidates, detectors_for
from .infrared_mask import MaskConfig, sha256, write_json

IRSA = "https://irsa.ipac.caltech.edu/"
CALIBRATION_DOC = IRSA + "data/SPHEREx/docs/spherex_spectral_calibrations.html"
MOST = IRSA + "cgi-bin/MOST/nph-most"
S3 = "https://nasa-irsa-spherex.s3.us-east-1.amazonaws.com/"


def _context():
    if sys.platform == "win32":
        try:
            import truststore

            return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        except ImportError:
            pass
    return ssl.create_default_context()


def _open(request):
    for attempt in range(3):
        try:
            return urllib.request.urlopen(request, timeout=50, context=_context())
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == 2:
                raise
        time.sleep(attempt + 1)


def download(url, path, max_bytes=64 * 1024 * 1024):
    """IRSA HTTPS only; atomic cache, bounded bytes, TLS verification always enabled."""
    parsed = urllib.parse.urlsplit(url)
    hosts = {"irsa.ipac.caltech.edu", "nasa-irsa-spherex.s3.us-east-1.amazonaws.com"}
    if parsed.scheme != "https" or parsed.hostname not in hosts or parsed.port:
        raise ValueError(
            "Somente URLs HTTPS do arquivo público IRSA e seu bucket oficial são permitidas."
        )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = path.with_suffix(path.suffix + ".source.json")
    if path.exists() and meta.exists():
        info = json.loads(meta.read_text(encoding="utf-8"))
        if info.get("url") == url and info.get("sha256") == sha256(path):
            return path
    temporary = path.with_suffix(path.suffix + ".part")
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Zephyr-IR-mask/0.1"})
        with _open(request) as response:
            if urllib.parse.urlsplit(response.url).hostname not in hosts:
                raise ValueError("Redirecionamento para host não autorizado.")
            size = 0
            with temporary.open("wb") as stream:
                while chunk := response.read(256 * 1024):
                    size += len(chunk)
                    if size > max_bytes:
                        raise ValueError("Arquivo excede o limite configurado.")
                    stream.write(chunk)
        temporary.replace(path)
        write_json(meta, {"url": url, "sha256": sha256(path), "bytes": size})
        return path
    finally:
        temporary.unlink(missing_ok=True)


def validate_request(params):
    allowed = {
        "object",
        "start",
        "end",
        "low_um",
        "high_um",
        "max_exposures",
        "detector",
        "channel_id",
        "sample_id",
        "include_context",
    }
    if set(params) - allowed:
        raise ValueError("Parâmetro de consulta desconhecido.")
    name = str(params.get("object", "1766")).strip()
    if not name or len(name) > 80 or any(ord(ch) < 32 for ch in name):
        raise ValueError("Identificação MPC inválida.")
    start = date.fromisoformat(str(params.get("start", "2026-07-20")))
    end = date.fromisoformat(str(params.get("end", "2026-07-25")))
    if not 0 < (end - start).days <= 7:
        raise ValueError("O piloto aceita intervalos maiores que zero e de até sete dias.")
    count = float(params.get("max_exposures", 12))
    if not count.is_integer():
        raise ValueError("Número de exposições deve ser inteiro.")
    detector = float(params.get("detector", 0))
    if not detector.is_integer():
        raise ValueError("Detector deve ser inteiro.")
    channel_id = float(params.get("channel_id", 0))
    if not channel_id.is_integer() or not 0 <= channel_id <= 102:
        raise ValueError("Selecione um canal SPHEREx de 1 a 102, ou todos (0).")
    if not isinstance(params.get("include_context", True), bool):
        raise ValueError("include_context deve ser booleano.")
    sample_id = params.get("sample_id", "")
    if not isinstance(sample_id, str) or len(sample_id) > 160:
        raise ValueError("Amostra inválida.")
    low, high = float(params.get("low_um", 0.75)), float(params.get("high_um", 5))
    if channel_id:
        from .infrared_catalogs import channel_grid

        channel = channel_grid()["channels"][int(channel_id) - 1]
        low, high, detector = (
            max(0.75, channel["low_um"]),
            min(5.0, channel["high_um"]),
            channel["detector"],
        )
    cfg = MaskConfig(
        low_um=low,
        high_um=high,
        max_exposures=int(count),
        detector=int(detector),
    )
    return name, start, end, cfg


def coordinate_candidates(sample, start, end, cfg, cache):
    """Find real image footprints at a selected sample; positions remain fixed sky."""
    from astropy.time import Time

    rows, queries = [], []
    for collection in ("spherex_dr1", "spherex_qr3"):
        url = (
            IRSA
            + "SIA?"
            + urllib.parse.urlencode(
                {
                    "POS": f"CIRCLE {sample['ra']:.8f} {sample['dec']:.8f} 0.001",
                    "COLLECTION": collection,
                    "TIME": f"{Time(start.isoformat()).mjd} {Time(end.isoformat()).mjd}",
                    "BAND": f"{cfg.low_um * 1e-6} {cfg.high_um * 1e-6}",
                    "MAXREC": "145",
                }
            )
        )
        path = download(url, cache / f"{collection}.xml", 8 * 1024 * 1024)
        table = Table.read(path, format="votable", use_names_over_ids=True)
        queries.append(
            {"url": url, "sha256": sha256(path), "possibly_truncated": len(table) >= 145}
        )
        for row in table:
            match = re.fullmatch(r"SPHEREx-D([1-6])", str(row["energy_bandpassname"]))
            if not match:
                continue
            mid = (float(row["t_min"]) + float(row["t_max"])) / 2
            rows.append(
                {
                    "observationid": str(row["obs_id"]),
                    "productid": "D" + match[1],
                    "ra_obj": sample["ra"],
                    "dec_obj": sample["dec"],
                    "uri": str(row["access_url"]),
                    "mjd_start": mid,
                    "mjd_end": mid,
                    "geo_dist": None,
                    "match": 1,
                }
            )
    return rows, queries


def _preview_at_target(path, ra, dec):
    """Approximate WCS-WAVE is only an acquisition filter, never measured science."""
    from astropy.wcs import WCS

    with fits.open(path, memmap=False) as h:
        spatial = WCS(h["IMAGE"].header).celestial
        x, y = spatial.all_world2pix(ra, dec, 0)
        spectral_header = h["IMAGE"].header.copy()
        for key in list(spectral_header):
            if key.startswith(("A_", "B_", "AP_", "BP_")):
                del spectral_header[key]
        spectral = WCS(spectral_header, h, key="W")
        spectral.sip = None
        values = spectral.all_pix2world(float(x), float(y), 0)
        # astropy may normalize spectral WCS units to metres.
        import astropy.units as u

        return float(values[0]) * u.Unit(spectral.wcs.cunit[0]).to(u.um)


def fetch_calibration(output, release="qr3", detector=4):
    """Discover the actual version name; docs examples can lag archive filenames."""
    if release not in ("dr1", "qr3"):
        raise ValueError("Coleção de calibração inválida.")
    if detector not in DETECTOR_BANDS:
        raise ValueError("Selecione uma calibração D1–D6.")
    output = Path(output)
    url = (
        S3
        + "?"
        + urllib.parse.urlencode(
            {"list-type": 2, "prefix": f"{release}/spectral_wcs/", "max-keys": 100}
        )
    )
    listing = download(url, output.with_suffix(".listing.xml"), 1024 * 1024)
    tree = ET.parse(listing)
    namespace = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
    if tree.findtext("s3:IsTruncated", namespaces=namespace) != "false":
        raise ValueError("Lista de calibrações incompleta; selecione manualmente uma versão.")
    keys = [el.text for el in tree.findall("s3:Contents/s3:Key", namespace)]
    keys = [
        key
        for key in keys
        if f"/{detector}/spectral_wcs_D{detector}_" in key and key.endswith(".fits")
    ]
    if len(keys) != 1:
        raise ValueError(
            f"Arquivo contém múltiplas versões D{detector} ou nenhuma; "
            "selecione uma calibração explicitamente."
        )
    calibration_url = IRSA + "ibe/data/spherex/" + keys[0]
    result = download(calibration_url, output, 40 * 1024 * 1024)
    with fits.open(result) as h:
        if (
            h["CWAVE"].data.shape != (2040, 2040)
            or "CBAND" not in h
            or int(h["CWAVE"].header.get("DETECTOR", h[0].header.get("DETECTOR", -1))) != detector
        ):
            raise ValueError("Produto de calibração espectral inesperado.")
    return result


def resolve_calibration(location, detector):
    location = Path(location).resolve()
    path = location if location.is_file() else location / f"calibration_D{detector}.fits"
    if not path.is_file():
        raise ValueError(f"Calibração D{detector} ausente: execute calibration --detector all.")
    with fits.open(path, memmap=True) as h:
        declared = h["CWAVE"].header.get("DETECTOR", h[0].header.get("DETECTOR"))
        valid = "CBAND" in h and h["CWAVE"].shape == h["CBAND"].shape
    if declared is None or int(declared) != detector or not valid:
        raise ValueError(f"Calibração D{detector} incompatível: confira detector e CWAVE/CBAND.")
    return path


def available_calibrations(location):
    available = []
    if not location:
        return available
    for detector in DETECTOR_BANDS:
        try:
            resolve_calibration(location, detector)
            available.append(detector)
        except (ValueError, OSError, KeyError):
            pass
    return available


def fetch_calibrations(directory, release="qr3", progress=lambda s: None):
    from concurrent.futures import ThreadPoolExecutor

    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)

    def fetch(detector):
        progress(f"Baixando calibração oficial D{detector}")
        return detector, fetch_calibration(
            directory / f"calibration_D{detector}.fits", release, detector
        )

    with ThreadPoolExecutor(max_workers=3) as pool:
        return dict(pool.map(fetch, DETECTOR_BANDS))


def fetch_gaia(ra, dec, cache):
    # Bound the cone and result size. Gaia is a contamination catalogue, not IR flux.
    query = (
        "SELECT TOP 3000 source_id,ra,dec,ref_epoch,pmra,pmdec,phot_g_mean_mag "
        "FROM gaia_dr3_source WHERE 1=CONTAINS(POINT('ICRS',ra,dec),"
        f"CIRCLE('ICRS',{ra:.8f},{dec:.8f},0.1)) AND phot_g_mean_mag<19"
    )
    url = (
        IRSA
        + "TAP/sync?"
        + urllib.parse.urlencode(
            {"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv", "QUERY": query}
        )
    )
    gator_url = (
        IRSA
        + "cgi-bin/Gator/nph-query?"
        + urllib.parse.urlencode(
            {
                "catalog": "gaia_dr3_source",
                "spatial": "Cone",
                "objstr": f"{ra:.8f} {dec:.8f}",
                "radius": "0.1",
                "radunits": "deg",
                "outfmt": "1",
                "outrows": "3000",
                "constraints": "phot_g_mean_mag < 19",
                "selcols": "source_id,ra,dec,ref_epoch,pmra,pmdec,phot_g_mean_mag",
            }
        )
    )
    attempts = []
    for endpoint, name, fmt in (
        (gator_url, "gaia.tbl", "ascii.ipac"),
        (url, "gaia.csv", "ascii.csv"),
    ):
        try:
            path = download(endpoint, cache / name, 5 * 1024 * 1024)
            table = Table.read(path, format=fmt)
            rows = []
            for row in table:
                item = {}
                for key in (
                    "source_id",
                    "ra",
                    "dec",
                    "ref_epoch",
                    "pmra",
                    "pmdec",
                    "phot_g_mean_mag",
                ):
                    val = row[key]
                    item[key] = (
                        None
                        if np.ma.is_masked(val)
                        else str(val)
                        if key == "source_id"
                        else float(val)
                        if np.isfinite(float(val))
                        else None
                    )
                rows.append(item)
            return rows, {
                "status": "loaded",
                "count": len(rows),
                "url": endpoint,
                "sha256": sha256(path),
                "complete": len(rows) < 3000,
                "failed_attempts": attempts,
            }
        except Exception as exc:
            attempts.append({"url": endpoint, "reason": str(exc)})
    return [], {"status": "unavailable", "attempts": attempts}


def prepare_archive(
    params,
    cache_dir,
    calibration,
    calibration_coordinates,
    progress=lambda s: None,
    mpc_orbit_line=None,
    coordinate_sample=None,
):
    name, start, end, cfg = validate_request(params)
    requested_detectors = detectors_for(cfg.low_um, cfg.high_um, cfg.detector)
    calibrations = {d: resolve_calibration(calibration, d) for d in requested_detectors}
    cache = Path(cache_dir).resolve()
    cache.mkdir(parents=True, exist_ok=True)
    from .infrared_catalogs import fetch_wise_context, resolve_mpc

    progress("Validando identificação na API do Minor Planet Center")
    identity = resolve_mpc(name, cache.parent / "mpc")
    if identity["status"] != "resolved":
        raise ValueError(
            "MPC: objeto não encontrado ou ambíguo; use Buscar no MPC e selecione um resultado."
        )
    name = identity["items"][0]["identifier"]
    query = {
        "catalog": "spherex",
        "input_type": "name_input",
        "obj_name": name,
        "obs_begin": start.strftime("%Y %m %d"),
        "obs_end": end.strftime("%Y %m %d"),
        "output_mode": "Brief",
        "ephem_step": "0.01",
    }
    if mpc_orbit_line:
        query.pop("obj_name")
        query.update(input_type="mpc_input", obj_type="Asteroid", mpc_data=mpc_orbit_line)
    url = MOST + "?" + urllib.parse.urlencode(query)
    progress("Consultando posições e exposições no MOST/IRSA")
    if coordinate_sample:
        table, image_queries = coordinate_candidates(coordinate_sample, start, end, cfg, cache)
        table_path = None
    else:
        table_path = download(url, cache / "most.tbl", 10 * 1024 * 1024)
        image_queries = []
        try:
            table = Table.read(table_path, format="ascii.ipac")
        except Exception as exc:
            raise ValueError(
                "MOST não retornou tabela de exposições. Verifique objeto e datas."
            ) from exc
    candidates = balanced_candidates(
        [r for r in table if int(r["match"]) == 1], requested_detectors
    )
    selected, rejected, seen = [], [], set()
    for row in candidates[:144]:
        obs = str(row["observationid"])
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", obs):
            raise ValueError("Identificador de observação inválido no arquivo.")
        detector = int(str(row["productid"])[1:])
        key = (obs, detector)
        if key in seen:
            continue
        seen.add(key)
        progress(f"Inspecionando recorte D{detector} {obs}")
        ra, dec = float(row["ra_obj"]), float(row["dec_obj"])
        image_url = (
            urllib.parse.urljoin(IRSA, str(row["uri"]))
            + "?"
            + urllib.parse.urlencode({"center": f"{ra},{dec}", "size": "0.12"})
        )
        try:
            image_path = download(image_url, cache / f"{obs}_D{detector}.fits", 12 * 1024 * 1024)
        except (OSError, TimeoutError) as exc:
            rejected.append(
                {
                    "observation": obs,
                    "detector": detector,
                    "reason": "download_failed",
                    "error": str(exc),
                }
            )
            continue
        preview = _preview_at_target(image_path, ra, dec)
        if not cfg.low_um - 0.03 <= preview <= cfg.high_um + 0.03:
            rejected.append(
                {
                    "observation": obs,
                    "detector": detector,
                    "reason": "preview_outside_band",
                    "approx_um": preview,
                }
            )
            continue
        # Validate with the full calibration, not the preview.
        from astropy.wcs import WCS

        from .infrared_mask import spectral_maps

        with fits.open(image_path, memmap=False) as hdul:
            header = hdul["IMAGE"].header
            if int(header.get("DETECTOR", -1)) != detector:
                raise ValueError("Detector do FITS difere do produto retornado pelo MOST.")
            wave, _ = spectral_maps(
                hdul,
                header,
                hdul["IMAGE"].data.shape,
                calibrations[detector],
                calibration_coordinates,
            )
            x, y = WCS(header).celestial.all_world2pix(ra, dec, 0)
            ix, iy = int(round(float(x))), int(round(float(y)))
            actual = (
                float(wave[iy, ix])
                if 0 <= iy < wave.shape[0] and 0 <= ix < wave.shape[1]
                else np.nan
            )
            mid = float(
                header.get("MJD-AVG", (float(row["mjd_start"]) + float(row["mjd_end"])) / 2)
            )
        if not np.isfinite(actual) or not cfg.low_um <= actual < cfg.high_um:
            rejected.append(
                {
                    "observation": obs,
                    "detector": detector,
                    "reason": "calibrated_target_outside_band",
                    "lambda_um": actual if np.isfinite(actual) else None,
                }
            )
            continue
        if params.get("channel_id"):
            from .infrared_catalogs import channel_for

            matched_channel = channel_for(actual, detector)
            if not matched_channel or matched_channel["id"] != int(params["channel_id"]):
                rejected.append(
                    {
                        "observation": obs,
                        "detector": detector,
                        "reason": "calibrated_target_outside_selected_channel",
                    }
                )
                continue
        selected.append(
            {
                "fits": image_path.name,
                "calibration": str(calibrations[detector]),
                "calibration_coordinates": calibration_coordinates,
                "source_url": image_url,
                "target": {
                    "ra": ra,
                    "dec": dec,
                    "mjd": mid
                    if coordinate_sample
                    else (float(row["mjd_start"]) + float(row["mjd_end"])) / 2,
                    "provider": "Selected sample / fixed ICRS coordinate"
                    if coordinate_sample
                    else "IRSA MOST / MPC orbit input"
                    if mpc_orbit_line
                    else "IRSA MOST / name resolver",
                    "frame": "ICRS",
                    "position_status": "fixed_sky_not_moving_ephemeris"
                    if coordinate_sample
                    else "observer_not_verified",
                    "geo_dist_au": None if coordinate_sample else float(row["geo_dist"]),
                    "time_offset_s": 86400
                    * ((float(row["mjd_start"]) + float(row["mjd_end"])) / 2 - mid),
                },
            }
        )
        if len(selected) == cfg.max_exposures:
            break
    if not selected:
        write_json(cache / "selection.json", {"rejected": rejected, "candidates": len(candidates)})
        raise ValueError(
            "Nenhuma exposição coloca o alvo na faixa calibrada. "
            "Altere datas/alvo; não foi substituída por outra banda."
        )
    progress("Consultando Gaia DR3 para sinalizar contaminação")
    import astropy.units as u
    from astropy.coordinates import SkyCoord

    gaia_by_id, cones, cone_status = {}, [], []
    for i, entry in enumerate(selected):
        target = entry["target"]
        coord = SkyCoord(target["ra"] * u.deg, target["dec"] * u.deg)
        if any(coord.separation(center).deg < 0.005 for center in cones):
            continue
        cones.append(coord)
        stars, status = fetch_gaia(target["ra"], target["dec"], cache / f"gaia_{i}")
        cone_status.append(status)
        for star in stars:
            gaia_by_id[star["source_id"]] = star
    gaia = list(gaia_by_id.values())
    gaia_status = {
        "status": "loaded"
        if all(s["status"] == "loaded" and s.get("complete") for s in cone_status)
        else "incomplete",
        "count": len(gaia),
        "cones": cone_status,
    }
    context = {}
    if params.get("include_context", True):
        progress("Concatenando contexto AllWISE / NEOWISE nas coordenadas SPHEREx")
        from concurrent.futures import ThreadPoolExecutor

        def fetch_context(item):
            i, center = item
            return fetch_wise_context(center.ra.deg, center.dec.deg, cache / f"wise_{i}")

        with ThreadPoolExecutor(max_workers=3) as pool:
            for fetched in pool.map(fetch_context, enumerate(cones)):
                for key, value in fetched.items():
                    group = context.setdefault(key, {"status": "loaded", "rows": [], "queries": []})
                    group["queries"].append({k: v for k, v in value.items() if k != "rows"})
                    if value["status"] != "loaded":
                        group["status"] = "incomplete"
                    group["rows"].extend(value["rows"])
        for group in context.values():
            group["rows"] = list(
                {
                    r.get("source_id")
                    or r.get("designation")
                    or r.get("base_url")
                    or json.dumps(r, sort_keys=True): r
                    for r in group["rows"]
                }.values()
            )
    manifest = {
        "object": name,
        "synthetic": False,
        "config": {
            "low_um": cfg.low_um,
            "high_um": cfg.high_um,
            "max_exposures": cfg.max_exposures,
            "detector": cfg.detector,
        },
        "gaia": gaia,
        "gaia_status": gaia_status,
        "context_catalogues": context,
        "request_selection": {
            "channel_id": int(params.get("channel_id", 0)),
            "sample": coordinate_sample,
        },
        "exposures": selected,
        "provenance": {
            "images": "SPHEREx IRSA",
            "mpc_identity": identity,
            "most_url": url if table_path else None,
            "most_sha256": sha256(table_path) if table_path else None,
            "image_queries": image_queries,
            "calibrations": {
                str(d): {"path": str(p), "sha256": sha256(p)} for d, p in calibrations.items()
            },
            "selection_method": "Round-robin D1–D6; temporal endpoints then widest gaps",
            "mpc_orbit_supplied": bool(mpc_orbit_line),
            "coordinate_reference": "SPHEREx IMAGE spatial WCS (ICRS/TAN-SIP)",
            "selection": {
                "candidates": len(candidates),
                "inspected": len(seen),
                "rejected": rejected,
            },
            "references": [
                CALIBRATION_DOC,
                "https://irsa.ipac.caltech.edu/applications/MOST/MOSTProgramInterface.html",
            ],
        },
    }
    path = cache / "manifest.json"
    write_json(path, manifest)
    return path
