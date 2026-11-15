"""Observed SPHEREx source/instrument classifier with Gaia DR3 label provenance.

No injected pixels or synthetic labels. Gaia matches label observed sources;
instrument flags label contamination. Unknown sky detections stay unlabeled.
Features are from native exposures in BOTH training and candidate inference.
This does not train an asteroid-vs-star classifier or a DIA-specific real/bogus model.
"""

import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np
import xgboost as xgb
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.table import Table
from astropy.time import Time
from astropy.wcs import WCS
from scipy.ndimage import convolve, maximum_filter

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402

from .classification import FEATURES, extract_features, fit_bounded, write_csv
from .quality import bad_pixel_mask
from .real_data import DEC, RA
from .sprints import run_motion
from .zogy_pipeline import sep_catalog

ARTIFACT_BITS = [0, 1, 2, 6, 10, 11, 19, 20, 22, 25, 27]


def acquire_catalogs(folder="data/catalogs"):
    from astroquery.gaia import Gaia
    from astroquery.ipac.irsa import Irsa

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    gaia_file, irsa_file = folder / "gaia_dr3.ecsv", folder / "spherex_astroquery.ecsv"
    query = (
        "SELECT source_id,ra,dec,ref_epoch,pmra,pmdec,phot_g_mean_mag,ruwe "
        f"FROM gaiadr3.gaia_source WHERE 1=CONTAINS(POINT('ICRS',ra,dec),"
        f"CIRCLE('ICRS',{RA},{DEC},0.22)) AND phot_g_mean_mag<20"
    )
    if not gaia_file.exists():
        Gaia.TIMEOUT = 60
        Gaia.launch_job(query).get_results().write(gaia_file)
    if not irsa_file.exists():
        Irsa.TIMEOUT = 60
        result = Irsa.query_sia(pos=(RA, DEC, 0.01), collection="spherex_dr1")
        table = result if isinstance(result, Table) else result.to_table()
        table.write(irsa_file)
    (folder / "gaia_query.adql").write_text(query)
    return Table.read(gaia_file), Table.read(irsa_file)


def identity_group(identity):
    return int(hashlib.sha256(str(identity).encode()).hexdigest()[:8], 16) % 16


def native_psf(h, x, y):
    header = h["IMAGE"].header
    original_x, original_y = 1 + x - header["CRPIX1A"], 1 + y - header["CRPIX2A"]
    rows = h["EPSF"].data
    i = np.argmin((rows["XCENTER"] - original_x) ** 2 + (rows["YCENTER"] - original_y) ** 2)
    psf = np.array(rows["EPSF"][i], float)
    sy, sx = int(h["EPSF"].header["OVSMPY"]), int(h["EPSF"].header["OVSMPX"])
    cy, cx = np.array(psf.shape) // 2
    sampled = np.maximum(
        psf[cy - 3 * sy : cy + 3 * sy + 1 : sy, cx - 3 * sx : cx + 3 * sx + 1 : sx], 0
    )
    return sampled / sampled.sum()


def native_representation(data, variance, finite, psf):
    weight = np.where(finite, 1 / np.where(finite, variance, 1), 0)
    numerator = convolve(np.where(finite, data, 0) * weight, psf, mode="constant")
    information = convolve(weight, psf**2, mode="constant")
    score = np.zeros_like(data)
    np.divide(numerator, np.sqrt(np.maximum(information, 0)), out=score, where=information > 0)
    return dict(
        difference=np.where(finite, data / np.sqrt(np.where(finite, variance, 1)), 0),
        scorr=score,
        valid=finite,
        psf_difference=np.pad(psf, 6),
    )


def gaia_at_epoch(gaia, mjd):
    pmra, pmdec = (
        np.asarray(gaia[k].filled(0), float)
        if hasattr(gaia[k], "filled")
        else np.asarray(gaia[k], float)
        for k in ["pmra", "pmdec"]
    )
    coordinates = SkyCoord(
        ra=gaia["ra"],
        dec=gaia["dec"],
        pm_ra_cosdec=np.nan_to_num(pmra) * u.mas / u.yr,
        pm_dec=np.nan_to_num(pmdec) * u.mas / u.yr,
        obstime=Time(2016.0, format="jyear"),
    )
    return coordinates.apply_space_motion(new_obstime=Time(mjd, format="mjd"))


