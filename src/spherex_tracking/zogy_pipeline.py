"""SEP, relative astrometry, calibrated ePSFs, ZOGY, candidates and null tests.

Uses the eight existing SPHEREx cutouts. No Gaia query or external astrometric
solution is claimed: the first calibrated image defines the relative frame.
"""

import importlib.metadata
import json
from pathlib import Path

import matplotlib
import numpy as np
import sep
from astropy.io import fits
from astropy.table import Table
from astropy.wcs import WCS
from scipy.ndimage import map_coordinates
from scipy.spatial import cKDTree
from scipy.stats import beta, norm

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402

from .differencing import robust_rms
from .quality import bad_pixel_mask
from .real_data import DEC, RA
from .zogy import cross_match_psfs, zogy_subtract

PAPER = "https://arxiv.org/abs/1601.02655"
PSF_DOC = "https://caltech-ipac.github.io/irsa-tutorials/spherex-psf/"
FLAGS_DOC = "https://irsa.ipac.caltech.edu/data/SPHEREx/docs/SPHEREx_Expsupp.pdf"


def sep_catalog(image, variance, mask, threshold=4.0):
    image = np.ascontiguousarray(np.where(mask, 0, image), dtype=np.float64)
    background = sep.Background(image, mask=mask, bw=32, bh=32, fw=3, fh=3)
    data = np.ascontiguousarray(image - background.back())
    error = np.ascontiguousarray(np.sqrt(np.where(mask, 1, variance)))
    objects = sep.extract(data, threshold, err=error, mask=mask, minarea=3)
    flux, flux_error, flag = sep.sum_circle(
        data, objects["x"], objects["y"], 3.0, err=error, mask=mask, subpix=5
    )
    catalog = Table(objects)
    catalog["ap_flux"], catalog["ap_flux_error"], catalog["ap_flag"] = flux, flux_error, flag
    return (
        data,
        catalog,
        dict(
            threshold_sigma=threshold,
            n_sources=len(catalog),
            background_rms=float(background.globalrms),
        ),
    )


def usable_sources(catalog):
    good = (
        (catalog["flag"] == 0)
        & (catalog["a"] < 5)
        & (catalog["b"] > 0.3)
        & (catalog["ap_flux"] > 0)
    )
    return catalog[good]


def mutual_matches(reference_xy, other_xy, radius=2.0):
    if not len(reference_xy) or not len(other_xy):
        return np.array([], int), np.array([], int)
    dist, index = cKDTree(other_xy).query(reference_xy)
    _, back = cKDTree(reference_xy).query(other_xy)
    keep = (dist < radius) & (back[index] == np.arange(len(reference_xy)))
    return np.flatnonzero(keep), index[keep]


def translation_fit(reference_xy, other_xy):
    """Translation only, fitted on half the stars and assessed on withheld stars."""
    ri, oi = mutual_matches(reference_xy, other_xy)
    delta = reference_xy[ri] - other_xy[oi]
    default = dict(
        n_matches=len(delta),
        correction_xy=[0.0, 0.0],
        sigma_xy=[0.2, 0.2],
        status="WCS only: insufficient independent centroid matches",
        validated=False,
    )
    if len(delta) < 6:
        return np.zeros(2), default
    center = np.median(delta, axis=0)
    keep = np.linalg.norm(delta - center, axis=1) < max(0.25, 3 * robust_rms(delta - center))
    delta = delta[keep]
    if len(delta) < 6:
        return np.zeros(2), default
    training, validation = delta[::2], delta[1::2]
    shift = np.median(training, axis=0)
    before = float(np.sqrt(np.mean(np.sum(validation**2, axis=1))))
    after = float(np.sqrt(np.mean(np.sum((validation - shift) ** 2, axis=1))))
    applied = np.linalg.norm(shift) < 1 and after <= before
    if not applied:
        shift = np.zeros(2)
        after = before
    sigma = np.maximum(np.sqrt(np.mean((validation - shift) ** 2, axis=0)), 0.02)
    return shift, dict(
        n_matches=len(delta),
        n_training=len(training),
        n_validation=len(validation),
        correction_xy=shift.tolist(),
        heldout_rms_before_pixels=before,
        heldout_rms_after_pixels=after,
        heldout_rms_after_arcsec=after * 6.15,
        sigma_xy=sigma.tolist(),
        status="translation applied" if applied else "WCS retained after check",
        validated=True,
        absolute_astrometry_validated=False,
    )


