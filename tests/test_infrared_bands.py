import json
import shutil

import pytest
from astropy.io import fits

from spherex_tracking.infrared import synthetic_manifest
from spherex_tracking.infrared_archive import available_calibrations, resolve_calibration
from spherex_tracking.infrared_bands import (
    DETECTOR_BANDS,
    balanced_candidates,
    detectors_for,
    spectral_coverage,
    spread_indices,
)
from spherex_tracking.infrared_mask import run_manifest


def test_full_spectrum_uses_each_actual_detector_and_exports_its_calibration(tmp_path):
    manifest = synthetic_manifest(tmp_path / "input")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    first = data["exposures"][0]
    data["exposures"] = []
    data["gaia"] = []
    for detector, (lo, hi) in DETECTOR_BANDS.items():
        filename = f"detector_{detector}.fits"
        source = manifest.parent / filename
        shutil.copyfile(manifest.parent / first["fits"], source)
        with fits.open(source, mode="update") as h:
            h["IMAGE"].header["DETECTOR"] = detector
            h["CWAVE"].header["DETECTOR"] = detector
            h["CBAND"].header["DETECTOR"] = detector
            h["CWAVE"].data[:] = (lo + hi) / 2
        data["exposures"].append({**first, "fits": filename})
    manifest.write_text(json.dumps(data), encoding="utf-8")
    report = run_manifest(manifest, tmp_path / "out")
    assert report["schema_version"] == 3
    assert {f["detector"] for f in report["frames"]} == set(range(1, 7))
    assert all(c["measurements"] == 1 for c in report["spectral_coverage"])
    for frame in report["frames"]:
        lo, hi = DETECTOR_BANDS[frame["detector"]]
        assert frame["measurement"]["lambda_um"] == pytest.approx((lo + hi) / 2)
        with fits.open(tmp_path / "out" / (frame["id"] + ".fits")) as h:
            assert h["IMAGE"].header["DETECTOR"] == frame["detector"]
    assert "detector,central_wavelength_um" in (tmp_path / "out/measurements.csv").read_text()
    with fits.open(manifest.parent / "detector_2.fits", mode="update") as h:
        h["CWAVE"].header["DETECTOR"] = 4
    with pytest.raises(ValueError, match="outro detector"):
        run_manifest(manifest, tmp_path / "wrong")


def test_sparse_observations_report_gaps_without_interpolation():
    rows = [{"detector": 4, "central_wavelength_um": 3.4, "measurement": {"flux_ujy": None}}]
    bands = spectral_coverage(rows, 0.75, 5)
    assert [b["status"] for b in bands] == [
        "not_observed",
        "not_observed",
        "not_observed",
        "no_accepted_measurement",
        "not_observed",
        "not_observed",
    ]
    assert bands[3]["centres_um"] == [3.4]
    assert detectors_for(3.35, 3.45) == [4]
    assert detectors_for(0.75, 5) == list(range(1, 7))


def test_candidates_balance_detectors_and_keep_shared_observation_identifiers():
    rows = [
        {"productid": f"D{d}", "mjd_start": t, "observation_id": f"obs{t}"}
        for d in range(1, 7)
        for t in range(8)
    ]
    ordered = balanced_candidates(rows, list(range(1, 7)))
    assert [r["productid"] for r in ordered[:6]] == [f"D{d}" for d in range(1, 7)]
    assert [r["mjd_start"] for r in ordered[:12]] == [0] * 6 + [7] * 6
    assert len(ordered) == len(rows)
    assert sorted(spread_indices(17)) == list(range(17))


def test_calibration_directory_never_trusts_a_wrongly_named_detector(tmp_path):
    source = synthetic_manifest(tmp_path / "input").parent / "synthetic_0.fits"
    calibration = tmp_path / "calibration_D1.fits"
    shutil.copyfile(source, calibration)
    assert available_calibrations(tmp_path) == []
    with pytest.raises(ValueError, match="incompatível"):
        resolve_calibration(tmp_path, 1)
    assert resolve_calibration(calibration, 4) == calibration


@pytest.mark.parametrize("detector", range(1, 7))
def test_alternate_wcs_preserves_swir_and_flips_only_mwir(tmp_path, detector):
    import numpy as np

    from spherex_tracking.infrared_mask import spectral_maps

    grid = np.arange(36, dtype=float).reshape(6, 6) + 1
    cal = tmp_path / "cal.fits"
    fits.HDUList(
        [
            fits.PrimaryHDU(),
            fits.ImageHDU(
                grid,
                fits.Header({"BUNIT": "um", "DETCOORD": "detector", "DETECTOR": detector}),
                name="CWAVE",
            ),
            fits.ImageHDU(grid / 100, fits.Header({"BUNIT": "um"}), name="CBAND"),
        ]
    ).writeto(cal)
    header = fits.Header(
        {
            "DETECTOR": detector,
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
    wave, _ = spectral_maps(fits.HDUList([fits.PrimaryHDU()]), header, (2, 2), cal)
    expected = grid[3:5, 2:4]
    np.testing.assert_array_equal(wave, expected[:, ::-1] if detector >= 4 else expected)
