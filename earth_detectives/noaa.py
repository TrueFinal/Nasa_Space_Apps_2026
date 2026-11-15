"""Preserva índice e classificação originais; não calcula fases ENSO."""

import math
import re

from .core import IngestionError, fingerprint

SEASONS = "DJF JFM FMA MAM AMJ MJJ JJA JAS ASO SON OND NDJ".split()


def inspect_roni(path):
    lines = path.read_text().splitlines()
    if not lines or lines[0].split() != ["SEAS", "YR", "ANOM"]:
        raise IngestionError("Cabeçalho RONI inesperado; possível página de erro")
    periods, missing = [], 0
    for line in lines[1:]:
        if not line.strip():
            continue
        try:
            season, year_text, anomaly_text = line.split()
            year, anomaly = int(year_text), float(anomaly_text)
            month = SEASONS.index(season) + 1
        except (ValueError, TypeError) as exc:
            raise IngestionError("Registro RONI inválido") from exc
        if year < 1900 or year > 2200 or not math.isfinite(anomaly):
            raise IngestionError("Ano ou anomalia RONI inválido")
        periods.append(f"{year:04d}-{month:02d}")
        missing += int(anomaly == -99.9 or anomaly == -999.0)
    if not periods or periods != sorted(set(periods)):
        raise IngestionError("RONI vazio, duplicado ou fora de ordem")
    return {
        "variables": {"RONI": {"units": "degree_Celsius", "source": "NOAA definition"}},
        "dimensions": {"overlapping_season": len(periods)},
        "temporal_records": len(periods),
        "observation_period": {"start": periods[0], "end": periods[-1]},
        "time_convention": "year and central month of official overlapping season",
        "missing_values": missing,
        "classification": "preserved in companion official HTML; not inferred",
        "integrity": "valid_ASCII_records",
    }


def inspect_classification(path):
    content = path.read_bytes().decode("latin-1").lower()
    if not all(marker in content for marker in ("<html", "roni", "<table", "1950")):
        raise IngestionError("Página NOAA não contém a tabela histórica esperada")
    if not re.search(r"(warm|cold|episodes)", content):
        raise IngestionError("Página NOAA sem descrição dos episódios")
    return {
        "integrity": "HTML_historical_table_present",
        "classification": "original HTML retained verbatim, including official styling",
        "variables": {},
        "temporal_records": None,
        "missing_values": None,
    }


def fetch_noaa(dataset, http, store, refresh=False, requested_period=None):
    result = []
    for kind, url in dataset["sources"].items():
        key = fingerprint({"dataset": "noaa_roni", "kind": kind, "url": url})
        if not refresh and (cached := store.cached(key)):
            result.append(cached)
            continue
        suffix, validator = (
            ("txt", inspect_roni) if kind == "series" else ("html", inspect_classification)
        )
        path, audit = http.download(
            url, store.root / f"raw/noaa_roni/RONI/global_index/{kind}.{suffix}", validator
        )
        metadata = {
            "dataset": "noaa_roni",
            "organization": dataset["organization"],
            "product": dataset["product"],
            "version": dataset["version"],
            "collection_id": None,
            "doi": None,
            "variables_requested": dataset["variables"] if kind == "series" else [],
            "spatial_resolution": dataset["spatial_resolution"],
            "temporal_resolution": dataset["temporal_resolution"],
            "requested_period": requested_period,
            "region": {
                "id": "global_index",
                "crs": "EPSG:4326",
                "index_region_bbox": [-170, -5, -120, 5],
            },
            "source_url": url,
            "endpoint": url,
            "request_parameters": {},
            "access_method": "HTTPS_original_full_history",
            "quality": "revisable official series; no local phase classification",
            "transformations": [],
        }
        result.append(store.record(key, path, audit, metadata))
    return result
