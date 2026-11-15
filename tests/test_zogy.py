import numpy as np
import pytest
from scipy.signal import fftconvolve

from spherex_tracking.core import gaussian_psf
from spherex_tracking.quality import bad_pixel_mask
from spherex_tracking.zogy import cross_match_psfs, zogy_subtract
from spherex_tracking.zogy_pipeline import translation_fit


def test_source_flag_is_not_a_bad_pixel():
    flags = np.array([0, 1 << 21, 1 << 6, (1 << 21) | (1 << 17)], dtype=np.int32)
    assert bad_pixel_mask(flags).tolist() == [False, False, True, True]


def test_astrometric_translation_on_withheld_stars():
    rng = np.random.default_rng(8)
    ref = rng.uniform(5, 95, (30, 2))
    actual = np.array([0.35, -0.2])
    other = ref - actual + rng.normal(0, 0.02, ref.shape)
    fitted, report = translation_fit(ref, other)
    assert np.linalg.norm(fitted - actual) < 0.03
    assert report["n_validation"] >= 10
    assert report["heldout_rms_after_pixels"] < report["heldout_rms_before_pixels"] / 5


def test_psf_matching_and_zogy_cancel_static_sources_with_different_psfs():
    scene = np.zeros((64, 64))
    scene[20, 20], scene[40, 43] = 100, 300
    pn, pr = gaussian_psf(0.8, 4), gaussian_psf(1.2, 4)
    new = 1.7 * fftconvolve(scene, pn, mode="same")
    ref = fftconvolve(scene, pr, mode="same")
    matched = cross_match_psfs(new, ref, pn, pr, np.ones_like(new), np.ones_like(ref), 1.7)
    assert np.max(np.abs(matched["difference"])) < 1e-12
    result = zogy_subtract(new, ref, pn, pr, 1, 1, flux_scale=1.7, pad=0)
    assert np.max(np.abs(result["difference"])) < 1e-11
    assert result["psf_difference"].sum() == pytest.approx(1)


def test_equal_psf_reduces_to_normalized_difference_and_swaps_sign():
    rng = np.random.default_rng(7)
    new, ref = rng.normal(size=(2, 48, 48))
    psf = gaussian_psf(0.6, 4)
    result = zogy_subtract(new, ref, psf, psf, 2.0, 3.0, pad=0)
    assert np.allclose(result["difference"], (new - ref) / np.sqrt(5), atol=1e-8)
    reversed_result = zogy_subtract(ref, new, psf, psf, 3.0, 2.0, pad=0)
    assert np.allclose(result["scorr"], -reversed_result["scorr"], atol=1e-9)


def test_scorr_noise_calibration_with_heterogeneous_variance_and_transient():
    rng = np.random.default_rng(17)
    shape = (48, 48)
    pn, pr = gaussian_psf(0.7, 4), gaussian_psf(1.1, 4)
    vn = np.broadcast_to(np.linspace(0.6, 1.5, 48), shape).copy()
    vr = np.ones(shape) * 1.3
    samples = []
    for _ in range(128):
        new, ref = rng.normal(size=(2, *shape)) * np.sqrt([vn, vr])
        result = zogy_subtract(new, ref, pn, pr, vn, vr, pad=0)
        samples.append(result["scorr"][24, 24])
    assert abs(np.mean(samples)) < 0.25
    assert 0.8 < np.std(samples, ddof=1) < 1.2
    new = np.zeros(shape)
    new[20:29, 20:29] = 80 * pn
    result = zogy_subtract(new, np.zeros(shape), pn, pr, vn, vr, pad=0)
    assert result["scorr"][24, 24] > 10
    assert np.unravel_index(np.argmax(result["scorr"]), shape) == (24, 24)