def extract_observed_frames(records, catalogs, keep_native=True):
    rows, native, thumbnails = [], [], []
    artifact_mask = sum(1 << bit for bit in ARTIFACT_BITS)
    for epoch, rec in enumerate(records):
        gaia = catalogs[rec.get("field_id", "base")]
        with fits.open(rec["path"]) as h:
            image = np.array(h["IMAGE"].data - h["ZODI"].data, float)
            variance = np.array(h["VARIANCE"].data, float)
            flags = h["FLAGS"].data.astype(np.uint32)
            finite = np.isfinite(image) & np.isfinite(variance) & (variance > 0)
            data, catalog, _ = sep_catalog(image, variance, ~finite, threshold=3.0)
            wcs = WCS(h["IMAGE"].header, naxis=2)
            psf = native_psf(h, (image.shape[1] - 1) / 2, (image.shape[0] - 1) / 2)
            representation = native_representation(data, variance, finite, psf)
            coordinates = gaia_at_epoch(gaia, h["IMAGE"].header["MJD-AVG"])
            if keep_native:
                native.append(dict(wcs=wcs, representation=representation, gaia=coordinates))
            ra, dec = wcs.pixel_to_world_values(catalog["x"], catalog["y"])
            sky = SkyCoord(ra * u.deg, dec * u.deg)
            index, sep, _ = sky.match_to_catalog_sky(coordinates)
            _, second_distance, _ = sky.match_to_catalog_sky(coordinates, nthneighbor=2)
            accepted = 0
            for j, obj in enumerate(catalog):
                x, y = int(round(obj["x"])), int(round(obj["y"]))
                if min(x, y) < 7 or x + 7 >= image.shape[1] or y + 7 >= image.shape[0]:
                    continue
                g = int(index[j])
                if (
                    sep[j].arcsec > 2
                    or second_distance[j].arcsec < 6.15
                    or float(gaia["phot_g_mean_mag"][g]) > 18.5
                    or bad_pixel_mask(flags[y - 1 : y + 2, x - 1 : x + 2]).any()
                ):
                    continue
                features = extract_features(representation, x, y)
                if features is None:
                    continue
                identity = "gaia:" + str(gaia["source_id"][g])
                rows.append(
                    dict(
                        sample_id=len(rows),
                        spatial_group=identity_group(identity),
                        identity=identity,
                        epoch=epoch,
                        x=x,
                        y=y,
                        label=1,
                        label_origin="Gaia DR3 matched observed SPHEREx source",
                        gaia_source_id=str(gaia["source_id"][g]),
                        gaia_separation_arcsec=float(sep[j].arcsec),
                        instrument_flags=int(flags[y, x]),
                        **features,
                    )
                )
                accepted += 1
                if sum(t["label"] == 1 for t in thumbnails) < 6:
                    thumbnails.append(dict(label=1, data=data[y - 6 : y + 7, x - 6 : x + 7].copy()))
            snr = representation["difference"]
            peaks = (
                (np.abs(snr) > 3)
                & (np.abs(snr) == maximum_filter(np.abs(snr), size=3))
                & ((flags & artifact_mask) != 0)
                & finite
            )
            yy, xx = np.nonzero(peaks)
            ra, dec = wcs.pixel_to_world_values(xx, yy)
            _, separation, _ = SkyCoord(ra * u.deg, dec * u.deg).match_to_catalog_sky(coordinates)
            negatives = 0
            for j, (x, y) in enumerate(zip(xx, yy)):
                if separation[j].arcsec < 6.15:
                    continue
                features = extract_features(representation, x, y, sign=1 if snr[y, x] >= 0 else -1)
                if features is None:
                    continue
                ox = int(round(1 + x - h["IMAGE"].header["CRPIX1A"]))
                oy = int(round(1 + y - h["IMAGE"].header["CRPIX2A"]))
                identity = f"detector{h['IMAGE'].header['DETECTOR']}:{ox}:{oy}"
                rows.append(
                    dict(
                        sample_id=len(rows),
                        spatial_group=identity_group(identity),
                        identity=identity,
                        epoch=epoch,
                        x=int(x),
                        y=int(y),
                        label=0,
                        label_origin="Observed SPHEREx instrumental-contamination flag",
                        gaia_source_id="",
                        gaia_separation_arcsec=float(separation[j].arcsec),
                        instrument_flags=int(flags[y, x]),
                        **features,
                    )
                )
                negatives += 1
                if sum(t["label"] == 0 for t in thumbnails) < 6:
                    thumbnails.append(dict(label=0, data=data[y - 6 : y + 7, x - 6 : x + 7].copy()))
            print(
                "Observed epoch",
                epoch,
                "Gaia sources",
                accepted,
                "instrumental examples",
                negatives,
                flush=True,
            )
    return rows, native, thumbnails


