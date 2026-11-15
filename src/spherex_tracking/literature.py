"""Reproducible experiments for Gural (2018) and Stetzler et al. (2025).

Gural: independent implementation of equations 1–2, not NASA SALTAD/TGEN.
Stetzler: calls the authors' installed find-asteroids CPU search and MCD refinement.
"""

import contextlib
import importlib.metadata
import io
import json
import time
from pathlib import Path

import matplotlib
import numpy as np
from astropy import units as u
from astropy.constants import au
from astropy.coordinates import get_body_barycentric
from astropy.io import fits
from astropy.table import QTable
from astropy.time import Time
from scipy.ndimage import maximum_filter

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402

from .core import Sequence, _filtered, gaussian_psf
from .real_data import DEC, RA, _load

GURAL = "https://doi.org/10.1088/1538-3873/aac1ff"
STETZLER = "https://arxiv.org/abs/2509.26279v1"


def parallax_template(observer_au, reference_wcs, times_hours, distance_au, ra=RA, dec=DEC):
    """Gural equations 1–2: zero-motion template minus endpoint linear motion.

    Observer vectors must have common inertial equatorial axes and origin.
    Output is referenced to the first exposure and is zero at both endpoints.
    A linear endpoint velocity is added by the search, independently of distance.
    """
    if np.isinf(distance_au):
        return np.zeros((len(times_hours), 2))
    if distance_au <= 0:
        raise ValueError("Distance must be positive.")
    ra, dec = np.deg2rad([ra, dec])
    look = np.array([np.cos(dec) * np.cos(ra), np.cos(dec) * np.sin(ra), np.sin(dec)])
    sight = distance_au * look + observer_au[0] - observer_au
    lon = np.rad2deg(np.arctan2(sight[:, 1], sight[:, 0]))
    lat = np.rad2deg(np.arctan2(sight[:, 2], np.hypot(sight[:, 0], sight[:, 1])))
    x, y = reference_wcs.world_to_pixel_values(lon, lat)
    shift = np.column_stack((x - x[0], y - y[0]))
    fraction = (times_hours - times_hours[0]) / np.ptp(times_hours)
    return shift - fraction[:, None] * shift[-1]


def observer_positions(metadata):
    """Read spacecraft midpoint vectors, add built-in Earth barycentric ephemeris.

    GEOCENTER specifies the origin, but does not fully specify axes in these
    headers. This experiment ASSUMES geocentric inertial equatorial axes aligned
    with ICRS. That assumption must be verified before scientific astrometry.
    """
    positions = []
    for record in metadata:
        with fits.open(record["path"]) as h:
            header = h["IMAGE"].header
            if header["XYZ_SC_SYSTEM"].strip() != "GEOCENTER":
                raise ValueError("Unsupported spacecraft state-vector origin.")
            positions.append([header[k] for k in ["X_SC", "Y_SC", "Z_SC"]])
    epochs = Time([r["mjd_avg"] for r in metadata], format="mjd", scale="utc")
    earth = get_body_barycentric("earth", epochs).xyz.to_value(u.au).T
    return earth + np.array(positions) / au.to_value(u.km)