def epsi_on_grid(frame, reference_wcs, cx, cy, correction):
    """Sample pixel-convolved ePSF; never integrate it a second time.

    Calibrated 5x oversampling is read from the FITS header. One nearest spatial
    zone is used for the central patch; subpixel phase is sampled on this grid.
    """
    grid_y, grid_x = np.mgrid[-4:5, -4:5]
    ra, dec = reference_wcs.pixel_to_world_values(
        cx + grid_x - correction[0], cy + grid_y - correction[1]
    )
    px, py = frame["wcs"].world_to_pixel_values(ra, dec)
    center_x, center_y = px[4, 4], py[4, 4]
    header = frame["header"]
    original_x = 1 + center_x - header["CRPIX1A"]
    original_y = 1 + center_y - header["CRPIX2A"]
    table = frame["epsf_rows"]
    index = int(
        np.argmin((table["XCENTER"] - original_x) ** 2 + (table["YCENTER"] - original_y) ** 2)
    )
    row = table[index]
    oversampled = np.asarray(row["EPSF"], float)
    # Same nearest native samples as the registered images.
    dx, dy = np.rint(px) - center_x, np.rint(py) - center_y
    model = map_coordinates(
        oversampled,
        [
            oversampled.shape[0] // 2 + dy * frame["oversampling"][1],
            oversampled.shape[1] // 2 + dx * frame["oversampling"][0],
        ],
        order=3,
        mode="constant",
        cval=0,
    )
    model = np.maximum(model, 0)
    if model.sum() <= 0:
        raise ValueError("Empty calibrated ePSF.")
    model /= model.sum()
    return model, dict(
        zone_index=index,
        bin_x=int(row["BINX"]),
        bin_y=int(row["BINY"]),
        oversampling=list(frame["oversampling"]),
        wave_um_at_zone=float(row["CWAVE"]),
        bandwidth_um_at_zone=float(row["CBAND"]),
        effective_area_pixels=float(1 / np.sum(model**2)),
        model="Sampled calibrated pixel-convolved ePSF; one spatial zone per image",
    )


def prepare_frames(output, data_dir="data/spherex", size=112):
    manifest = json.loads((Path(data_dir) / "manifest.json").read_text())
    frames, metadata = [], []
    for i, rec in enumerate(manifest["files"]):
        with fits.open(rec["path"]) as h:
            image = np.array(h["IMAGE"].data - h["ZODI"].data, dtype=float)
            variance = np.array(h["VARIANCE"].data, dtype=float)
            flags = h["FLAGS"].data
            mask = (
                bad_pixel_mask(flags)
                | ~np.isfinite(image)
                | ~np.isfinite(variance)
                | (variance <= 0)
            )
            data, catalog, summary = sep_catalog(image, variance, mask)
            catalog.write(output / f"sep_native_{i}.ecsv", overwrite=True)
            frames.append(
                dict(
                    data=data,
                    variance=variance,
                    mask=mask,
                    catalog=catalog,
                    wcs=WCS(h["IMAGE"].header, naxis=2),
                    header=h["IMAGE"].header.copy(),
                    epsf_rows=h["EPSF"].data.copy(),
                    oversampling=(int(h["EPSF"].header["OVSMPX"]), int(h["EPSF"].header["OVSMPY"])),
                )
            )
            metadata.append(
                dict(
                    **rec,
                    exposure=i,
                    mjd_avg=float(h["IMAGE"].header["MJD-AVG"]),
                    sep=summary,
                    source_flag_pixels_preserved=int(
                        np.sum((flags.astype(np.uint32) == (1 << 21)) & ~mask)
                    ),
                )
            )
    reference = frames[0]["wcs"]
    refcat = usable_sources(frames[0]["catalog"])
    refxy = np.column_stack((refcat["x"], refcat["y"]))
    cx, cy = np.rint(reference.world_to_pixel_values(RA, DEC)).astype(float)
    yy, xx = np.mgrid[:size, :size].astype(float)
    xx += cx - size // 2
    yy += cy - size // 2
    aligned, variances, masks, psfs, catalogs = [], [], [], [], []
    for i, frame in enumerate(frames):
        catalog = usable_sources(frame["catalog"])
        ra, dec = frame["wcs"].pixel_to_world_values(catalog["x"], catalog["y"])
        rx, ry = reference.world_to_pixel_values(ra, dec)
        mapped = np.column_stack((rx, ry))
        if i:
            correction, astrometry = translation_fit(refxy, mapped)
        else:
            correction = np.zeros(2)
            astrometry = dict(
                status="reference frame",
                validated=True,
                n_matches=len(refxy),
                correction_xy=[0.0, 0.0],
                sigma_xy=[0.0, 0.0],
                absolute_astrometry_validated=False,
            )
        mapped += correction
        catalogs.append(dict(xy=mapped, flux=np.asarray(catalog["ap_flux"])))
        ra, dec = reference.pixel_to_world_values(xx - correction[0], yy - correction[1])
        px, py = frame["wcs"].world_to_pixel_values(ra, dec)
        ix, iy = np.rint(px).astype(int), np.rint(py).astype(int)
        inside = (
            (ix >= 0) & (iy >= 0) & (ix < frame["data"].shape[1]) & (iy < frame["data"].shape[0])
        )
        ix, iy = (
            np.clip(ix, 0, frame["data"].shape[1] - 1),
            np.clip(iy, 0, frame["data"].shape[0] - 1),
        )
        ids = iy * frame["data"].shape[1] + ix
        _, inverse, counts = np.unique(ids, return_inverse=True, return_counts=True)
        duplicate = counts[inverse].reshape(ids.shape) > 1
        mask = frame["mask"][iy, ix] | ~inside | duplicate
        image = np.where(mask, 0, frame["data"][iy, ix])
        variance = np.where(
            mask, np.median(frame["variance"][~frame["mask"]]), frame["variance"][iy, ix]
        )
        psf, psf_meta = epsi_on_grid(frame, reference, cx, cy, correction)
        aligned.append(image)
        variances.append(variance)
        masks.append(mask)
        psfs.append(psf)
        metadata[i].update(
            astrometry=astrometry, psf=psf_meta, valid_fraction=float(np.mean(~mask))
        )
    return np.array(aligned), np.array(variances), np.array(masks), psfs, catalogs, metadata


