"""Planejamento público e execução explícita da coleta do MVP."""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv
from shapely.geometry import shape

from .core import HTTP, IngestionError, Store, atomic_json, fingerprint, sha256, timestamps
from .nasa import collection, fetch_nasa, iso, make_plan
from .noaa import fetch_noaa

ROOT = Path(__file__).resolve().parents[1]
LOG = logging.getLogger("ingestion")


def read_config(path, key):
    with Path(path).open() as stream:
        body = yaml.safe_load(stream)
    if not isinstance(body, dict) or not isinstance(body.get(key), dict):
        raise IngestionError(f"Configuração inválida: {key}")
    return body[key]


def region_config(name, regions, config_path):
    if name not in regions or not re.fullmatch(r"[a-zA-Z0-9_-]+", name):
        raise IngestionError("Identificador de região desconhecido ou inválido")
    region = {**regions[name], "id": name}
    if region.get("crs") != "EPSG:4326":
        raise IngestionError("A região deve declarar EPSG:4326; não há reprojeção implícita")
    if "geometry_file" in region:
        path = Path(config_path).resolve().parent / region["geometry_file"]
        document = json.loads(path.read_text())
        if "crs" in document:
            raise IngestionError("Use GeoJSON RFC 7946 em WGS84, sem declaração CRS legada")
        geometry = document["geometry"] if document.get("type") == "Feature" else document
        polygon = shape(geometry)
        if polygon.geom_type not in ("Polygon", "MultiPolygon"):
            raise IngestionError("GeoJSON deve conter Polygon ou MultiPolygon")
        if not polygon.is_valid or polygon.is_empty:
            raise IngestionError("Polígono vazio ou inválido")
        region.update(
            {
                "bbox": list(polygon.bounds),
                "geometry": geometry,
                "geometry_sha256": sha256(path),
                "extraction": "polygon_envelope_only",
            }
        )
        region.pop("geometry_file")
    box = region.get("bbox", [])
    if len(box) != 4 or not all(isinstance(v, (int, float)) for v in box):
        raise IngestionError("Bounding box deve ter quatro números: oeste,sul,leste,norte")
    west, south, east, north = box
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise IngestionError("Bounding box inválida; antimeridiano requer regiões separadas")
    region.setdefault("extraction", "bounding_box")
    region["geometry_id"] = fingerprint(region.get("geometry", box))
    return region


def inventory(store):
    """Auditoria descritiva dos arquivos existentes, sem interpretar o clima."""
    report = {"generated_at": timestamps(), "datasets": {}, "runs": store.data["runs"]}
    for entry in store.data["files"]:
        item = report["datasets"].setdefault(
            entry["dataset"],
            {
                "file_count": 0,
                "total_bytes": 0,
                "files": [],
                "integrity_problems": [],
            },
        )
        item["file_count"] += 1
        item["total_bytes"] += entry["size_bytes"]
        path = store.root / entry["path"]
        verified = path.is_file() and sha256(path) == entry["sha256"]
        if not verified:
            item["integrity_problems"].append(entry["path"])
        item["files"].append(
            {
                "path": entry["path"],
                "size_bytes": entry["size_bytes"],
                "sha256": entry["sha256"],
                "sha256_verified": verified,
                **entry["audit"],
            }
        )
    atomic_json(store.root / "metadata/inventory.json", report)
    csv_path = store.root / "metadata/dataset_catalog.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "dataset",
        "product",
        "version",
        "path",
        "size_bytes",
        "sha256",
        "retrieved_at_utc",
        "retrieved_at_local",
    ]
    with csv_path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(store.data["files"])
    return report


def parser():
    p = argparse.ArgumentParser(description="Earth Detectives — coleta rastreável, sem EDA")
    p.add_argument(
        "--datasets",
        nargs="+",
        default=[
            "noaa_roni",
            "gpm_daily",
            "gpm_monthly",
            "gldas",
            "merra2",
        ],
    )
    p.add_argument("--datasets-config", type=Path, default=ROOT / "config/datasets.yaml")
    p.add_argument("--regions-config", type=Path, default=ROOT / "config/regions.yaml")
    p.add_argument("--region", help="Substitui a região padrão de todos os produtos NASA")
    p.add_argument("--start", type=date.fromisoformat, help="Data inclusiva YYYY-MM-DD")
    p.add_argument("--end", type=date.fromisoformat, help="Data inclusiva YYYY-MM-DD")
    p.add_argument("--output", type=Path, default=ROOT / "data")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--refresh", action="store_true", help="Busca nova revisão; preserva snapshots")
    p.add_argument(
        "--max-granules",
        type=int,
        default=50,
        help="Recusa dataset acima deste limite; 0 libera explicitamente",
    )
    p.add_argument(
        "--wait-seconds",
        type=int,
        default=120,
        help="Espera máxima por job; reexecução retoma jobs salvos",
    )
    p.add_argument("--timeout", type=int, default=60)
    p.add_argument("--attempts", type=int, default=3)
    p.add_argument("--inventory-only", action="store_true", help="Confere hashes sem acessar rede")
    return p


