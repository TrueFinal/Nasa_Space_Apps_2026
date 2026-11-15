"""Linear motion in a common pixel grid: x=column, y=row, velocity=pixel/hour.

The search uses integer offsets (no interpolation of noisy data). Refinement
evaluates subpixel PSF models on the original pixels, preserving the noise model.
"""

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import binary_dilation, convolve, maximum_filter
from scipy.optimize import minimize


@dataclass
class Sequence:
    """Registered, photometrically comparable exposures with independent pixel noise.

    ``times_hours`` are exposure midpoints relative to a common arbitrary origin.
    ``variance`` is pixel variance, not standard deviation. True mask pixels are bad.
    WCS registration, spectral compatibility and instrument calibration are caller duties.
    """

    images: np.ndarray
    times_hours: np.ndarray
    variance: np.ndarray
    mask: np.ndarray | None = None

    def __post_init__(self):
        self.images = np.array(self.images, dtype=float, copy=True)
        self.times_hours = np.array(self.times_hours, dtype=float, copy=True)
        if self.images.ndim != 3 or min(self.images.shape) < 1:
            raise ValueError("images deve ter dimensões (épocas, altura, largura).")
        if self.times_hours.shape != (len(self.images),):
            raise ValueError("É necessário um instante por exposição.")
        if len(self.images) < 2 or not np.all(np.isfinite(self.times_hours)):
            raise ValueError("São necessárias pelo menos duas épocas finitas.")
        if np.any(np.diff(self.times_hours) <= 0):
            raise ValueError("As épocas devem ser distintas e estritamente crescentes.")
        self.variance = np.broadcast_to(self.variance, self.images.shape).astype(float).copy()
        bad = ~np.isfinite(self.images) | ~np.isfinite(self.variance) | (self.variance <= 0)
        if self.mask is not None:
            bad |= np.broadcast_to(np.asarray(self.mask, dtype=bool), self.images.shape)
        self.mask = bad
        if np.any(np.all(bad, axis=(1, 2))):
            raise ValueError("Existe uma exposição sem pixels válidos.")
        self.images[bad] = 0
        self.variance[bad] = np.inf

    @property
    def reference_time(self):
        return float(np.median(self.times_hours))

    @property
    def dt(self):
        return self.times_hours - self.reference_time


@dataclass(frozen=True)
class Candidate:
    x: float
    y: float
    vx: float
    vy: float
    snr: float
    flux: float
    n_frames: int


def gaussian_psf(sigma, radius=None):
    if not np.isfinite(sigma) or sigma <= 0:
        raise ValueError("sigma deve ser positivo e finito.")
    radius = int(np.ceil(4 * sigma)) if radius is None else radius
    yy, xx = np.mgrid[-radius : radius + 1, -radius : radius + 1]
    psf = np.exp(-(xx**2 + yy**2) / (2 * sigma**2))
    return psf / psf.sum()


def prepare(sequence, star_sigma=8.0, dilation=3):
    """Subtract scalar sky medians; mask bright stationary sources, never replace noise.

    This simple temporal-median mask can suppress slow movers. It is a prototype,
    not PSF subtraction. A supplied instrument mask is always preserved.
    """
    masked = np.where(sequence.mask, np.nan, sequence.images)
    backgrounds = np.nanmedian(masked, axis=(1, 2))
    residual = masked - backgrounds[:, None, None]
    static = np.ma.median(np.ma.masked_invalid(residual), axis=0).filled(0)
    n_valid = np.sum(~sequence.mask, axis=0)
    variance = np.ma.median(
        np.ma.masked_invalid(np.where(sequence.mask, np.nan, sequence.variance)), axis=0
    ).filled(np.inf)
    # Gaussian median standard error; used only to build the heuristic star mask.
    reference_noise = np.sqrt(np.pi * variance / (2 * np.maximum(n_valid, 1)))
    stars = (static > star_sigma * reference_noise) & (n_valid >= 2)
    if dilation > 0:
        stars = binary_dilation(stars, iterations=dilation)
    return Sequence(residual, sequence.times_hours, sequence.variance, sequence.mask | stars[None])


