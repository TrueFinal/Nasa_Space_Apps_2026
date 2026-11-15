"""Exploratory search on public SPHEREx cutouts, with download provenance.

The native image pixels are filtered before WCS mapping: noisy science images
are never interpolated for the search. The Gaussian PSF and constant flux model
are provisional; scores are not discovery significances.
"""

import json
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

import matplotlib
import numpy as np
from astropy.io import fits
from astropy.table import Table
from astropy.time import Time
from astropy.wcs import WCS
from scipy.interpolate import RegularGridInterpolator
from scipy.ndimage import binary_dilation, maximum_filter

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402

from .core import Candidate, Sequence, _filtered
from .quality import bad_pixel_mask

RA, DEC = 134.6917, 16.0303
SOURCE = "https://irsa.ipac.caltech.edu/spherex-archive-documentation/spherex-data-access/"


def download(data_dir="data/spherex"):
    folder = Path(data_dir)
    folder.mkdir(parents=True, exist_ok=True)
    query = "https://irsa.ipac.caltech.edu/SIA?" + urlencode(
        {"COLLECTION": "spherex_dr1", "POS": f"CIRCLE {RA} {DEC} 0.01"}
    )
    catalog = folder / "query.xml"
    if not catalog.exists():
        with urlopen(query, timeout=60) as response:
            catalog.write_bytes(response.read())
    table = Table.read(catalog, format="votable", use_names_over_ids=True)
    # A compact actual sequence: two groups of four slews on 2025-10-31.
    selected = table[
        (np.asarray(table["energy_bandpassname"]) == "SPHEREx-D1")
        & (np.asarray(table["t_min"], float) > 60979.3)
        & (np.asarray(table["t_min"], float) < 60979.4)
    ]
    selected.sort("t_min")
    if len(selected) < 2:
        raise RuntimeError("A consulta não retornou a sequência esperada.")
    selected.write(folder / "selected.ecsv", overwrite=True)
    records = []
    for row in selected:
        url = str(row["access_url"]) + "?" + urlencode({"center": f"{RA},{DEC}", "size": "0.25"})
        path = folder / (str(row["obs_id"]) + "D1.fits")
        if not path.exists():
            for attempt in range(3):
                try:
                    with urlopen(url, timeout=45) as response:
                        payload = response.read()
                    temporary = path.with_suffix(".partial")
                    temporary.write_bytes(payload)
                    with fits.open(temporary) as h:
                        if "IMAGE" not in h or "VARIANCE" not in h:
                            raise ValueError("Resposta sem imagem/variância.")
                    temporary.replace(path)
                    break
                except Exception:
                    if attempt == 2:
                        raise
        records.append(dict(path=str(path), url=url, obs_id=str(row["obs_id"])))
        print("FITS disponível:", path.name, flush=True)
    manifest = dict(
        query_url=query,
        documentation=SOURCE,
        ra_deg=RA,
        dec_deg=DEC,
        cutout_size_deg=0.25,
        files=records,
    )
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def _wave_at(h, x, y):
    """Visualization-grade wavelength only; not science CWAVE/CBAND calibration."""
    row = h["WCS-WAVE"].data[0]
    header = h["IMAGE"].header
    # Convert cutout zero-based coordinates to original FITS one-based pixels.
    ox, oy = x + 2 - header["CRPIX1A"], y + 2 - header["CRPIX2A"]
    values = np.asarray(row["VALUES"])
    return RegularGridInterpolator(
        (row["Y"], row["X"]), values, bounds_error=False, fill_value=np.nan
    )([[oy, ox]])[0]


def _load(manifest):
    frames, variances, masks, wcs_list, metadata = [], [], [], [], []
    for record in manifest["files"]:
        with fits.open(record["path"]) as h:
            image = np.array(h["IMAGE"].data, float)
            variance = np.array(h["VARIANCE"].data, float)
            flags = h["FLAGS"].data
            mask = (
                bad_pixel_mask(flags)
                | ~np.isfinite(image)
                | ~np.isfinite(variance)
                | (variance <= 0)
            )
            residual = image - h["ZODI"].data
            residual -= np.median(residual[~mask])
            bright = (residual > 8 * np.sqrt(np.maximum(variance, 0))) & ~mask
            mask |= binary_dilation(bright, iterations=3)
            wcs = WCS(h["IMAGE"].header, naxis=2)
            cx, cy = wcs.world_to_pixel_values(RA, DEC)
            wave, band = _wave_at(h, cx, cy)
            metadata.append(
                dict(
                    **record,
                    mjd_avg=float(h["IMAGE"].header["MJD-AVG"]),
                    date_avg=h["IMAGE"].header["DATE-AVG"],
                    shape=list(image.shape),
                    original_shape=[2040, 2040],
                    unit=h["IMAGE"].header["BUNIT"],
                    center_wave_um_preview=float(wave),
                    bandwidth_um_preview=float(band),
                    masked_fraction=float(np.mean(mask)),
                )
            )
            frames.append(residual)
            variances.append(variance)
            masks.append(mask)
            wcs_list.append(wcs)
    shape = np.max([a.shape for a in frames], axis=0)

    def pad(a, value):
        return np.pad(
            a, [(0, shape[0] - a.shape[0]), (0, shape[1] - a.shape[1])], constant_values=value
        )

    mjd = np.array([m["mjd_avg"] for m in metadata])
    sequence = Sequence(
        [pad(a, 0) for a in frames],
        (mjd - mjd[0]) * 24,
        [pad(a, np.inf) for a in variances],
        [pad(a, True) for a in masks],
    )
    return sequence, wcs_list, metadata


