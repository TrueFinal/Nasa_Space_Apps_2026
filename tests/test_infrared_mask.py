import json
import threading
import urllib.error
import urllib.request

import numpy as np
import pytest
from astropy.io import fits
from astropy.time import Time
from astropy.wcs import WCS

from spherex_tracking.infrared import LabState, LocalServer, make_handler, synthetic_manifest
from spherex_tracking.infrared_archive import download, validate_request
from spherex_tracking.infrared_mask import (
    REJECT_BITS,
    MaskConfig,
    _midtime,
    _solid_angles,
    _weights,
    aperture_measure,
    gaia_positions,
    run_manifest,
    sha256,
    spectral_maps,
)


@pytest.fixture
def fixture(tmp_path):
    path = synthetic_manifest(tmp_path / "input")
    data = json.loads(path.read_text(encoding="utf-8"))
    data["gaia"] = []
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_pipeline_preserves_sources_flags_nulls_and_originals(fixture, tmp_path):
    inputs = list(fixture.parent.glob("*.fits"))
    before = {p: sha256(p) for p in inputs}
    report = run_manifest(fixture, tmp_path / "output")
    assert len(report["frames"]) == 4
    assert report["synthetic"]
    f = report["frames"][0]
    m = np.array(f["mask"])
    assert m[31, 29] & 32  # OUTLIER records a real injected source; not rejection.
    assert not (m[31, 29] & REJECT_BITS)
    assert m[6, 10] & 2  # HOT is rejected.
    assert f["masked"][6][10] is None
    assert f["measurement"]["flux_ujy"] > 0
    assert f["measurement"]["coverage"] == 1
    assert f["zodi_subtracted"]
    for p in inputs:
        assert sha256(p) == before[p]
    with fits.open(tmp_path / "output" / "exposure_00.fits", checksum=True) as hdul:
        assert all(h.verify_checksum() == 1 for h in hdul)
        assert np.isnan(hdul["MASKED"].data[6, 10])
        assert hdul["MASK"].data[31, 29] & 64  # informative target bit
        assert hdul["IMAGE"].header["BANDLO"] == 0.75
        assert hdul["IMAGE"].header["BANDHI"] == 5.0
    json.loads(
        (tmp_path / "output" / "report.json").read_text(encoding="utf-8"),
        parse_constant=lambda x: pytest.fail(f"Non-standard JSON {x}"),
    )


def test_native_aperture_flux_and_variance_have_physical_units():
    shape = (40, 40)
    w = WCS(naxis=2)
    w.wcs.crval = [12, -3]
    w.wcs.crpix = [20, 20]
    w.wcs.cdelt = [-6.2 / 3600, 6.2 / 3600]
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    image = np.full(shape, 8.0)
    image[20, 20] += 2
    var = np.full(shape, 0.04)
    mask = np.zeros(shape, np.uint16)
    config = MaskConfig()
    wave, width = np.full(shape, 3.4), np.full(shape, 0.08)
    m = aperture_measure(image, var, mask, wave, width, w, 20, 20, config)
    area = _solid_angles(w, shape)
    assert m["flux_ujy"] == pytest.approx(2 * area[20, 20] * 1e12, rel=1e-8)
    weights = _weights(shape, 20, 20, 2) * area * 1e12
    yy, xx = np.indices(shape)
    n = ((np.hypot(xx - 20, yy - 20) >= 4) & (np.hypot(xx - 20, yy - 20) <= 7)).sum()
    expected = np.sqrt((weights**2 * 0.04).sum() + weights.sum() ** 2 * np.pi / 2 * 0.04 / n)
    assert m["error_ujy"] == pytest.approx(expected)
    assert m["lambda_um"] == pytest.approx(3.4)
    mask[20, 20] |= 2
    blocked = aperture_measure(image, var, mask, wave, width, w, 20, 20, config)
    assert blocked["flux_ujy"] is None
    assert blocked["coverage"] < 1


