"""MPC identities and SPHEREx-anchored positional catalogue associations.

External fluxes retain their native filters/epochs. This is a left join of
context, never a fabricated 102-channel spectrum from Gaia or WISE photometry.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import astropy.units as u
import numpy as np
from astropy.coordinates import SkyCoord
from astropy.table import Table

MPC = "https://data.minorplanetcenter.net/api/query-identifier"
GRID = Path(__file__).with_name("spherex_channels.json")
# Approximate retrieval windows only; not response curves or synthetic photometry.
WISE_WINDOWS = {"W1": (2.8, 3.8), "W2": (4.1, 5.2)}


@lru_cache(maxsize=1)
def channel_grid():
    return json.loads(GRID.read_text(encoding="utf-8"))


def channel_for(wave, detector):
    if wave is None or not np.isfinite(wave):
        return None
    choices = [
        c
        for c in channel_grid()["channels"]
        if c["detector"] == detector and c["low_um"] <= wave <= c["high_um"]
    ]
    return min(choices, key=lambda c: abs(c["center_um"] - wave)) if choices else None


def wise_bands(channel):
    return (
        [
            name
            for name, (lo, hi) in WISE_WINDOWS.items()
            if channel["low_um"] <= hi and channel["high_um"] >= lo
        ]
        if channel
        else []
    )


def resolve_mpc(name, cache):
    from .infrared_archive import _open
    from .infrared_mask import sha256, write_json

    name = str(name).strip()
    if not name or len(name) > 80 or any(ord(c) < 32 for c in name):
        raise ValueError("Invalid MPC identifier.")
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / (hashlib.sha256(name.encode()).hexdigest()[:24] + ".json")
    payload = {"ids": [name]}
    # GET with JSON body is the documented MPC protocol. Cache for at most one day.
    if not path.exists() or datetime.now().timestamp() - path.stat().st_mtime > 86400:
        req = urllib.request.Request(
            MPC,
            data=json.dumps(payload).encode(),
            method="GET",
            headers={"Content-Type": "application/json", "User-Agent": "Zephyr-IR-Lab/0.2"},
        )
        with _open(req) as response:
            if urllib.parse.urlsplit(response.url).hostname != "data.minorplanetcenter.net":
                raise ValueError("MPC redirecionou para host inesperado.")
            raw = response.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError("Resposta MPC excede o limite.")
        value = json.loads(raw)
        if not isinstance(value, dict) or not isinstance(value.get(name), dict):
            raise ValueError("MPC retornou uma resposta inesperada.")
        write_json(path, value)
        write_json(
            path.with_suffix(".source.json"),
            {
                "url": MPC,
                "request": payload,
                "sha256": sha256(path),
                "fetched_utc": datetime.now(timezone.utc).isoformat(),
            },
        )
    value = json.loads(path.read_text("utf-8"))[name]
    found = int(value.get("found", 0))
    choices = [value] if found == 1 else (value.get("disambiguation_list") or [])[:50]
    items = []
    for row in choices:
        identifier = (
            row.get("permid")
            or row.get("iau_designation")
            or row.get("unpacked_primary_provisional_designation")
        )
        if identifier:
            items.append(
                {
                    "identifier": str(identifier).strip("() "),
                    "name": row.get("name"),
                    "object_type": row.get("object_type"),
                    "designation": row.get("unpacked_primary_provisional_designation"),
                }
            )
    return {
        "status": "resolved" if found == 1 and items else "ambiguous" if found > 1 else "not_found",
        "query": name,
        "items": items,
        "provenance": {"url": MPC, "request": payload, "sha256": sha256(path)},
    }


def _clean(value):
    if np.ma.is_masked(value):
        return None
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if np.isfinite(value) else None
    return str(value)


def fetch_wise_context(ra, dec, cache):
    from .infrared_archive import IRSA, download
    from .infrared_mask import sha256

    cache = Path(cache)
    result = {}
    for key, catalog, columns in (
        (
            "allwise",
            "allwise_p3as_psd",
            "source_id,designation,coadd_id,ra,dec,w1mpro,w2mpro,cc_flags,ph_qual",
        ),
        ("neowise", "neowiser_p1bs_psd", "source_id,ra,dec,mjd,w1mpro,w2mpro,cc_flags,ph_qual"),
    ):
        url = (
            IRSA
            + "cgi-bin/Gator/nph-query?"
            + urllib.parse.urlencode(
                {
                    "catalog": catalog,
                    "spatial": "Cone",
                    "objstr": f"{ra:.8f} {dec:.8f}",
                    "radius": "0.09",
                    "radunits": "deg",
                    "outfmt": "1",
                    "outrows": "2000",
                    "selcols": columns,
                }
            )
        )
        try:
            path = download(url, cache / f"{key}.tbl", 5 * 1024 * 1024)
            table = Table.read(path, format="ascii.ipac")
            rows = [{col: _clean(row[col]) for col in table.colnames} for row in table]
            result[key] = {
                "status": "loaded" if len(rows) < 2000 else "truncated",
                "rows": rows,
                "url": url,
                "sha256": sha256(path),
            }
        except (OSError, ValueError, KeyError) as exc:
            result[key] = {"status": "unavailable", "rows": [], "url": url, "reason": str(exc)}
    # Official coadd IDs come from the catalogue; do not guess a tile from RA.
    rows = []
    coadds = {str(row.get("coadd_id", "")) for row in result["allwise"]["rows"]}
    for coadd in sorted(coadds):
        if not re.fullmatch(r"[0-9]{4}[pm][0-9]{3}_ac[0-9]+", coadd):
            continue
        for band in (1, 2):
            image = (
                IRSA + f"ibe/data/wise/allwise/p3am_cdd/{coadd[:2]}/{coadd[:4]}/"
                f"{coadd}/{coadd}-w{band}-int-3.fits"
            )
            rows.append({"band": f"W{band}", "coadd_id": coadd, "base_url": image})
    result["images"] = {
        "status": result["allwise"]["status"],
        "rows": rows,
        "method": "official AllWISE coadd_id from positional catalogue candidates",
    }
    return result


def _nearby(ra, dec, records, radius=3.0):
    valid = [
        r
        for r in records
        if r.get("ra") is not None
        and r.get("dec") is not None
        and np.isfinite(float(r["ra"]) + float(r["dec"]))
    ]
    if not valid:
        return []
    sky = SkyCoord(
        [float(r["ra"]) for r in valid] * u.deg, [float(r["dec"]) for r in valid] * u.deg
    )
    separation = SkyCoord(ra * u.deg, dec * u.deg).separation(sky).arcsec
    return [
        {**valid[i], "separation_arcsec": float(separation[i])}
        for i in np.argsort(separation)
        if separation[i] <= radius
    ][:20]


def build_join(report, context=None):
    """Left join covered SPHEREx samples to all positional candidates within 3 arcsec."""
    context = context or {}
    samples = []
    for frame in report["frames"]:
        if frame.get("plot", {}).get("eligible") is False:
            continue
        points = [("target", frame["target"])] + [
            ("gaia-" + str(s["source_id"]), s) for s in frame.get("gaia", [])[:100]
        ]
        for kind, point in points:
            x, y = point["x"], point["y"]
            if not np.isfinite(x + y):
                continue
            ix, iy = int(np.floor(x + 0.5)), int(np.floor(y + 0.5))
            height, width = frame["shape"]
            if not (0 <= ix < width and 0 <= iy < height):
                continue
            if frame["mask"][iy][ix] & (1 | 2 | 4 | 16):
                continue
            wave = frame["wavelength"][iy][ix]
            channel = channel_for(wave, frame["detector"])
            bands = wise_bands(channel)
            ra, dec = float(point["ra"]), float(point["dec"])
            gaia = _nearby(ra, dec, frame.get("gaia", []))
            wise = _nearby(ra, dec, context.get("allwise", {}).get("rows", [])) if bands else []
            neo = _nearby(ra, dec, context.get("neowise", {}).get("rows", [])) if bands else []
            for candidate in neo:
                mjd = candidate.get("mjd")
                candidate["delta_days"] = (
                    abs(float(mjd) - frame["mjd_utc"]) if mjd is not None else None
                )
                candidate["epoch_compatible"] = (
                    candidate["delta_days"] is not None and candidate["delta_days"] <= 1
                )
            query = urllib.parse.urlencode({"ra": f"{ra:.8f}", "dec": f"{dec:.8f}", "size": 176})
            images = [
                {
                    **row,
                    "url": row["base_url"]
                    + "?"
                    + urllib.parse.urlencode({"center": f"{ra:.8f},{dec:.8f}", "size": "0.12"}),
                }
                for row in context.get("images", {}).get("rows", [])
                if row["band"] in bands and row["coadd_id"] in {c.get("coadd_id") for c in wise}
            ]
            samples.append(
                {
                    "id": frame["id"] + ":" + kind,
                    "frame_id": frame["id"],
                    "kind": "target" if kind == "target" else "gaia",
                    "ra": ra,
                    "dec": dec,
                    "mjd": frame["mjd_utc"],
                    "utc": frame["utc"],
                    "detector": frame["detector"],
                    "lambda_um": wave,
                    "channel_id": channel["id"] if channel else None,
                    "wise_bands": bands,
                    "gaia_candidates": gaia,
                    "allwise_candidates": wise,
                    "neowise_candidates": neo,
                    "wiseview_url": "https://byw.tools/wiseview#" + query,
                    "wise_images": images,
                    "association": "positional_context_not_identity",
                }
            )
    channels = [
        {**c, "samples": sum(s["channel_id"] == c["id"] for s in samples)}
        for c in channel_grid()["channels"]
    ]
    return {
        "base": "SPHEREx CWAVE / official 102-channel grid",
        "radius_arcsec": 3.0,
        "gaia_samples_per_frame_limit": 100,
        "gaia_truncated_frames": [
            f["id"] for f in report["frames"] if len(f.get("gaia", [])) > 100
        ],
        "candidates_per_catalogue_per_sample_limit": 20,
        "channel_mapping": (
            "Nearest nominal centre inside official detector/channel wavelength interval"
        ),
        "neowise_epoch_tolerance_days": 1,
        "channels": channels,
        "samples": samples,
        "catalogue_status": {
            k: {a: b for a, b in v.items() if a != "rows"} for k, v in context.items()
        },
        "limitations": [
            "Associações posicionais não identificam um objeto móvel.",
            "Gaia é propagado à época SPHEREx; WISE mantém época e filtro originais.",
            "Gaia/WISE não preenchem canais SPHEREx sem observação.",
            "Janelas W1/W2 aproximadas selecionam contexto, não equivalência fotométrica.",
        ],
    }