def run_real(output="outputs/spherex", data_dir="data/spherex"):
    manifest = download(data_dir)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    sequence, wcs_list, metadata = _load(manifest)
    reference = wcs_list[0]
    # Evaluate on a central 96x96 region, with exact WCS for every tested path.
    cx, cy = reference.world_to_pixel_values(RA, DEC)
    yy, xx = np.mgrid[:96, :96].astype(float)
    xx += np.rint(cx) - 48
    yy += np.rint(cy) - 48
    nums, dens = _filtered(sequence, sigma=1.2)

    def evaluate(vx, vy, indices=None):
        total, info = np.zeros_like(xx), np.zeros_like(xx)
        count = np.zeros_like(xx, dtype=int)
        images, weights = [], []
        indices = list(range(len(nums))) if indices is None else list(indices)
        for i in indices:
            t = sequence.dt[i]
            ra, dec = reference.pixel_to_world_values(xx + vx * t, yy + vy * t)
            px, py = wcs_list[i].world_to_pixel_values(ra, dec)
            ix, iy = np.rint(px).astype(int), np.rint(py).astype(int)
            inside = (ix >= 0) & (iy >= 0) & (ix < nums.shape[2]) & (iy < nums.shape[1])
            ix = np.clip(ix, 0, nums.shape[2] - 1)
            iy = np.clip(iy, 0, nums.shape[1] - 1)
            good = inside & (dens[i, iy, ix] > 0)
            total += np.where(good, nums[i, iy, ix], 0)
            info += np.where(good, dens[i, iy, ix], 0)
            count += good
            weight = np.where(inside, 1 / sequence.variance[i, iy, ix], 0)
            images.append(sequence.images[i, iy, ix] * weight)
            weights.append(weight)
        score = np.full_like(xx, -np.inf)
        np.divide(total, np.sqrt(info), out=score, where=(info > 0) & (count == len(indices)))
        weights = np.sum(weights, axis=0)
        mean = np.full_like(xx, np.nan)
        np.divide(np.sum(images, axis=0), weights, out=mean, where=weights > 0)
        return score, mean, count

    # Nonzero velocity hypotheses; stationary sources remain a contamination risk.
    candidates = []
    best_map = np.full_like(xx, -np.inf)
    for vx in np.arange(-8, 9, 1.0):
        for vy in np.arange(-8, 9, 1.0):
            if np.hypot(vx, vy) < 1:
                continue
            score, _, count = evaluate(vx, vy)
            best_map = np.maximum(best_map, score)
            peaks = (score > 5) & (score == maximum_filter(score, size=5))
            ys, xs = np.nonzero(peaks)
            for j in np.argsort(score[ys, xs])[-5:]:
                y, x = ys[j], xs[j]
                candidates.append(
                    Candidate(
                        float(xx[y, x]),
                        float(yy[y, x]),
                        float(vx),
                        float(vy),
                        float(score[y, x]),
                        0,
                        int(count[y, x]),
                    )
                )
    candidates.sort(key=lambda c: c.snr, reverse=True)
    selected = []
    for c in candidates:
        if all(
            np.max(
                np.hypot(
                    c.x - p.x + (c.vx - p.vx) * sequence.dt, c.y - p.y + (c.vy - p.vy) * sequence.dt
                )
            )
            >= 3
            for p in selected
        ):
            selected.append(c)
        if len(selected) >= 10:
            break
    zero_score, stationary, _ = evaluate(0, 0)
    best = selected[0] if selected else None
    tracked = evaluate(best.vx, best.vy)[1] if best else stationary
    wavelengths = [m["center_wave_um_preview"] for m in metadata]
    candidate_records = []
    for c in selected:
        row, col = int(round(c.y - yy[0, 0])), int(round(c.x - xx[0, 0]))
        record = asdict(c)
        record.pop("flux")  # No calibrated flux is measured by this exploratory search.
        record["snr_model_uncalibrated"] = record.pop("snr")
        record["zero_motion_snr_at_same_position"] = (
            float(zero_score[row, col]) if np.isfinite(zero_score[row, col]) else None
        )
        record["group_snrs_model_uncalibrated"] = []
        for group in [range(4), range(4, 8)]:
            score = evaluate(c.vx, c.vy, indices=group)[0][row, col]
            record["group_snrs_model_uncalibrated"].append(
                float(score) if np.isfinite(score) else None
            )
        record["ra_deg"], record["dec_deg"] = map(float, reference.pixel_to_world_values(c.x, c.y))
        candidate_records.append(record)
    report = dict(
        experiment="REAL SPHEREx DR1 exposures, no injected moving source",
        documentation=SOURCE,
        center_ra_deg=RA,
        center_dec_deg=DEC,
        n_exposures=len(metadata),
        start_utc=metadata[0]["date_avg"],
        end_utc=metadata[-1]["date_avg"],
        time_span_hours=float(np.ptp(sequence.times_hours)),
        intervals_seconds=(np.diff(sequence.times_hours) * 3600).tolist(),
        reference_mjd=float(np.median([m["mjd_avg"] for m in metadata])),
        wavelength_range_um_preview=[float(min(wavelengths)), float(max(wavelengths))],
        velocity_grid_pixels_per_hour=[-8, 8, 1],
        candidates=candidate_records,
        exposures=metadata,
        confirmed_asteroids=0,
        conclusion="Exploratory real-data execution only; candidates are unvalidated.",
        limitations=[
            "WCS registration uses nearest native-pixel PSF statistics, with pixel rounding.",
            "Gaussian sigma=1.2 pixels is provisional; supplied ePSFs are not modeled yet.",
            "Different LVF wavelengths; constant flux across exposures is not verified.",
            "WCS-WAVE values are visualization-grade, not CWAVE/CBAND science calibration.",
            "All flags except SOURCE, and bright pixels, are masked conservatively.",
            "Scores assume independent Gaussian pixel noise, not empirically calibrated.",
            "Group scores are diagnostics after selection, not independent confirmation.",
            "No ephemeris association, completeness or purity measurement.",
        ],
    )
    (output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False))
    np.savez_compressed(
        output / "search.npz",
        maximum_score=best_map,
        zero_motion_score=zero_score,
        stationary=stationary,
        tracked=tracked,
    )
    # View the real first exposure on the same WCS grid (display only).
    ra, dec = reference.pixel_to_world_values(xx, yy)
    px, py = wcs_list[0].world_to_pixel_values(ra, dec)
    ix, iy = np.rint(px).astype(int), np.rint(py).astype(int)
    ix = np.clip(ix, 0, sequence.images.shape[2] - 1)
    iy = np.clip(iy, 0, sequence.images.shape[1] - 1)
    first = np.where(sequence.mask[0, iy, ix], np.nan, sequence.images[0, iy, ix])
    lo, hi = np.nanpercentile(first, [5, 99])
    fig, axes = plt.subplots(1, 3, figsize=(13, 4), layout="constrained")
    for ax, image, title in zip(
        axes,
        [first, stationary, tracked],
        [
            "Exposição real (fundo subtraído)",
            "Empilhamento sem movimento",
            "Trajetória candidata — sem confirmação",
        ],
    ):
        ax.imshow(
            image,
            origin="lower",
            cmap="gray",
            vmin=lo,
            vmax=hi,
            extent=(xx.min() - 0.5, xx.max() + 0.5, yy.min() - 0.5, yy.max() + 0.5),
        )
        ax.set(title=title, xlabel="x na grade de referência [pixel]", ylabel="y [pixel]")
    if best:
        axes[2].plot(best.x, best.y, "o", mfc="none", mec="cyan", ms=16)
    date = Time(metadata[0]["mjd_avg"], format="mjd").isot[:10]
    fig.suptitle(f"SPHEREx DR1 / detector 1 / {date} / {len(metadata)} exposições reais")
    fig.savefig(output / "comparison.png", dpi=160)
    plt.close(fig)
    print(
        json.dumps(
            {
                k: report[k]
                for k in [
                    "n_exposures",
                    "time_span_hours",
                    "wavelength_range_um_preview",
                    "confirmed_asteroids",
                    "conclusion",
                ]
            },
            indent=2,
        )
    )
    return report


if __name__ == "__main__":
    run_real()