def test_spectral_map_uses_zero_based_alternate_wcs_and_mwir_flip(tmp_path):
    grid = np.arange(36, dtype=float).reshape(6, 6) + 3
    p = tmp_path / "cal.fits"
    fits.HDUList(
        [
            fits.PrimaryHDU(),
            fits.ImageHDU(
                grid,
                fits.Header({"BUNIT": "um", "DETCOORD": "detector", "DETECTOR": 4}),
                name="CWAVE",
            ),
            fits.ImageHDU(grid / 100, fits.Header({"BUNIT": "um"}), name="CBAND"),
        ]
    ).writeto(p)
    h = fits.Header(
        {
            "DETECTOR": 4,
            "DETCOORD": "sky",
            "CTYPE1A": "LINEAR",
            "CTYPE2A": "LINEAR",
            "CRPIX1A": -1.0,
            "CRPIX2A": -2.0,
            "CRVAL1A": 0.0,
            "CRVAL2A": 0.0,
            "CDELT1A": 1.0,
            "CDELT2A": 1.0,
        }
    )
    wave, width = spectral_maps(fits.HDUList([fits.PrimaryHDU()]), h, (2, 2), p)
    # cutout (0,0) -> detector sky (2,3), then x-flip -> (3,3).
    np.testing.assert_array_equal(wave, grid[3:5, 2:4][:, ::-1])
    np.testing.assert_allclose(width, wave / 100)
    with pytest.raises(ValueError, match="conflita"):
        spectral_maps(fits.HDUList([fits.PrimaryHDU()]), h, (2, 2), p, "sky")


def test_never_uses_spectral_preview_for_science():
    with pytest.raises(ValueError, match="CWAVE"):
        spectral_maps(fits.HDUList([fits.PrimaryHDU()]), fits.Header(), (4, 4))


def test_midpoint_uses_observation_epoch_not_file_date():
    h = fits.Header({"MJD-AVG": 61000.0, "DATE": "2026-11-01"})
    assert _midtime(h).mjd == 61000
    del h["MJD-AVG"]
    with pytest.raises(ValueError, match="época"):
        _midtime(h)
    h.update({"MJD-BEG": 61000.0, "MJD-END": 61000.002})
    assert _midtime(h).mjd == pytest.approx(61000.001)


def test_gaia_motion_wraps_ra_at_observation_epoch():
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [0, 0]
    w.wcs.crpix = [10, 10]
    w.wcs.cdelt = [-0.001, 0.001]
    rows = [{"ra": 359.9999, "dec": 0, "pmra": 1000, "pmdec": 0, "ref_epoch": 2016.0}]
    star = gaia_positions(rows, Time(2026.0, format="jyear"), w)[0]
    assert 0 < star["ra"] < 0.01
    assert star["proper_motion_applied"]


def test_gaia_contamination_blocks_flux(fixture, tmp_path):
    d = json.loads(fixture.read_text(encoding="utf-8"))
    target = d["exposures"][0]["target"]
    d["gaia"] = [{"ra": target["ra"], "dec": target["dec"], "phot_g_mean_mag": 12}]
    fixture.write_text(json.dumps(d), encoding="utf-8")
    report = run_manifest(fixture, tmp_path / "out")
    m = report["frames"][0]["measurement"]
    assert m["status"] == "masked_aperture"
    assert m["flux_ujy"] is None


def test_missing_calibration_and_bad_variance_fail_closed(fixture, tmp_path):
    path = fixture.parent / "synthetic_0.fits"
    with fits.open(path, mode="update") as h:
        h["VARIANCE"].data[31, 29] = -1
    report = run_manifest(fixture, tmp_path / "out")
    assert report["frames"][0]["measurement"]["flux_ujy"] is None
    with fits.open(path, mode="update") as h:
        del h["CWAVE"]
    with pytest.raises(ValueError, match="CWAVE"):
        run_manifest(fixture, tmp_path / "out2")


@pytest.mark.parametrize(
    "args",
    [
        {"low_um": 3.5, "high_um": 3.4},
        {"max_exposures": 73},
        {"detector": 7},
        {"detector": 1, "low_um": 3.35, "high_um": 3.45},
        {"aperture_px": 8},
        {"low_um": float("nan")},
    ],
)
def test_invalid_configuration(args):
    with pytest.raises(ValueError):
        MaskConfig(**args)


def test_bounded_archive_requests():
    for params in (
        {"start": "2026-01-01", "end": "2026-12-31"},
        {"max_exposures": 2.5},
        {"detector": 1.5},
        {"object": ""},
        {"url": "http://localhost"},
    ):
        with pytest.raises(ValueError):
            validate_request(params)
    with pytest.raises(ValueError):
        download("http://localhost/private", "unused")


def test_no_output_overwrites_original(fixture):
    with pytest.raises(ValueError, match="originais"):
        run_manifest(fixture, fixture.parent)