def _shift_integer(array, dx, dy):
    """Output[y,x] = input[y+dy,x+dx], zero-filled with no wrapping."""
    result = np.zeros_like(array)
    height, width = array.shape
    if abs(dx) >= width or abs(dy) >= height:
        return result
    x0, x1 = max(0, -dx), min(width, width - dx)
    y0, y1 = max(0, -dy), min(height, height - dy)
    result[y0:y1, x0:x1] = array[y0 + dy : y1 + dy, x0 + dx : x1 + dx]
    return result


def _filtered(sequence, sigma):
    psf = gaussian_psf(sigma)
    invvar = 1 / sequence.variance
    num = np.array(
        [convolve(a * w, psf, mode="constant", cval=0) for a, w in zip(sequence.images, invvar)]
    )
    den = np.array([convolve(w, psf**2, mode="constant", cval=0) for w in invvar])
    # Exclude centers whose PSF support would extend outside the exposure.
    radius = psf.shape[0] // 2
    den[:, :radius] = den[:, -radius:] = 0
    den[:, :, :radius] = den[:, :, -radius:] = 0
    return num, den


def _score_maps(num, den, dt, vx, vy, min_frames):
    numerator = np.zeros_like(num[0])
    information = np.zeros_like(den[0])
    coverage = np.zeros_like(den[0], dtype=int)
    for i, t in enumerate(dt):
        dx, dy = int(np.rint(vx * t)), int(np.rint(vy * t))
        n = _shift_integer(num[i], dx, dy)
        d = _shift_integer(den[i], dx, dy)
        good = d > 0
        numerator += np.where(good, n, 0)
        information += d
        coverage += good
    good = (information > 0) & (coverage >= min_frames)
    snr = np.full_like(numerator, -np.inf)
    flux = np.zeros_like(numerator)
    np.divide(numerator, np.sqrt(information), out=snr, where=good)
    np.divide(numerator, information, out=flux, where=good)
    return snr, flux, coverage


def search(
    sequence, vx_grid, vy_grid, sigma=1.2, threshold=5.0, min_fraction=1.0, max_candidates=20
):
    """Blind velocity search with a PSF-weighted Gaussian-noise detection statistic.

    SNR = sum(P D / V) / sqrt(sum(P² / V)); flux is fitted as constant.
    Threshold is per hypothesis, NOT a globally calibrated false-alarm probability.
    Rounding paths to pixels is a coarse approximation; use refine afterwards.
    """
    vx_grid, vy_grid = np.asarray(vx_grid, float), np.asarray(vy_grid, float)
    if (
        vx_grid.ndim != 1
        or vy_grid.ndim != 1
        or not vx_grid.size
        or not vy_grid.size
        or not np.all(np.isfinite(vx_grid))
        or not np.all(np.isfinite(vy_grid))
    ):
        raise ValueError("As grades de velocidades devem ser vetores finitos não vazios.")
    if not 0 < min_fraction <= 1 or max_candidates < 1 or not np.isfinite(threshold):
        raise ValueError("Fração, quantidade de candidatos ou limiar inválidos.")
    num, den = _filtered(sequence, sigma)
    min_frames = int(np.ceil(min_fraction * len(sequence.images)))
    peaks = []
    for vx in vx_grid:
        for vy in vy_grid:
            snr, flux, coverage = _score_maps(num, den, sequence.dt, vx, vy, min_frames)
            local = (snr >= threshold) & (snr == maximum_filter(snr, size=5))
            yy, xx = np.nonzero(local)
            # Bound intermediate memory even on a deliberately low threshold.
            order = np.argsort(snr[yy, xx])[-max_candidates:]
            peaks.extend(
                Candidate(
                    float(xx[j]),
                    float(yy[j]),
                    float(vx),
                    float(vy),
                    float(snr[yy[j], xx[j]]),
                    float(flux[yy[j], xx[j]]),
                    int(coverage[yy[j], xx[j]]),
                )
                for j in order
            )
    peaks.sort(key=lambda c: c.snr, reverse=True)
    selected = []
    for c in peaks:
        # Merge hypotheses only when their predicted tracks remain within 2 pixels.
        duplicate = any(
            np.max(
                np.hypot(
                    c.x - p.x + (c.vx - p.vx) * sequence.dt, c.y - p.y + (c.vy - p.vy) * sequence.dt
                )
            )
            < 2
            for p in selected
        )
        if not duplicate:
            selected.append(c)
        if len(selected) >= max_candidates:
            break
    return selected


