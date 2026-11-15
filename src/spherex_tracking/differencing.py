"""Leave-one-out image differencing with an explicit shared-reference noise model.

This is a constant-scene, common-PSF baseline, not Alard-Lupton or ZOGY.
For linear trajectory template P and weights w=1/V, eliminate the static scene:
  residual = I - sum(w I)/sum(w)
  information = sum(w P²) - sum_pixels(sum_epochs(w P)²/sum_epochs(w)).
The latter accounts for shared-reference covariance and moving-source self-subtraction.
"""

import json
from dataclasses import asdict
from pathlib import Path

import matplotlib
import numpy as np
from astropy.io import fits
from astropy.wcs import WCS

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402

from .core import Sequence, gaussian_psf, search
from .quality import bad_pixel_mask
from .real_data import DEC, RA


def register_real(data_dir="data/spherex", size=96):
    """Nearest-neighbor WCS registration, discarding duplicate native samples.

    Each retained sample in an exposure uses a distinct original detector pixel.
    No interpolation of noisy pixel values; PSF quantization remains a limitation.
    """
    manifest = json.loads((Path(data_dir) / "manifest.json").read_text())
    images, variances, masks, epochs, metadata = [], [], [], [], []
    reference = None
    for record in manifest["files"]:
        with fits.open(record["path"]) as h:
            header = h["IMAGE"].header
            wcs = WCS(header, naxis=2)
            if reference is None:
                reference = wcs
                cx, cy = reference.world_to_pixel_values(RA, DEC)
                yy, xx = np.mgrid[:size, :size].astype(float)
                xx += np.rint(cx) - size // 2
                yy += np.rint(cy) - size // 2
                ra, dec = reference.pixel_to_world_values(xx, yy)
            px, py = wcs.world_to_pixel_values(ra, dec)
            ix, iy = np.rint(px).astype(int), np.rint(py).astype(int)
            native = h["IMAGE"].data
            inside = (ix >= 0) & (iy >= 0) & (ix < native.shape[1]) & (iy < native.shape[0])
            ix, iy = np.clip(ix, 0, native.shape[1] - 1), np.clip(iy, 0, native.shape[0] - 1)
            ids = iy * native.shape[1] + ix
            _, inverse, counts = np.unique(ids, return_inverse=True, return_counts=True)
            duplicate = counts[inverse].reshape(ids.shape) > 1
            image = np.asarray(native[iy, ix] - h["ZODI"].data[iy, ix], float)
            variance = np.asarray(h["VARIANCE"].data[iy, ix], float)
            mask = (
                ~inside
                | duplicate
                | bad_pixel_mask(h["FLAGS"].data[iy, ix])
                | ~np.isfinite(image)
                | ~np.isfinite(variance)
                | (variance <= 0)
            )
            image -= np.median(image[~mask])
            images.append(image)
            variances.append(variance)
            masks.append(mask)
            epochs.append(float(header["MJD-AVG"]))
            metadata.append(
                dict(
                    **record,
                    mjd_avg=epochs[-1],
                    duplicate_sample_fraction=float(np.mean(duplicate)),
                    valid_fraction=float(np.mean(~mask)),
                )
            )
    times = (np.array(epochs) - epochs[0]) * 24
    return Sequence(images, times, variances, masks), metadata


def difference(sequence):
    """References exclude the tested exposure; propagate per-image variances.

    Cross-exposure difference covariances are not stored here. They are accounted
    for algebraically in trajectory_score, never by stacking D/sqrt(VarD).
    """
    weights = 1 / sequence.variance
    total_weight = weights.sum(axis=0)
    total_signal = (weights * sequence.images).sum(axis=0)
    others = total_weight[None] - weights
    valid = (others > 0) & ~sequence.mask
    reference = np.full_like(sequence.images, np.nan)
    np.divide(
        total_signal[None] - weights * sequence.images, others, out=reference, where=others > 0
    )
    variance = np.full_like(reference, np.inf)
    np.divide(1, others, out=variance, where=valid)
    variance += sequence.variance
    differences = np.where(valid, sequence.images - reference, np.nan)
    scene = np.zeros_like(total_weight)
    np.divide(total_signal, total_weight, out=scene, where=total_weight > 0)
    residual = np.where(valid, sequence.images - scene, 0)
    return reference, differences, variance, residual, ~valid