def photometric_ratio(new_catalog, reference_catalog):
    ri, ni = mutual_matches(reference_catalog["xy"], new_catalog["xy"], radius=1.0)
    ratios = new_catalog["flux"][ni] / reference_catalog["flux"][ri]
    ratios = ratios[np.isfinite(ratios) & (ratios > 0.1) & (ratios < 10)]
    if len(ratios) < 5:
        return 1.0, dict(
            n_stars=len(ratios),
            ratio=1.0,
            status="unverified unit scale",
            fractional_scatter=None,
            verified=False,
        )
    ratio = float(np.median(ratios))
    scatter = robust_rms(ratios) / ratio
    return ratio, dict(
        n_stars=len(ratios),
        ratio=ratio,
        fractional_scatter=float(scatter),
        fitted=True,
        verified=bool(scatter < 0.15),
        status="median aperture-flux ratio; source colors not modeled",
    )


def signed_candidates(result, pair_id, science, reference, threshold=5.0):
    values = np.ascontiguousarray(result["scorr"], dtype=float)
    mask = np.ascontiguousarray(~result["valid"])
    candidates = []
    for sign in [1, -1]:
        objects = sep.extract(
            np.ascontiguousarray(sign * values), threshold, mask=mask, minarea=1, filter_kernel=None
        )
        for obj in objects:
            x, y = int(obj["xpeak"]), int(obj["ypeak"])
            candidates.append(
                dict(
                    pair=pair_id,
                    science=science,
                    reference=reference,
                    x=x,
                    y=y,
                    sign=sign,
                    abs_scorr=float(sign * values[y, x]),
                    area=int(obj["npix"]),
                    sep_flags=int(obj["flag"]),
                )
            )
    return candidates


