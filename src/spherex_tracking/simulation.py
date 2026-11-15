"""Controlled Gaussian-noise experiment, not a SPHEREx instrument simulator."""

from dataclasses import dataclass

import numpy as np

from .core import Sequence, gaussian_psf


@dataclass
class Simulation:
    sequence: Sequence
    truth: dict
    expected_single_snr: np.ndarray
    measured_single_snr: np.ndarray


def _source(shape, x, y, sigma):
    yy, xx = np.indices(shape)
    psf = np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * sigma**2))
    return psf / psf.sum()


def simulate(seed=42, single_snr=2.2, n_frames=32):
    """Inject a constant-flux, untrailed source into stars + sky + Gaussian noise.

    True positions are used for validation only. Search never receives them.
    Set single_snr=0 for a null field with the same stationary stars and masks.
    """
    if n_frames < 2 or not np.isfinite(single_snr) or single_snr < 0:
        raise ValueError("Número de imagens ou SNR de injeção inválido.")
    rng = np.random.default_rng(seed)
    shape, sigma = (64, 64), 1.2
    times = np.linspace(0, 3, n_frames) + rng.uniform(-0.01, 0.01, n_frames)
    times -= times[0]
    dt = times - np.median(times)
    noise = np.linspace(0.8, 1.2, n_frames)
    flux = float(single_snr / np.sqrt(np.sum(gaussian_psf(sigma) ** 2)))
    x0, y0, vx, vy = 30.3, 31.8, 5.3, -2.7
    field = sum(
        300 * _source(shape, x, y, sigma) for x, y in [(14, 14), (50, 49), (15, 48), (50, 15)]
    )
    images, expected, measured = [], [], []
    for t, std in zip(dt, noise):
        psf = _source(shape, x0 + vx * t, y0 + vy * t, sigma)
        # A varying uniform sky is deliberately included for background subtraction.
        sky = 20 + np.sin(t)
        frame = sky + field + flux * psf + rng.normal(0, std, shape)
        images.append(frame)
        expected.append(flux * np.sqrt(np.sum(psf**2)) / std)
        # Forced measurement at the known injected path, not a blind detection.
        measured.append(np.sum(psf * (frame - field - sky)) / (std * np.sqrt((psf**2).sum())))
    mask = np.zeros((n_frames, *shape), dtype=bool)
    # A masked detector artifact tests that a large value does not become a candidate.
    images[2][8, 40] = 1e6
    mask[2, 8, 40] = True
    sequence = Sequence(images, times, noise[:, None, None] ** 2, mask)
    truth = dict(
        x=x0,
        y=y0,
        vx=vx,
        vy=vy,
        flux=flux,
        sigma=sigma,
        reference_time_hours=sequence.reference_time,
    )
    return Simulation(sequence, truth, np.array(expected), np.array(measured))