def execute(args):
    if args.timeout <= 0 or args.attempts <= 0 or args.wait_seconds < 0 or args.max_granules < 0:
        raise IngestionError("Timeout/tentativas devem ser positivos; limites não negativos")
    if args.start and args.end and args.start > args.end:
        raise IngestionError("A data inicial deve anteceder a final")
    store = Store(args.output)
    if args.inventory_only:
        report = inventory(store)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return int(any(x["integrity_problems"] for x in report["datasets"].values()))
    datasets = read_config(args.datasets_config, "datasets")
    regions = read_config(args.regions_config, "regions")
    names = list(dict.fromkeys(args.datasets))
    unknown = set(names) - set(datasets)
    if unknown:
        raise IngestionError(f"Datasets desconhecidos: {sorted(unknown)}")
    for name in names:
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", name):
            raise IngestionError("Identificador de dataset inválido")
        if not re.fullmatch(r"[a-zA-Z0-9_.-]+", datasets[name]["product"]):
            raise IngestionError("Identificador de produto inválido")
    http, metadata, plans, failures = HTTP(args.attempts, args.timeout), {}, {}, {}
    # Descoberta pública de todas as fontes antes de decidir a janela comum.
    for name in names:
        if name == "noaa_roni":
            continue
        try:
            metadata[name] = collection(http, datasets[name])
            atomic_json(store.root / f"metadata/{name}_discovery.json", metadata[name])
        except IngestionError as exc:
            failures[name] = str(exc)
    available = [item["available_period"] for item in metadata.values()]
    common_start = max((iso(x["start"]) for x in available), default=None)
    common_end = min((iso(x["end"]) for x in available), default=None)
    start = (
        datetime.combine(args.start, datetime.min.time(), timezone.utc).isoformat()
        if args.start
        else common_start.isoformat()
        if common_start
        else None
    )
    end = (
        datetime.combine(args.end, datetime.max.time(), timezone.utc).isoformat()
        if args.end
        else common_end.isoformat()
        if common_end
        else None
    )
    for name, meta in metadata.items():
        try:
            region = region_config(
                args.region or datasets[name]["region"], regions, args.regions_config
            )
            if datasets[name].get("domain") == "land" and region.get("domain") == "ocean":
                raise IngestionError("GLDAS terrestre não deve ser coletado em região oceânica")
            plans[name] = make_plan(name, datasets[name], meta, region, start, end, http)
        except IngestionError as exc:
            failures[name] = str(exc)
    if "noaa_roni" in names:
        plans["noaa_roni"] = {
            "dataset": "noaa_roni",
            "sources": datasets["noaa_roni"]["sources"],
            "access_method": "HTTPS_original_full_history",
            "authentication_required": False,
            "requested_period": {"start": start, "end": end},
            "note": "Preserva toda a fonte, sem filtrar a série nem inferir fases",
        }
    run = {
        **timestamps(),
        "mode": "dry_run" if args.dry_run else "fetch",
        "requested_datasets": names,
        "common_window_of_discovered_NASA_products": {
            "start": common_start,
            "end": common_end,
            "all_selected_products_discovered": not failures,
        },
        "plans": plans,
        "results": {},
        "failures": failures,
    }
    if not args.dry_run:
        for name in names:
            if name in failures:
                continue
            try:
                if name == "noaa_roni":
                    files = fetch_noaa(
                        datasets[name], http, store, args.refresh, plans[name]["requested_period"]
                    )
                else:
                    files = fetch_nasa(
                        datasets[name],
                        plans[name],
                        http,
                        store,
                        os.getenv("EARTHDATA_TOKEN"),
                        max_granules=args.max_granules,
                        wait_seconds=args.wait_seconds,
                        refresh=args.refresh,
                    )
                run["results"][name] = {"status": "complete", "files": len(files)}
            except IngestionError as exc:
                failures[name] = str(exc)
                LOG.error("dataset=%s: %s", name, exc)
            store.save()
    store.data["runs"].append(run)
    store.save()
    atomic_json(store.root / "metadata/latest_run.json", run)
    if not args.dry_run:
        inventory(store)
    print(json.dumps(run, ensure_ascii=False, indent=2, default=str))
    return 1 if failures else 0


def main(argv=None):
    load_dotenv(ROOT / ".env")
    args = parser().parse_args(argv)
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(logs / "ingestion.log"), logging.StreamHandler(sys.stderr)],
    )
    try:
        return execute(args)
    except IngestionError as exc:
        LOG.error("%s", exc)
        return 2
    except (OSError, ValueError, KeyError, yaml.YAMLError):
        # Não imprimir exceções externas: podem incluir tokens ou URLs assinadas.
        LOG.error("Configuração/manifesto inválido ou falha de disco; revise arquivos e parâmetros")
        return 2