def path_template(sequence, x, y, vx, vy, sigma=1.2):
    """Same rounded paths and truncated PSF as the coarse search."""
    radius = int(np.ceil(4 * sigma))
    kernel = gaussian_psf(sigma)
    template = np.zeros_like(sequence.images)
    for i, t in enumerate(sequence.dt):
        cx, cy = int(round(x)) + int(np.rint(vx * t)), int(round(y)) + int(np.rint(vy * t))
        if (
            cx - radius < 0
            or cy - radius < 0
            or cx + radius >= template.shape[2]
            or cy + radius >= template.shape[1]
        ):
            return None
        template[i, cy - radius : cy + radius + 1, cx - radius : cx + radius + 1] = kernel
    return template


def trajectory_score(sequence, template):
    """Gaussian profile-likelihood score after eliminating the static sky.

    Exact for the supplied diagonal original variances, fixed masks, fixed PSF,
    and an additive static sky with constant source flux. No empirical noise or
    model mismatch is corrected. Zero-motion sources are degenerate with sky.
    """
    weights = 1 / sequence.variance
    total = weights.sum(axis=0)
    p_sum = (weights * template).sum(axis=0)
    p_mean = np.zeros_like(total)
    np.divide(p_sum, total, out=p_mean, where=total > 0)
    centered = template - p_mean
    information = float(np.sum(weights * centered**2))
    original_info = float(np.sum(weights * template**2))
    if information <= max(1e-14, original_info * 1e-12):
        return dict(score=None, flux=None, information=0.0, retained_information_fraction=0.0)
    numerator = float(np.sum(weights * centered * sequence.images))
    return dict(
        score=numerator / np.sqrt(information),
        flux=numerator / information,
        information=information,
        retained_information_fraction=information / original_info,
    )


def detect(sequence, max_proposals=100):
    """Coarse proposals then covariance-aware rescoring (not exhaustive likelihood).

    Proposal statistic uses projected residuals and original variances. Final
    ranking uses trajectory_score. Top-100 truncation can miss slow sources.
    """
    _, _, _, residual, mask = difference(sequence)
    projected = Sequence(residual, sequence.times_hours, sequence.variance, mask)
    proposals = search(
        projected,
        np.arange(-8, 9),
        np.arange(-8, 9),
        sigma=1.2,
        threshold=0,
        max_candidates=max_proposals,
    )
    candidates = []
    for candidate in proposals:
        if np.hypot(candidate.vx, candidate.vy) < 1:
            continue
        template = path_template(sequence, candidate.x, candidate.y, candidate.vx, candidate.vy)
        if template is None:
            continue
        result = trajectory_score(sequence, template)
        if result["score"] is not None:
            record = asdict(candidate)
            record.pop("snr")
            record.update(result)
            candidates.append(record)
    return sorted(candidates, key=lambda c: c["score"], reverse=True)


def inject(sequence, snr=3.0):
    """Artificial constant-flux Gaussian source on the registered REAL backgrounds.

    Choose position by valid-pixel information only; masks fixed before injection.
    This is a favorable-case experiment, not a population completeness estimate.
    """
    best_info, best = -np.inf, None
    for x in range(20, sequence.images.shape[2] - 20, 4):
        for y in range(20, sequence.images.shape[1] - 20, 4):
            template = path_template(sequence, x, y, 3.0, -2.0)
            info = float(np.sum(template**2 / sequence.variance))
            if info > best_info:
                best_info, best = info, (x, y, template)
    x, y, template = best
    noise = np.sqrt(np.median(sequence.variance[np.isfinite(sequence.variance)]))
    flux = snr * noise / np.sqrt(np.sum(gaussian_psf(1.2) ** 2))
    sequence_injected = Sequence(
        sequence.images + flux * template, sequence.times_hours, sequence.variance, sequence.mask
    )
    truth = dict(
        x=float(x),
        y=float(y),
        vx=3.0,
        vy=-2.0,
        flux=float(flux),
        nominal_single_snr=snr,
        expected_single_snrs_after_masks=(
            flux * np.sqrt(np.sum(template**2 / sequence.variance, axis=(1, 2)))
        ).tolist(),
    )
    return sequence_injected, truth, template


def assess(candidates, sequence, truth):
    matches = []
    for rank, c in enumerate(candidates, 1):
        error = float(
            np.max(
                np.hypot(
                    c["x"] - truth["x"] + (c["vx"] - truth["vx"]) * sequence.dt,
                    c["y"] - truth["y"] + (c["vy"] - truth["vy"]) * sequence.dt,
                )
            )
        )
        if error < 2:
            matches.append(dict(rank=rank, max_track_error_pixels=error, **c))
    return dict(
        recovered_among_proposals=bool(matches),
        matched_candidates=matches,
        tolerance_max_track_error_pixels=2,
    )


