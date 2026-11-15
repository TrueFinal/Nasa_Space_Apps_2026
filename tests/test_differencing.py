import numpy as np
import pytest

from spherex_tracking.core import Sequence
from spherex_tracking.differencing import difference, path_template, trajectory_score


def test_reference_excludes_target_and_propagates_noise():
    images = np.full((3, 8, 8), 10.0)
    images[0, 3, 3] += 9
    sequence = Sequence(images, [0, 1, 2], np.array([1, 4, 9])[:, None, None])
    reference, diff, variance, _, _ = difference(sequence)
    assert reference[0, 3, 3] == pytest.approx(10)
    assert diff[0, 3, 3] == pytest.approx(9)
    assert variance[0, 3, 3] == pytest.approx(1 + 1 / (1 / 4 + 1 / 9))
    assert np.allclose(diff[:, 1, 1], 0)
    # A stationary source cannot be distinguished from the fitted static sky.
    assert (
        trajectory_score(sequence, path_template(sequence, 4, 4, 0, 0, sigma=0.5))["score"] is None
    )


def test_projected_score_has_unit_noise_despite_shared_references():
    rng = np.random.default_rng(10)
    times = np.linspace(0, 1.7, 8)
    shape = (8, 40, 40)
    variance = np.linspace(0.6, 2, 8)[:, None, None]
    static_scene = rng.uniform(5, 20, shape[1:])
    empty = Sequence(np.zeros(shape), times, variance)
    template = path_template(empty, 20, 20, 3, -2)
    values = []
    for _ in range(256):
        images = static_scene + rng.normal(size=shape) * np.sqrt(variance)
        sequence = Sequence(images, times, variance)
        values.append(trajectory_score(sequence, template)["score"])
    assert abs(np.mean(values)) < 0.2
    assert 0.85 < np.std(values, ddof=1) < 1.15


def test_moving_signal_survives_and_reference_ghost_is_modeled():
    times = np.linspace(0, 2, 8)
    empty = Sequence(np.zeros((8, 48, 48)), times, 1)
    template = path_template(empty, 24, 24, 3, -2)
    source = Sequence(30 * template, times, 1)
    _, diff, _, _, _ = difference(source)
    assert np.nanmax(diff) > 0
    assert np.nanmin(diff) < 0
    fit = trajectory_score(source, template)
    assert fit["flux"] == pytest.approx(30)
    assert fit["score"] > 5
    assert 0 < fit["retained_information_fraction"] < 1