class NativeSearch:
    """Common scoring for the linear baseline and parallax hypotheses."""

    def __init__(self, sequence, wcs_list, size=96):
        self.sequence, self.wcs_list = sequence, wcs_list
        self.reference = wcs_list[0]
        cx, cy = self.reference.world_to_pixel_values(RA, DEC)
        self.yy, self.xx = np.mgrid[:size, :size].astype(float)
        self.xx += np.rint(cx) - size // 2
        self.yy += np.rint(cy) - size // 2
        self.num, self.den = _filtered(sequence, sigma=1.2)
        self.dt = sequence.times_hours - sequence.times_hours[0]

    def score(self, vx, vy, template):
        num, den = np.zeros_like(self.xx), np.zeros_like(self.xx)
        count = np.zeros_like(self.xx, dtype=int)
        for i, t in enumerate(self.dt):
            ra, dec = self.reference.pixel_to_world_values(
                self.xx + vx * t + template[i, 0], self.yy + vy * t + template[i, 1]
            )
            x, y = self.wcs_list[i].world_to_pixel_values(ra, dec)
            ix, iy = np.rint(x).astype(int), np.rint(y).astype(int)
            good = (ix >= 0) & (iy >= 0) & (ix < self.num.shape[2]) & (iy < self.num.shape[1])
            ix, iy = np.clip(ix, 0, self.num.shape[2] - 1), np.clip(iy, 0, self.num.shape[1] - 1)
            good &= self.den[i, iy, ix] > 0
            num += np.where(good, self.num[i, iy, ix], 0)
            den += np.where(good, self.den[i, iy, ix], 0)
            count += good
        score = np.full_like(num, -np.inf)
        np.divide(num, np.sqrt(den), out=score, where=(den > 0) & (count == len(self.dt)))
        return score

    def search(self, templates, velocities=np.arange(-8, 9)):
        start = time.perf_counter()
        best = None
        maximum = np.full_like(self.xx, -np.inf)
        for distance, template in templates:
            for vx in velocities:
                for vy in velocities:
                    if np.hypot(vx, vy) < 1:
                        continue
                    scores = self.score(vx, vy, template)
                    maximum = np.maximum(maximum, scores)
                    iy, ix = np.unravel_index(np.argmax(scores), scores.shape)
                    value = float(scores[iy, ix])
                    if np.isfinite(value) and (best is None or value > best["score"]):
                        best = dict(
                            x=float(self.xx[iy, ix]),
                            y=float(self.yy[iy, ix]),
                            vx=float(vx),
                            vy=float(vy),
                            score=value,
                            distance_au=None if np.isinf(distance) else float(distance),
                        )
            print("Range completed:", distance, flush=True)
        return dict(
            best=best,
            seconds=time.perf_counter() - start,
            n_templates=len(templates) * (len(velocities) ** 2 - 1),
        ), maximum


def detection_catalog(engine, threshold):
    """Low-SNR local maxima on native PSF-filtered images, transformed to sky."""
    rows = []
    for i, (num, den) in enumerate(zip(engine.num, engine.den)):
        snr = np.full_like(num, -np.inf)
        np.divide(num, np.sqrt(den), out=snr, where=den > 0)
        yy, xx = np.nonzero((snr >= threshold) & (snr == maximum_filter(snr, size=5)))
        ra, dec = engine.wcs_list[i].pixel_to_world_values(xx, yy)
        rx, ry = engine.reference.world_to_pixel_values(ra, dec)
        for j in range(len(xx)):
            if (
                engine.xx.min() <= rx[j] <= engine.xx.max()
                and engine.yy.min() <= ry[j] <= engine.yy.max()
            ):
                rows.append(
                    (ra[j], dec[j], engine.sequence.times_hours[i] / 24, i, snr[yy[j], xx[j]])
                )
    values = np.array(rows).reshape(-1, 5)
    return values