def trajectory_snr(sequence, x, y, vx, vy, sigma=1.2):
    """Fit a subpixel Gaussian PSF directly to native pixels along a trajectory.

    Assumes independent Gaussian noise and an untrailed, constant Gaussian PSF.
    No image interpolation, no covariance silently discarded. Returns SNR, flux, count.
    """
    gaussian_psf(sigma)  # Validate sigma consistently with the coarse search.
    radius = int(np.ceil(4 * sigma))
    height, width = sequence.images.shape[1:]
    numerator, information, count = 0.0, 0.0, 0
    for i, t in enumerate(sequence.dt):
        cx, cy = x + vx * t, y + vy * t
        ix, iy = int(np.rint(cx)), int(np.rint(cy))
        if ix - radius < 0 or iy - radius < 0:
            continue
        if ix + radius >= width or iy + radius >= height:
            continue
        ys, xs = slice(iy - radius, iy + radius + 1), slice(ix - radius, ix + radius + 1)
        yy, xx = np.mgrid[ys, xs]
        psf = np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * sigma**2))
        psf /= psf.sum()
        weight = 1 / sequence.variance[i, ys, xs]
        info = float(np.sum(psf**2 * weight))
        if info > 0:
            numerator += float(np.sum(psf * sequence.images[i, ys, xs] * weight))
            information += info
            count += 1
    if information <= 0:
        return -np.inf, 0.0, 0
    return numerator / np.sqrt(information), numerator / information, count


def refine(sequence, candidate, sigma=1.2, velocity_radius=0.5, position_radius=1.5):
    """Local bounded SNR maximization; independent of the simulation's true path.

    This is an engineering alternative to the paper's elongation-driven iteration,
    not an exact reproduction. Candidate morphology remains an external validation.
    """
    if velocity_radius <= 0 or position_radius <= 0:
        raise ValueError("Os raios de refinamento devem ser positivos.")
    initial = np.array([candidate.x, candidate.y, candidate.vx, candidate.vy])
    radii = np.array([position_radius, position_radius, velocity_radius, velocity_radius])

    def objective(params):
        snr, _, count = trajectory_snr(sequence, *params, sigma=sigma)
        return -snr if count >= candidate.n_frames and np.isfinite(snr) else 1e12

    result = minimize(
        objective,
        initial,
        method="Powell",
        bounds=list(zip(initial - radii, initial + radii)),
        options={"xtol": 1e-4, "ftol": 1e-6, "maxiter": 100},
    )
    params = result.x if objective(result.x) <= objective(initial) else initial
    snr, flux, count = trajectory_snr(sequence, *params, sigma=sigma)
    return Candidate(*map(float, params), float(snr), float(flux), count)


def stack(sequence, vx, vy):
    """Inverse-variance mean using rounded shifts; returns image, variance, coverage.

    Primarily a visualization. Candidate statistics come from native-pixel PSF fits.
    Invalid output pixels have NaN intensity and infinite variance.
    """
    numerator = np.zeros_like(sequence.images[0])
    weights = np.zeros_like(numerator)
    coverage = np.zeros_like(numerator, dtype=int)
    for image, variance, t in zip(sequence.images, sequence.variance, sequence.dt):
        dx, dy = int(np.rint(vx * t)), int(np.rint(vy * t))
        weight = _shift_integer(1 / variance, dx, dy)
        numerator += _shift_integer(image / variance, dx, dy)
        weights += weight
        coverage += weight > 0
    mean, variance = np.full_like(weights, np.nan), np.full_like(weights, np.inf)
    np.divide(numerator, weights, out=mean, where=weights > 0)
    np.divide(1, weights, out=variance, where=weights > 0)
    return mean, variance, coverage
