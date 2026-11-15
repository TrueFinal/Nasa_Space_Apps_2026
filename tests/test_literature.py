import numpy as np
import pytest
from astropy.wcs import WCS

from spherex_tracking.literature import parallax_template


def test_parallax_template_matches_independent_moving_body_projection():
    wcs = WCS(naxis=2)
    wcs.wcs.crpix = [100, 100]
    wcs.wcs.crval = [134.6917, 16.0303]
    wcs.wcs.cdelt = [-6.15 / 3600, 6.15 / 3600]
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    times = np.array([0, 0.1, 0.25, 1.5, 1.6, 1.7])
    phase = times * 2 * np.pi / 1.6
    observers = 4.5e-5 * np.column_stack((np.cos(phase), np.sin(phase), np.sin(phase) / 3))
    template = parallax_template(observers, wcs, times, 0.8)
    ra, dec = np.deg2rad(wcs.wcs.crval)
    look = np.array([np.cos(dec) * np.cos(ra), np.cos(dec) * np.sin(ra), np.sin(dec)])
    east = np.array([-np.sin(ra), np.cos(ra), 0])
    # Independent 3D moving-body geometry, not a call to the template builder.
    body = 0.8 * look + observers[0] + times[:, None] * east * 3e-5
    sight = body - observers
    lon = np.rad2deg(np.arctan2(sight[:, 1], sight[:, 0]))
    lat = np.rad2deg(np.arctan2(sight[:, 2], np.hypot(sight[:, 0], sight[:, 1])))
    x, y = wcs.world_to_pixel_values(lon, lat)
    path = np.column_stack((x - x[0], y - y[0]))
    curvature = path - (times / times[-1])[:, None] * path[-1]
    assert np.max(np.abs(curvature - template)) < 0.001
    assert np.allclose(template[[0, -1]], 0)
    assert np.allclose(parallax_template(observers, wcs, times, np.inf), 0)


def test_authors_catalog_code_recovers_known_linear_track(tmp_path):
    pytest.importorskip("find_asteroids")
    from spherex_tracking.literature import run_catalog

    rng = np.random.default_rng(2026)
    times = np.linspace(0, 0.1, 24)
    target = np.column_stack((130 + 0.16 * times, 16 + 0.08 * times))
    target += rng.normal(0, 0.1 / 3600, target.shape)
    values = np.column_stack((target, times, np.arange(24), np.full(24, 4)))
    noise = np.column_stack(
        (
            rng.uniform(129.95, 130.05, 150),
            rng.uniform(15.95, 16.05, 150),
            rng.choice(times, 150),
            rng.integers(0, 24, 150),
            np.full(150, 2),
        )
    )
    result = run_catalog(np.vstack((values, noise)), tmp_path, "known")
    recovered = [
        c
        for c in result["candidates"]
        if abs(c["vra_deg_day"] - 0.16) < 0.01 and abs(c["vdec_deg_day"] - 0.08) < 0.01
    ]
    assert recovered
    assert max(c["distinct_exposures"] for c in recovered) >= 20