def run_catalog(values, output, label):
    """Execute authors' CPU Hough search + original MCD refinement/gather."""
    from find_asteroids.directions import SearchDirections
    from find_asteroids.postprocess import gather, refine
    from find_asteroids.search import search

    output = Path(output)
    table = QTable()
    table["ra"], table["dec"] = values[:, 0] * u.deg, values[:, 1] * u.deg
    table["time"] = values[:, 2] * u.day
    table["exposure"] = values[:, 3].astype(int)
    table["single_frame_snr"] = values[:, 4]
    table.meta["time_origin"] = "Relative days, arbitrary origin; NOT MJD. Use CPU API."
    table.write(output / f"{label}_catalog.ecsv", overwrite=True)
    if len(values) < 4 or np.ptp(values[:, 2]) == 0:
        return dict(n_peaks=len(values), candidates=[], reason="Insufficient catalog")
    # Equation 16: spacing * temporal baseline must not exceed histogram bin width.
    dx = 6.15 * u.arcsec
    spacing = min(0.04, dx.to_value(u.deg) / np.ptp(values[:, 2]))
    axis = np.arange(-0.36, 0.36 + spacing / 2, spacing)
    a, b = np.meshgrid(axis, axis)
    directions = np.column_stack((a.ravel(), b.ravel()))
    directions = directions[np.linalg.norm(directions, axis=1) >= 0.04]
    hypotheses = SearchDirections(
        None, None, dx, np.ptp(values[:, 2]) * u.day, b=directions * u.deg / u.day
    )
    start = time.perf_counter()
    # Capture upstream verbose output for reproducibility, not in the notebook.
    log = io.StringIO()
    candidates = []
    np.random.seed(42)  # MCD's random subset selection is stochastic.
    with contextlib.redirect_stdout(log):
        results, groups = search(
            values[:, :3],
            hypotheses,
            dx,
            float(values[:, 2].min()),
            num_results=10,
            precompute=False,
            gpu=False,
        )
        for result, points in zip(results, groups):
            if len(points) < 4:
                continue
            model = refine(points)
            if model is None:
                continue
            chosen = gather(model, *values[:, :3].T, dx.to_value(u.deg))
            predicted = model.predict(values[:, 2, None])
            residual = np.linalg.norm(values[:, :2] - predicted, axis=1) * 3600
            epochs = np.unique(values[chosen, 3]).astype(int)
            candidates.append(
                dict(
                    reference_day=float(values[:, 2].min()),
                    ra_at_reference_deg=float(model.predict([[values[:, 2].min()]])[0, 0]),
                    dec_at_reference_deg=float(model.predict([[values[:, 2].min()]])[0, 1]),
                    vra_deg_day=float(model.beta[0, 0]),
                    vdec_deg_day=float(model.beta[0, 1]),
                    raw_hough_votes=int(result[3]),
                    n_gathered=int(chosen.sum()),
                    distinct_exposures=len(epochs),
                    exposure_ids=epochs.tolist(),
                    median_residual_arcsec=float(np.median(residual[chosen]))
                    if chosen.any()
                    else None,
                )
            )
    (output / f"{label}_authors.log").write_text(log.getvalue())
    return dict(
        n_peaks=len(values),
        n_velocity_hypotheses=len(directions),
        velocity_spacing_deg_day=float(spacing),
        seconds_including_jit=time.perf_counter() - start,
        candidates=candidates,
        minimum_distinct_exposures_for_review=4,
        n_candidates_with_four_exposures=sum(c["distinct_exposures"] >= 4 for c in candidates),
    )


def assess_catalog_injection(result, truth, reference_wcs, times_hours):
    """Compare each fitted sky track to injection truth, only after blind search."""
    recovered = False
    for candidate in result["candidates"]:
        days = np.asarray(times_hours) / 24 - candidate["reference_day"]
        ra = candidate["ra_at_reference_deg"] + candidate["vra_deg_day"] * days
        dec = candidate["dec_at_reference_deg"] + candidate["vdec_deg_day"] * days
        x, y = reference_wcs.world_to_pixel_values(ra, dec)
        expected_x = truth["x"] + truth["vx"] * np.asarray(times_hours)
        expected_y = truth["y"] + truth["vy"] * np.asarray(times_hours)
        error = float(np.max(np.hypot(x - expected_x, y - expected_y)))
        candidate["injection_max_track_error_pixels"] = error
        matched = error < 2 and candidate["distinct_exposures"] >= 4
        candidate["matches_injection"] = matched
        recovered |= matched
    result["injected_track_recovered"] = recovered
    return result


def catalog_truth_support(values, truth, reference_wcs):
    """Forced diagnostic of the input catalog, not a blind recovered trajectory."""
    x, y = reference_wcs.world_to_pixel_values(values[:, 0], values[:, 1])
    dt = values[:, 2] * 24
    error = np.hypot(x - truth["x"] - truth["vx"] * dt, y - truth["y"] - truth["vy"] * dt)
    matched = np.unique(values[error < 2, 3]).astype(int)
    return dict(
        radius_pixels=2,
        exposures_with_peak_near_truth=matched.tolist(),
        n_exposures_with_peak_near_truth=len(matched),
    )