def link_dipoles(candidates, times):
    """Exploratory positive/negative temporal consistency, never orbit confirmation."""
    positive = [c for c in candidates if c["sign"] == 1]
    negative = [c for c in candidates if c["sign"] == -1]
    if not positive or not negative:
        return []
    xy = np.array([[c["x"], c["y"]] for c in positive], float)
    dt = np.array([times[c["science"]] for c in positive]) - np.median(times)
    groups = []
    for vx in np.arange(-8, 9, 2):
        for vy in np.arange(-8, 9, 2):
            if vx == vy == 0:
                continue
            projected = xy - dt[:, None] * [vx, vy]
            neighborhoods = cKDTree(projected).query_ball_point(projected, 1.5)
            for i, neighbors in enumerate(neighborhoods):
                epochs = sorted({positive[j]["science"] for j in neighbors})
                if len(epochs) < 3:
                    continue
                supported = set()
                for j in neighbors:
                    c = positive[j]
                    gap = times[c["science"]] - times[c["reference"]]
                    expected = np.array([c["x"] - vx * gap, c["y"] - vy * gap])
                    if any(
                        n["pair"] == c["pair"] and np.linalg.norm(expected - [n["x"], n["y"]]) < 1.5
                        for n in negative
                    ):
                        supported.add(c["science"])
                if len(supported) >= 2:
                    groups.append(
                        dict(
                            x=float(projected[i, 0]),
                            y=float(projected[i, 1]),
                            vx=float(vx),
                            vy=float(vy),
                            n_science_epochs=len(epochs),
                            science_epochs=epochs,
                            negative_supported_epochs=sorted(supported),
                        )
                    )
    groups.sort(
        key=lambda g: (g["n_science_epochs"], len(g["negative_supported_epochs"])), reverse=True
    )
    selected = []
    for group in groups:
        if all(np.linalg.norm([group["x"] - g["x"], group["y"] - g["y"]]) > 2 for g in selected):
            selected.append(group)
        if len(selected) == 10:
            break
    return selected