def test_local_api_exposes_report_not_arbitrary_files(fixture, tmp_path, monkeypatch):
    output = tmp_path / "out"
    report = run_manifest(fixture, output)
    from spherex_tracking.infrared_color import render_color_mosaic

    render_color_mosaic(report, output)
    from spherex_tracking import infrared_catalogs

    monkeypatch.setattr(
        infrared_catalogs,
        "resolve_mpc",
        lambda name, cache: {
            "status": "resolved",
            "query": name,
            "items": [{"identifier": "1766"}],
        },
    )
    state = LabState(output)
    server = LocalServer(("127.0.0.1", 0), make_handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urllib.request.urlopen(base + "/api/report") as r:
            assert json.load(r)["synthetic"]
        with urllib.request.urlopen(base + "/api/channels") as r:
            assert len(json.load(r)["channels"]) == 102
        with urllib.request.urlopen(base + "/api/mpc?object=Slipher") as r:
            assert json.load(r)["items"][0]["identifier"] == "1766"
        with urllib.request.urlopen(base + "/files/joined_samples.json") as r:
            assert json.load(r)["samples"]
        with urllib.request.urlopen(base + "/plate.mjs") as r:
            assert r.headers["Content-Type"] == "text/javascript; charset=utf-8"
            assert b"export function cropFor" in r.read()
        with urllib.request.urlopen(base + "/") as r:
            assert b"spherex-canvas" in r.read()
            assert "script-src 'self' 'unsafe-inline'" in r.headers["Content-Security-Policy"]
        with urllib.request.urlopen(base + "/lab") as r:
            assert b'id="detector-view"' in r.read()
            assert "script-src 'self';" in r.headers["Content-Security-Policy"]
        for asset, kind in (
            ("theme.css", "text/css"),
            ("zephyr-logo.svg", "image/svg+xml"),
            ("three.min.js", "text/javascript"),
        ):
            with urllib.request.urlopen(base + "/site-assets/" + asset) as r:
                assert r.headers["Content-Type"].startswith(kind)
        with urllib.request.urlopen(base + "/files/exposure_00.fits") as r:
            assert r.headers["Content-Type"] == "application/fits"
        for name in ("color_mosaic.png", "color_mosaic_rgba.png"):
            with urllib.request.urlopen(base + "/files/" + name + "?v=new-analysis") as r:
                assert r.headers["Content-Type"] == "image/png"
                assert r.read().startswith(b"\x89PNG")
        with urllib.request.urlopen(base + "/files/color_mosaic.json") as r:
            assert json.load(r)["display_only"]
        for path in (
            "/files/../manifest.json",
            "/files/%2e%2e/secrets",
            "/src/infrared.py",
            "/site-assets/%2e%2e/index.html",
        ):
            with pytest.raises(urllib.error.HTTPError) as exc:
                urllib.request.urlopen(base + path)
            assert exc.value.code == 404
        req = urllib.request.Request(
            base + "/api/run", data=b"{}", headers={"Origin": "https://other.example"}
        )
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(req)
        assert exc.value.code == 403
        req = urllib.request.Request(base + "/api/state", headers={"Host": "evil.example"})
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(req)
        assert exc.value.code == 403
    finally:
        server.shutdown()
        server.server_close()
        state.executor.shutdown()


def test_duplicate_exposures_are_not_independent_measurements(fixture, tmp_path):
    data = json.loads(fixture.read_text(encoding="utf-8"))
    data["exposures"][1] = data["exposures"][0]
    fixture.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicadas"):
        run_manifest(fixture, tmp_path / "out")


def test_position_epoch_must_match_exposure(fixture, tmp_path):
    data = json.loads(fixture.read_text(encoding="utf-8"))
    data["exposures"][0]["target"]["mjd"] += 1
    fixture.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="ponto médio"):
        run_manifest(fixture, tmp_path / "out")


def test_gaia_catalogue_keeps_identifiers_and_handles_missing_motion(tmp_path, monkeypatch):
    from astropy.table import MaskedColumn, Table

    from spherex_tracking import infrared_archive as archive

    table = Table(
        {
            "source_id": [1234567890123456789],
            "ra": [28.0],
            "dec": [12.0],
            "ref_epoch": [2016.0],
            "phot_g_mean_mag": [15.0],
        }
    )
    table["pmra"] = MaskedColumn([0.0], mask=[True])
    table["pmdec"] = MaskedColumn([0.0], mask=[True])
    path = tmp_path / "gaia.tbl"
    table.write(path, format="ascii.ipac")
    monkeypatch.setattr(archive, "download", lambda *args: path)
    rows, status = archive.fetch_gaia(28, 12, tmp_path)
    assert status["status"] == "loaded"
    assert rows[0]["source_id"] == "1234567890123456789"
    assert rows[0]["pmra"] is None
    assert status["complete"]


def test_local_server_port_is_exclusive(tmp_path):
    state = LabState(tmp_path)
    server = LocalServer(("127.0.0.1", 0), make_handler(state))
    try:
        with pytest.raises(OSError):
            LocalServer(server.server_address, make_handler(state))
    finally:
        server.server_close()
        state.executor.shutdown()