def run_observed(
    output="outputs/observed", timeout=120.0, reuse_training=False, training_metrics_path=None
):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    gaia, archive = acquire_catalogs()
    manifest = json.loads(Path("data/spherex/manifest.json").read_text())
    gaia.write(output / "gaia_catalog.ecsv", overwrite=True)
    archive.write(output / "spherex_archive_query.ecsv", overwrite=True)
    available_ids = set(map(str, archive["obs_id"]))
    if any(rec["obs_id"] not in available_ids for rec in manifest["files"]):
        raise ValueError("Some FITS observation IDs were not returned by the live IRSA query.")
    rows, native, thumbnails = extract_observed_frames(manifest["files"], {"base": gaia})
    write_csv(output / "observed_training_samples.csv", rows)
    np.savez_compressed(
        output / "observed_thumbnails.npz",
        images=np.array([t["data"] for t in thumbnails]),
        labels=[t["label"] for t in thumbnails],
    )
    registry = Path("outputs/active_observed_model.json")
    if training_metrics_path is None and registry.exists():
        training_metrics_path = json.loads(registry.read_text())["metrics_path"]
    if training_metrics_path is not None:
        metrics = json.loads(Path(training_metrics_path).read_text())
        metrics["external_training_metrics"] = str(training_metrics_path)
        (output / "training_metrics.json").write_text(json.dumps(metrics, indent=2))
    elif reuse_training:
        metrics = json.loads((output / "training_metrics.json").read_text())
        matrix = np.load(output / "training_matrix.npz")
        current_x = np.array([[r[k] for k in FEATURES] for r in rows])
        current_y = np.array([r["label"] for r in rows])
        if (
            current_x.shape != matrix["x"].shape
            or not np.allclose(current_x, matrix["x"])
            or not np.array_equal(current_y, matrix["y"])
        ):
            raise ValueError("Observed training data changed; rerun without --reuse-training.")
    else:
        metrics = fit_bounded(
            rows,
            output,
            timeout,
            evaluation_domain="Observed SPHEREx/Gaia sources versus flagged contamination",
            split_description="Disjoint Gaia IDs/detector coordinates; flags and IDs excluded",
        )
    if metrics["status"] != "complete":
        (output / "observed_report.json").write_text(
            json.dumps(dict(training=metrics, n_observed_samples=len(rows)), indent=2)
        )
        return metrics
    model = xgb.Booster({"nthread": 2})
    model.load_model(metrics["model_path"])
    upstream = json.loads(Path("outputs/zogy/report.json").read_text())
    with fits.open(manifest["files"][0]["path"]) as h:
        reference_wcs = WCS(h["IMAGE"].header, naxis=2)
    cx, cy = np.rint(reference_wcs.world_to_pixel_values(RA, DEC))
    origin_x, origin_y = cx - 56, cy - 56
    ranking = []
    for i, candidate in enumerate(upstream["candidates"]):
        epoch = candidate["science"] if candidate["sign"] > 0 else candidate["reference"]
        ra, dec = reference_wcs.pixel_to_world_values(
            candidate["x"] + origin_x, candidate["y"] + origin_y
        )
        x, y = map(float, native[epoch]["wcs"].world_to_pixel_values(ra, dec))
        if not np.isfinite(x + y):
            continue
        features = extract_features(native[epoch]["representation"], int(round(x)), int(round(y)))
        if features is None:
            continue
        gi, gs, _ = SkyCoord(float(ra) * u.deg, float(dec) * u.deg).match_to_catalog_sky(
            native[epoch]["gaia"]
        )
        gaia_index = int(np.asarray(gi).reshape(-1)[0])
        gaia_separation = float(np.asarray(gs.arcsec).reshape(-1)[0])
        ranking.append(
            {
                "candidate_id": i,
                **candidate,
                "zogy_abs_scorr": candidate["abs_scorr"],
                **features,
                "human_label": "",
                "label_status": "unlabeled real candidate",
                "gaia_source_id": str(gaia["source_id"][gaia_index])
                if gaia_separation <= 2
                else "",
                "gaia_separation_arcsec": gaia_separation,
            }
        )
    matrix = np.array([[r[k] for k in FEATURES] for r in ranking])
    scores = model.predict(xgb.DMatrix(matrix, feature_names=FEATURES, nthread=2))
    for row, score in zip(ranking, scores):
        row.update(
            source_like_score=float(score),
            predicted_class="fonte_candidata" if score >= 0.5 else "provavel_artefato",
            ranking_method="Observed native SPHEREx/Gaia source-vs-instrument model",
        )
    ranking.sort(key=lambda r: r["source_like_score"], reverse=True)
    for i, row in enumerate(ranking, 1):
        row["rank"] = i
    (output / "candidate_ranking.json").write_text(json.dumps(ranking, indent=2))
    write_csv(output / "candidate_ranking.csv", ranking)
    motion = run_motion(output, include_controls=False)
    report = dict(
        training=metrics,
        n_gaia_catalog_sources=len(gaia),
        n_spherex_archive_rows=len(archive),
        n_observed_samples=len(rows),
        n_actual_model_training_rows=sum(
            metrics.get(k, 0) for k in ["n_train", "n_validation", "n_test"]
        ),
        n_positive_samples=sum(r["label"] for r in rows),
        n_flagged_contamination_samples=sum(not r["label"] for r in rows),
        artificial_samples=0,
        unique_gaia_source_ids=len({r["gaia_source_id"] for r in rows if r["label"] == 1}),
        input_files=[
            dict(**rec, sha256=hashlib.sha256(Path(rec["path"]).read_bytes()).hexdigest())
            for rec in manifest["files"]
        ],
        gaia_match_radius_arcsec=2.0,
        gaia_exclusion_radius_for_artifacts_arcsec=6.15,
        negative_label_bits=ARTIFACT_BITS,
        n_ranked_candidates=len(ranking),
        motion=motion,
        positive_definition="Observed SPHEREx source, isolated Gaia counterpart, clean core",
        negative_definition="Observed instrumental peak; no Gaia counterpart within 6.15 arcsec",
        unknown_definition="Not matching Gaia alone never creates a negative label",
        feature_domain="Native flux and PSF score, not DIA-residual morphology",
        label_caveat="Catalog/flag supervised labels; not manually confirmed asteroid events",
        apis=dict(
            spherex="astroquery.ipac.irsa.Irsa.query_sia", gaia="astroquery.gaia.Gaia.launch_job"
        ),
    )
    (output / "observed_report.json").write_text(json.dumps(report, indent=2))
    fig, axes = plt.subplots(2, 6, figsize=(13, 5), layout="constrained")
    for label in [1, 0]:
        selected = [t for t in thumbnails if t["label"] == label]
        for ax, thumb in zip(axes[1 - label], selected):
            data = thumb["data"]
            bound = max(np.max(np.abs(data)), 1e-6)
            ax.imshow(data, origin="lower", cmap="gray", vmin=-bound * 0.1, vmax=bound)
            ax.set_xticks([])
            ax.set_yticks([])
            ax.set_title("Fonte Gaia" if label else "Flag instrumental", fontsize=9)
    fig.suptitle("Exemplos OBSERVADOS do SPHEREx — nenhum pixel injetado")
    fig.savefig(output / "observed_examples.png", dpi=150)
    plt.close(fig)
    print(
        "Local observed examples:",
        len(rows),
        "; active model dataset rows:",
        report["n_actual_model_training_rows"],
        "; training wall seconds:",
        metrics["wall_seconds"],
        flush=True,
    )
    return report


if __name__ == "__main__":
    run_observed()
