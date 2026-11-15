import numpy as np
import pytest

from spherex_tracking.core import (
    Sequence,
    gaussian_psf,
    prepare,
    refine,
    search,
    stack,
    trajectory_snr,
)
from spherex_tracking.fits_io import inventory
from spherex_tracking.simulation import simulate


def test_blind_recovery_of_subthreshold_source():
    simulation = simulate()
    clean = prepare(simulation.sequence)
    candidates = search(clean, np.arange(-8, 9), np.arange(-5, 6), max_candidates=3)
    assert candidates
    best = max((refine(clean, c, velocity_radius=1) for c in candidates), key=lambda c: c.snr)
    truth = simulation.truth
    assert np.median(simulation.expected_single_snr) < 3
    assert best.snr > 8
    assert np.hypot(best.x - truth["x"], best.y - truth["y"]) < 0.7
    assert np.hypot(best.vx - truth["vx"], best.vy - truth["vy"]) < 0.7
    wrong_snr, _, _ = trajectory_snr(clean, best.x, best.y, -best.vx, -best.vy)
    assert best.snr > wrong_snr + 4


def test_sqrt_n_gain_and_inverse_variance_weights():
    psf = gaussian_psf(1)
    images = np.zeros((9, 25, 25))
    images[:, 8:17, 8:17] = 10 * psf
    variance = np.arange(1, 10)[:, None, None]
    sequence = Sequence(images, np.arange(9), variance)
    snr, flux, count = trajectory_snr(sequence, 12, 12, 0, 0, sigma=1)
    assert flux == pytest.approx(10)
    assert count == 9
    assert snr == pytest.approx(10 * np.sqrt(np.sum(psf**2) * np.sum(1 / variance)))
    equal = Sequence(images, np.arange(9), 1)
    equal_snr, _, _ = trajectory_snr(equal, 12, 12, 0, 0, sigma=1)
    assert equal_snr == pytest.approx(3 * 10 * np.sqrt(np.sum(psf**2)))


def test_stack_sign_edges_coverage_and_masked_artifacts():
    images = np.zeros((3, 9, 9))
    images[np.arange(3), 4, [2, 4, 6]] = 10
    images[0, 0, 0] = 1e8
    mask = np.zeros_like(images, dtype=bool)
    mask[0, 0, 0] = True
    mask[1, 0, 8] = True
    sequence = Sequence(images, [0, 1, 2], 4, mask)
    image, variance, coverage = stack(sequence, 2, 0)
    assert image[4, 4] == pytest.approx(10)
    assert variance[4, 4] == pytest.approx(4 / 3)
    assert coverage[4, 4] == 3
    assert coverage[4, 0] == 2  # No wrap from the opposite border.
    assert np.nanmax(image) == pytest.approx(10)
    empty, var, hits = stack(sequence, 100, 100)
    assert hits[0, 0] == 1
    assert hits[0, 8] == 0
    assert np.isnan(empty[0, 8])
    assert np.isinf(var[0, 8])


def test_coarse_statistic_agrees_with_native_psf_on_integer_track():
    rng = np.random.default_rng(10)
    sequence = Sequence(rng.normal(size=(4, 25, 25)), np.arange(4), 1)
    candidate = search(sequence, [0], [0], sigma=1, threshold=-100, max_candidates=1)[0]
    snr, flux, _ = trajectory_snr(sequence, candidate.x, candidate.y, 0, 0, sigma=1)
    assert snr == pytest.approx(candidate.snr)
    assert flux == pytest.approx(candidate.flux)


def test_invalid_epochs_and_pixels():
    with pytest.raises(ValueError, match="crescentes"):
        Sequence(np.ones((2, 8, 8)), [1, 1], 1)
    images = np.ones((2, 8, 8))
    images[0, 3, 3] = np.nan
    sequence = Sequence(images, [0, 1], 1)
    assert sequence.mask[0, 3, 3]
    assert np.isinf(sequence.variance[0, 3, 3])
    with pytest.raises(ValueError, match="sem pixels"):
        Sequence(images, [0, 1], 0)


def test_null_field_does_not_create_a_high_significance_source():
    null = prepare(simulate(seed=123, single_snr=0).sequence)
    candidates = search(null, np.arange(-8, 9, 2), np.arange(-5, 6, 2), threshold=7)
    assert candidates == []


def test_fits_inventory_keeps_spectral_cube_separate_from_time(tmp_path):
    from astropy.io import fits

    path = tmp_path / "cube.fits"
    image = fits.ImageHDU(np.zeros((102, 4, 4)), name="IMAGE")
    image.header["BUNIT"] = "MJy/sr"
    image.header["CTYPE3"] = "WAVE"
    fits.HDUList([fits.PrimaryHDU(), image]).writeto(path)
    result = inventory(path)
    assert result["hdus"][1]["fits_axes_reversed"] == [102, 4, 4]
    assert result["hdus"][1]["metadata"]["CTYPE3"] == "WAVE"
    assert "times_hours" not in result