def run_pipeline(output="outputs/zogy", data_dir="data/spherex", null_trials=128):
    if null_trials < 16:
        raise ValueError("Use at least 16 null trials; default 128.")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    images, variance, masks, psfs, catalogs, metadata = prepare_frames(output, data_dir)
    print("SEP counts:", [m["sep"]["n_sources"] for m in metadata], flush=True)
    times = (np.array([m["mjd_avg"] for m in metadata]) - metadata[0]["mjd_avg"]) * 24
    # Spectral/time tradeoff: long time separation vs. neighboring LVF wavelengths.
    pairs = [(4, 0), (5, 1), (6, 2), (7, 3), (1, 0), (3, 2), (5, 4), (7, 6)]
    results, pair_meta, candidates = [], [], []
    for index, (n, r) in enumerate(pairs):
        ratio, photometry = photometric_ratio(catalogs[n], catalogs[r])
        sigma = np.hypot(
            metadata[n]["astrometry"]["sigma_xy"], metadata[r]["astrometry"]["sigma_xy"]
        )
        result = zogy_subtract(
            images[n],
            images[r],
            psfs[n],
            psfs[r],
            variance[n],
            variance[r],
            flux_scale=ratio,
            mask_new=masks[n],
            mask_reference=masks[r],
            astrometric_sigma_xy=sigma,
        )
        matched = cross_match_psfs(
            images[n], images[r], psfs[n], psfs[r], variance[n], variance[r], ratio
        )
        valid = result["valid"]
        residual_scale = robust_rms(result["scorr"][valid]) if valid.any() else None
        found = signed_candidates(result, index, n, r)
        wave_n, wave_r = (
            metadata[n]["psf"]["wave_um_at_zone"],
            metadata[r]["psf"]["wave_um_at_zone"],
        )
        pair_meta.append(
            dict(
                pair=index,
                science=n,
                reference=r,
                family="long_baseline" if index < 4 else "neighboring_wavelengths",
                gap_hours=float(times[n] - times[r]),
                photometry=photometry,
                astrometric_sigma_xy=sigma.tolist(),
                zone_wave_difference_um=float(abs(wave_n - wave_r)),
                spectral_response_equivalence_verified=False,
                valid_score_pixels=int(valid.sum()),
                scorr_robust_scale=residual_scale,
                common_psf_effective_area=float(1 / np.sum(matched["common_psf"] ** 2)),
                cross_convolution_residual_rms=robust_rms(matched["difference"][valid])
                if valid.any()
                else None,
                positive_candidates=sum(c["sign"] == 1 for c in found),
                negative_candidates=sum(c["sign"] == -1 for c in found),
                calibrated_noise_quality_pass=bool(
                    residual_scale is not None and 0.8 < residual_scale < 1.2
                ),
            )
        )
        result["psf_matched_difference"] = matched["difference"]
        results.append(result)
        candidates.extend(found)
        print(
            "ZOGY pair",
            n,
            r,
            "valid",
            int(valid.sum()),
            "scale",
            residual_scale,
            "candidates",
            len(found),
            flush=True,
        )
    rng = np.random.default_rng(2026)
    maxima = []
    for trial in range(null_trials):
        # Same eight noise realizations reused by their pairs: preserves shared-image dependence.
        noise = rng.normal(size=images.shape) * np.sqrt(variance)
        peaks = []
        for index, (n, r) in enumerate(pairs):
            ratio = pair_meta[index]["photometry"]["ratio"]
            null = zogy_subtract(
                noise[n],
                noise[r],
                psfs[n],
                psfs[r],
                variance[n],
                variance[r],
                flux_scale=ratio,
                mask_new=masks[n],
                mask_reference=masks[r],
            )
            valid = results[index]["valid"]
            if valid.any():
                peaks.append(float(np.max(np.abs(null["scorr"][valid]))))
        maxima.append(max(peaks, default=0.0))
        if (trial + 1) % 32 == 0:
            print("Null trials completed", trial + 1, flush=True)
    n_tests = sum(p["valid_score_pixels"] for p in pair_meta)
    for c in candidates:
        c["bonferroni_p_nominal"] = float(min(1, 2 * n_tests * norm.sf(c["abs_scorr"])))
        c["conditional_null_max_tail_plus_one"] = float(
            (1 + np.sum(np.array(maxima) >= c["abs_scorr"])) / (null_trials + 1)
        )
        c["real_sky_statistically_validated"] = False
    # Artificial moving ePSF source in all eight images. References contain it too.
    injection_results = []
    positions = [(42, 47), (68, 60), (54, 76)]
    for amplitude in [3.0, 5.0, 8.0]:
        for x, y in positions:
            injected = images.copy()
            fluxes, actual_snrs = [], []
            for i, psf in enumerate(psfs):
                px = int(round(x + 3 * times[i]))
                py = int(round(y - 2 * times[i]))
                radius = psf.shape[0] // 2
                scale = amplitude * np.sqrt(np.median(variance[i]) / np.sum(psf**2))
                fluxes.append(float(scale))
                stamp_variance = variance[
                    i, py - radius : py + radius + 1, px - radius : px + radius + 1
                ]
                stamp_mask = masks[i, py - radius : py + radius + 1, px - radius : px + radius + 1]
                actual_snrs.append(
                    float(scale * np.sqrt(np.sum(np.where(stamp_mask, 0, psf**2 / stamp_variance))))
                )
                injected[i, py - radius : py + radius + 1, px - radius : px + radius + 1] += (
                    scale * psf
                )
            per_pair = []
            for index, (n, r) in enumerate(pairs):
                ratio = pair_meta[index]["photometry"]["ratio"]
                added = zogy_subtract(
                    injected[n],
                    injected[r],
                    psfs[n],
                    psfs[r],
                    variance[n],
                    variance[r],
                    flux_scale=ratio,
                    mask_new=masks[n],
                    mask_reference=masks[r],
                    astrometric_sigma_xy=pair_meta[index]["astrometric_sigma_xy"],
                )
                px, py = int(round(x + 3 * times[n])), int(round(y - 2 * times[n]))
                found = signed_candidates(added, index, n, r)
                recovered = any(
                    c["sign"] == 1 and np.hypot(c["x"] - px, c["y"] - py) < 2 for c in found
                )
                preexisting = any(
                    c["pair"] == index and c["sign"] == 1 and np.hypot(c["x"] - px, c["y"] - py) < 2
                    for c in candidates
                )
                valid = bool(added["valid"][py, px])
                per_pair.append(
                    dict(
                        pair=index,
                        center_valid=valid,
                        score_before=float(results[index]["scorr"][py, px]) if valid else None,
                        score_after=float(added["scorr"][py, px]) if valid else None,
                        detected_within_2pixels=recovered,
                        candidate_already_present_before_injection=preexisting,
                        newly_recovered=bool(recovered and not preexisting),
                    )
                )
            injection_results.append(
                dict(
                    nominal_single_frame_snr=amplitude,
                    origin_xy=[x, y],
                    velocity_pixels_hour=[3, -2],
                    position_selection="Three fixed positions chosen before scoring",
                    injected_fluxes=fluxes,
                    expected_single_snrs_after_masks=actual_snrs,
                    per_pair=per_pair,
                )
            )
    exceedances = int(np.sum(np.array(maxima) >= 5))
    interval = [
        0.0
        if not exceedances
        else float(beta.ppf(0.025, exceedances, null_trials - exceedances + 1)),
        1.0
        if exceedances == null_trials
        else float(beta.ppf(0.975, exceedances + 1, null_trials - exceedances)),
    ]
    recovery_summary = []
    for amplitude in [3.0, 5.0, 8.0]:
        subset = [c for c in injection_results if c["nominal_single_frame_snr"] == amplitude]
        recovered = sum(
            any(p["newly_recovered"] and p["pair"] < 4 for p in c["per_pair"]) for c in subset
        )
        recovery_summary.append(
            dict(
                nominal_single_snr=amplitude,
                n_fixed_positions=len(subset),
                newly_detected_in_any_long_baseline_pair=recovered,
                population_completeness_measured=False,
            )
        )
    report = dict(
        method="Independent ZOGY equations 13–17 and 25–30; SEP source extraction",
        references=dict(zogy=PAPER, epsf=PSF_DOC, flags=FLAGS_DOC),
        versions={p: importlib.metadata.version(p) for p in ["numpy", "sep", "astropy", "scipy"]},
        data="Eight REAL SPHEREx DR1 detector 1 cutouts, 2025-10-31",
        source_mask_correction="SOURCE bit 21 preserved; every other nonzero flag rejected",
        exposures=metadata,
        pairs=pair_meta,
        statistical_validation=dict(
            null_trials=null_trials,
            seed=2026,
            conditional_null="Zero-scene Gaussian noise with FITS variances, fixed masks, "
            "PSFs and fitted flux scales. Shared image dependencies preserved. "
            "Does not simulate PSF/color/background/astrometric model error.",
            null_global_maxima=maxima,
            null_global_max_95percent=float(np.quantile(maxima, 0.95)),
            conditional_fwer_at_abs_scorr_5=exceedances / null_trials,
            conditional_fwer_95percent_binomial_interval=interval,
            valid_pixel_tests=n_tests,
            nominal_two_sided_bonferroni_threshold_05=float(norm.isf(0.05 / (2 * n_tests)))
            if n_tests
            else None,
        ),
        n_candidates=len(candidates),
        candidates=candidates,
        exploratory_dipole_track_groups=link_dipoles(candidates, times),
        injections=injection_results,
        injection_summary=recovery_summary,
        confirmed_asteroids=0,
        limitations=[
            "Relative star-based WCS refinement, not independent absolute Gaia astrometry.",
            "One calibrated ePSF zone and representative phase per 112x112 patch.",
            "Nearest-pixel resampling quantizes PSF; duplicate samples discarded.",
            "FFT masks use 1% kernel-energy tolerance and eight-pixel edge exclusion.",
            "Photometric scale is scalar; unequal LVF passbands and source colors remain.",
            "Astrometric correction uses centroid residuals as approximate registration noise.",
            "Gaussian noise null is conditional, not a real-sky false-positive calibration.",
            "Nine injections use ePSFs at constant nominal SNR, without a physical spectrum.",
            "No ephemeris association, orbit solution or discovery claim.",
        ],
    )
    (output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False))
    arrays = dict(images=images, variances=variance, masks=masks, psfs=np.array(psfs))
    for i, result in enumerate(results):
        for name in [
            "difference",
            "score",
            "scorr",
            "score_variance",
            "valid",
            "psf_matched_difference",
        ]:
            arrays[f"pair{i}_{name}"] = result[name]
    np.savez_compressed(output / "products.npz", **arrays)
    fig, axes = plt.subplots(2, 3, figsize=(13, 8), layout="constrained")
    # One long-baseline and one close-wavelength pair, fixed before inspecting scores.
    for row, index in enumerate([0, 4]):
        result = results[index]
        for ax, image, title, bound in zip(
            axes[row],
            [result["psf_matched_difference"], result["difference"], result["scorr"]],
            ["PSF matching: convolução cruzada", "ZOGY: diferença D", "ZOGY: escore S_corr"],
            [None, 5, 5],
        ):
            image = np.where(result["valid"], image, np.nan)
            limit = (
                max(float(np.nanpercentile(np.abs(image), 98)), 1e-6) if bound is None else bound
            )
            cmap = plt.get_cmap("RdBu_r").copy()
            cmap.set_bad("#777777")
            artist = ax.imshow(image, origin="lower", cmap=cmap, vmin=-limit, vmax=limit)
            ax.set(title=f"Par {index}: {title}", xlabel="x [pixel]", ylabel="y [pixel]")
            fig.colorbar(artist, ax=ax, shrink=0.75)
    fig.suptitle("SPHEREx real — fontes preservadas; resíduos não equivalem a asteroides")
    fig.savefig(output / "comparison.png", dpi=150)
    plt.close(fig)
    print("Pipeline completed; candidates", len(candidates), flush=True)
    return report


if __name__ == "__main__":
    run_pipeline()