def inject_real(sequence, wcs_list, template, flux_snr=3.0):
    """One Gaussian injection on REAL backgrounds; not an astrophysical spectrum model.

    Choose an injection location with low masked-pixel loss (favorable-case test).
    Search receives no truth. Mask is held fixed from the original data.
    """
    engine = NativeSearch(sequence, wcs_list)
    xx, yy = engine.xx, engine.yy
    vx, vy = 3.0, -2.0
    # Favorable position chosen by PSF information, not image signal.
    info = np.zeros_like(xx)
    for i, t in enumerate(engine.dt):
        ra, dec = engine.reference.pixel_to_world_values(
            xx + vx * t + template[i, 0], yy + vy * t + template[i, 1]
        )
        px, py = wcs_list[i].world_to_pixel_values(ra, dec)
        ix, iy = np.rint(px).astype(int), np.rint(py).astype(int)
        inside = (ix >= 0) & (iy >= 0) & (ix < engine.den.shape[2]) & (iy < engine.den.shape[1])
        ix, iy = np.clip(ix, 0, engine.den.shape[2] - 1), np.clip(iy, 0, engine.den.shape[1] - 1)
        info += np.where(inside, engine.den[i, iy, ix], 0)
    border = (
        (xx > xx.min() + 20) & (xx < xx.max() - 20) & (yy > yy.min() + 20) & (yy < yy.max() - 20)
    )
    row, col = np.unravel_index(np.argmax(np.where(border, info, -np.inf)), info.shape)
    x, y = float(xx[row, col]), float(yy[row, col])
    variance = np.median(sequence.variance[np.isfinite(sequence.variance)])
    flux = flux_snr * np.sqrt(variance / np.sum(gaussian_psf(1.2) ** 2))
    images = sequence.images.copy()
    detected_expectation = []
    for i, t in enumerate(engine.dt):
        ra, dec = engine.reference.pixel_to_world_values(
            x + vx * t + template[i, 0], y + vy * t + template[i, 1]
        )
        px, py = wcs_list[i].world_to_pixel_values(ra, dec)
        gy, gx = np.indices(images.shape[1:])
        psf = np.exp(-((gx - px) ** 2 + (gy - py) ** 2) / (2 * 1.2**2))
        psf /= psf.sum()
        images[i] += flux * psf
        detected_expectation.append(float(flux * np.sqrt(np.sum(psf**2 / sequence.variance[i]))))
    return Sequence(images, sequence.times_hours, sequence.variance, sequence.mask), dict(
        x=x,
        y=y,
        vx=vx,
        vy=vy,
        flux=float(flux),
        expected_single_snrs_after_mask=detected_expectation,
        location_selection="Favorable PSF-information position; not a completeness measurement",
    )