def robust_rms(values):
    values = values[np.isfinite(values)]
    return float(1.4826 * np.median(np.abs(values - np.median(values))))


def run_difference(output="outputs/differencing", data_dir="data/spherex"):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    sequence, metadata = register_real(data_dir)
    reference, diffs, variances, _, bad = difference(sequence)
    real_candidates = detect(sequence)
    controls = {}
    for snr in [3.0, 5.0]:
        injected, truth, template = inject(sequence, snr)
        candidates = detect(injected)
        base_measurement = trajectory_score(sequence, template)
        measurement = trajectory_score(injected, template)
        expected_increment = truth["flux"] * np.sqrt(measurement["information"])
        controls[str(snr)] = dict(
            truth=truth,
            assessment=assess(candidates, sequence, truth),
            forced_score_before=base_measurement,
            forced_score_after=measurement,
            expected_score_increment=float(expected_increment),
            candidates=candidates[:20],
        )
    normalized = diffs / np.sqrt(variances)
    real_summary = []
    for i in range(len(diffs)):
        valid = ~bad[i]
        real_summary.append(
            dict(
                exposure=i,
                obs_id=metadata[i]["obs_id"],
                valid_fraction=float(np.mean(valid)),
                normalized_residual_robust_rms=robust_rms(normalized[i][valid]),
                n_pixels_abs_nominal_residual_above_5=int(np.sum(np.abs(normalized[i][valid]) > 5)),
            )
        )
    report = dict(
        method="Inverse-variance leave-one-out references + shared-reference covariance scoring",
        implementation="Independent constant-scene baseline; NOT ZOGY/Alard-Lupton/Bramich",
        data="Eight REAL SPHEREx DR1 exposures; controls explicitly injected after registration",
        reference_policy="For exposure i, weighted mean of all other seven exposures",
        n_exposures=len(diffs),
        time_span_hours=float(np.ptp(sequence.times_hours)),
        residual_diagnostics=real_summary,
        candidates=real_candidates[:20],
        controls=controls,
        confirmed_asteroids=0,
        exposures=metadata,
        limitations=[
            "No empirical PSF matching kernel or ePSF fitting; common Gaussian PSF is provisional.",
            "LVF response differences can leave stationary sources in difference images.",
            "Nearest-pixel registration removes duplicates but quantizes PSF and astrometry.",
            "Input detector variances assume independent pixels; real residuals can be correlated.",
            "Final model score accounts for shared references and source self-subtraction.",
            "Only top 100 coarse proposals are rescored; this is not exhaustive likelihood search.",
            "Two favorable injections do not measure completeness, purity or significance.",
            "No external ephemeris confirmation or orbital solution.",
        ],
    )
    (output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False))
    np.savez_compressed(
        output / "differences.npz",
        images=sequence.images,
        references=reference,
        differences=diffs,
        difference_variance=variances,
        masks=bad,
        times_hours=sequence.times_hours,
    )
    # Show one fixed exposure, not an image selected for a prominent residual.
    i = 4
    data = np.where(sequence.mask[i], np.nan, sequence.images[i])
    lo, hi = np.nanpercentile(data, [5, 99])
    scale = max(np.nanpercentile(np.abs(diffs[i]), 98), 1e-10)
    fig, axes = plt.subplots(1, 3, figsize=(13, 4), layout="constrained")
    for ax, image, title, cmap, vmin, vmax in zip(
        axes,
        [data, reference[i], diffs[i]],
        [
            "Exposição real 5 (ZODI subtraído)",
            "Referência: outras sete exposições",
            "Diferença: exposição − referência",
        ],
        ["gray", "gray", "RdBu_r"],
        [lo, lo, -scale],
        [hi, hi, scale],
    ):
        color_map = plt.get_cmap(cmap).copy()
        color_map.set_bad("#777777")
        artist = ax.imshow(image, origin="lower", cmap=color_map, vmin=vmin, vmax=vmax)
        ax.set(title=title, xlabel="x na região registrada [pixel]", ylabel="y [pixel]")
    fig.colorbar(artist, ax=axes[2], label="Resíduo [MJy/sr]")
    fig.suptitle("SPHEREx DR1 — diferenciação de imagens reais, sem injeção")
    fig.savefig(output / "comparison.png", dpi=160)
    plt.close(fig)
    return report


if __name__ == "__main__":
    run_difference()