def run_literature(output="outputs/literature"):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(Path("data/spherex/manifest.json").read_text())
    sequence, wcs_list, metadata = _load(manifest)
    observers = observer_positions(metadata)
    bend = parallax_template(observers, wcs_list[0], sequence.times_hours, 0.4)
    amplitude = float(np.max(np.linalg.norm(bend, axis=1)))
    # Uniform inverse range gives uniform displacement at small angles, sec. 2.3.
    n_ranges = int(np.ceil(amplitude / 0.5)) + 1
    inverse_ranges = np.linspace(0, 2.5, n_ranges)
    ranges = [np.inf if inv == 0 else 1 / inv for inv in inverse_ranges]
    templates = [
        (r, parallax_template(observers, wcs_list[0], sequence.times_hours, r)) for r in ranges
    ]
    engine = NativeSearch(sequence, wcs_list)
    print("Gural: real exposures, range hypotheses", ranges, flush=True)
    gural_real, map_gural = engine.search(templates)
    print("Linear baseline, same first-epoch grid", flush=True)
    linear_real, map_linear = engine.search(templates[:1])
    injected, truth = inject_real(sequence, wcs_list, templates[-1][1])
    injection_engine = NativeSearch(injected, wcs_list)
    print("Gural: injected source on real backgrounds", flush=True)
    gural_injection, _ = injection_engine.search(templates)
    linear_injection, _ = injection_engine.search(templates[:1])
    for result in [gural_injection, linear_injection]:
        c = result["best"]
        result["best_position_error_pixels"] = float(
            np.hypot(c["x"] - truth["x"], c["y"] - truth["y"])
        )
        result["best_velocity_error_pixels_hour"] = float(
            np.hypot(c["vx"] - truth["vx"], c["vy"] - truth["vy"])
        )
        result["truth_recovered_as_top_candidate"] = (
            result["best_position_error_pixels"] < 2
            and result["best_velocity_error_pixels_hour"] < 2
        )
    catalogs = {}
    for threshold in [2.0, 3.0, 5.0]:
        print("Stetzler: real catalog threshold", threshold, flush=True)
        catalogs[str(threshold)] = run_catalog(
            detection_catalog(engine, threshold), output, f"real_snr{threshold:g}"
        )
    # A linear injection is appropriate to the linear model of Stetzler's paper.
    linear_injected, linear_truth = inject_real(sequence, wcs_list, templates[0][1])
    catalogs["linear_injection_snr2"] = run_catalog(
        detection_catalog(NativeSearch(linear_injected, wcs_list), 2), output, "injection_snr2"
    )
    assess_catalog_injection(
        catalogs["linear_injection_snr2"], linear_truth, wcs_list[0], sequence.times_hours
    )
    catalogs["linear_injection_snr2"]["input_catalog_truth_support"] = catalog_truth_support(
        detection_catalog(NativeSearch(linear_injected, wcs_list), 2), linear_truth, wcs_list[0]
    )
    row, col = int(truth["y"] - engine.yy[0, 0]), int(truth["x"] - engine.xx[0, 0])
    forced_gural = float(
        injection_engine.score(truth["vx"], truth["vy"], templates[-1][1])[row, col]
    )
    forced_linear = float(
        injection_engine.score(truth["vx"], truth["vy"], templates[0][1])[row, col]
    )
    report = dict(
        references=dict(gural=GURAL, stetzler=STETZLER),
        data="Eight real SPHEREx DR1 detector 1 exposures; controls labeled as injected",
        versions={
            p: importlib.metadata.version(p)
            for p in ["find-asteroids", "mcd-regression", "numpy", "astropy"]
        },
        gural=dict(
            implementation="Independent equations 1–2 + inverse-range spacing; not SALTAD/TGEN",
            original_source_status="NASA repository has request forms, no executable source",
            ranges_au=[None if np.isinf(r) else r for r in ranges],
            max_nonlinearity_at_0_4au_pixels=amplitude,
            real=gural_real,
            linear_baseline=linear_real,
            injection_truth=truth,
            injection=gural_injection,
            linear_on_parallax_injection=linear_injection,
            forced_scores_at_injected_path=dict(
                parallax=forced_gural,
                linear=forced_linear,
                note="Known-position diagnostic, not blind recovery",
            ),
        ),
        stetzler=dict(
            implementation="Authors' find-asteroids CPU Hough + MCD refine/gather",
            catalog_extraction="Native Gaussian PSF matched-filter local maxima; thresholds 2,3,5",
            bin_width_arcsec=6.15,
            catalogs=catalogs,
            linear_injection_truth=linear_truth,
        ),
        confirmed_asteroids=0,
        limitations=[
            "Gural observer axes assumed inertial equatorial; GEOCENTER alone does not prove axes.",
            "Built-in Earth ephemeris, no light-time/aberration correction or range-rate bounds.",
            "Gural first-order common template over small field, distances >=0.4au.",
            "Gaussian PSF; LVF spectral differences, backgrounds and noise remain provisional.",
            "Stetzler is linear; noise correlations and repeated epochs can contaminate votes.",
            "Real-background injections have favorable mask coverage and artificial constant flux.",
            "Scores, Hough votes and post-selected candidates are not calibrated significance.",
            "No population completeness, ephemeris confirmation or published speedup reproduction.",
        ],
    )
    (output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False))
    np.savez_compressed(output / "maps.npz", linear=map_linear, parallax=map_gural, template=bend)
    fig, axes = plt.subplots(1, 3, figsize=(14, 4), layout="constrained")
    for ax, image, title in zip(
        axes[:2], [map_linear, map_gural], ["Movimento linear", "Gural: com paralaxe"]
    ):
        artist = ax.imshow(
            np.where(np.isfinite(image), image, np.nan), origin="lower", vmin=0, vmax=12
        )
        ax.set(title=title, xlabel="coluna na região de busca", ylabel="linha")
    fig.colorbar(artist, ax=list(axes[:2]), label="Escore do modelo, sem calibração global")
    axes[2].plot(sequence.times_hours, bend[:, 0], "o-", label="x")
    axes[2].plot(sequence.times_hours, bend[:, 1], "o-", label="y")
    axes[2].set(
        title="Componente não linear a 0,4 au", xlabel="tempo [h]", ylabel="deslocamento [pixel]"
    )
    axes[2].legend()
    fig.savefig(output / "comparison.png", dpi=160)
    plt.close(fig)
    return report


if __name__ == "__main__":
    run_literature()
