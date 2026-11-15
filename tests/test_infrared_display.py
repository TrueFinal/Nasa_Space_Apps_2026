import json

import numpy as np
from astropy.io import fits

from spherex_tracking.infrared import synthetic_manifest
from spherex_tracking.infrared_display import covered, crop_around, trajectory_segments
from spherex_tracking.infrared_mask import run_manifest


def test_plot_stretch_does_not_turn_missing_data_into_bright_sources():
    from spherex_tracking.infrared_display import display_normalization

    values = np.ma.masked_invalid([0.0, np.nan, 1.0])
    result = display_normalization(0, 1)(values)
    assert result.mask.tolist() == [False, True, False]
    assert result[0] == 0
    assert result[2] == 1


def test_footprint_requires_finite_positions_and_available_pixels():
    support = np.ones((40, 70), bool)
    support[12, 10] = False
    assert not covered({"x": 10, "y": 12}, support)
    assert not covered({"x": np.nan, "y": 3}, support)
    assert not covered({"x": 69.5, "y": 20}, support)
    assert covered({"x": -0.4, "y": 20}, support)
    crop = {"x": 10, "y": 10, "w": 20, "h": 20}
    assert not covered({"x": 9, "y": 15}, support, crop)


def test_mpc_crop_stays_in_the_real_image_even_near_edges():
    crop = crop_around([{"x": 2, "y": 3}, {"x": 4, "y": 5}], (50, 70))
    assert crop == {"x": 0, "y": 0, "w": 40, "h": 40}
    crop = crop_around([{"x": 68, "y": 48}], (50, 70))
    assert crop == {"x": 30, "y": 10, "w": 40, "h": 40}


def test_trajectory_breaks_on_missing_coverage_and_distant_epochs():
    support = np.ones((40, 40), bool)
    support[20, 20] = False
    crop = {"x": 0, "y": 0, "w": 40, "h": 40}
    points = [
        {"x": 18, "y": 20, "mjd": 61000},
        {"x": 22, "y": 20, "mjd": 61000.001},
        {"x": 24, "y": 20, "mjd": 61001},
    ]
    assert [len(s) for s in trajectory_segments(points, support, crop, 61000)] == [1, 1]


def test_real_geometry_filters_catalogue_and_does_not_change_measurements(tmp_path):
    manifest = synthetic_manifest(tmp_path / "inputs")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    baseline = run_manifest(manifest, tmp_path / "baseline")
    data["gaia"].append(
        {
            "source_id": "far-away",
            "ra": 0.5,
            "dec": 12.0,
            "pmra": 0,
            "pmdec": 0,
            "phot_g_mean_mag": 10,
        }
    )
    manifest.write_text(json.dumps(data), encoding="utf-8")
    report = run_manifest(manifest, tmp_path / "out")
    for f, old in zip(report["frames"], baseline["frames"]):
        assert f["plot"]["eligible"]
        assert f["plot"]["crop"]["w"] == 40
        assert f["measurement"] == old["measurement"]
        assert all(s["source_id"] != "far-away" for s in f["gaia"])
        assert f["plot"]["counts"]["excluded_from_image"] == 1
        with fits.open(tmp_path / "out" / (f["id"] + ".fits")) as h:
            assert h["IMAGE"].data.shape == (64, 64)  # Plot crop is not a scientific cutout.


def test_gaia_failure_does_not_plot_or_mask_stale_catalogue_records(tmp_path):
    manifest = synthetic_manifest(tmp_path / "inputs")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["gaia_status"] = {"status": "unavailable", "reason": "503"}
    manifest.write_text(json.dumps(data), encoding="utf-8")
    report = run_manifest(manifest, tmp_path / "out")
    assert all(f["gaia"] == [] and f["mask_counts"]["gaia"] == 0 for f in report["frames"])
    assert report["gaia_status"]["status"] == "unavailable"


def test_mpc_position_without_an_available_image_is_excluded_from_plot(tmp_path):
    manifest = synthetic_manifest(tmp_path / "inputs")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    for entry in data["exposures"]:
        entry["target"]["ra"] = (entry["target"]["ra"] + 1) % 360
    manifest.write_text(json.dumps(data), encoding="utf-8")
    report = run_manifest(manifest, tmp_path / "out")
    assert report["plotting"]["frame_ids"] == []
    assert len(report["plotting"]["excluded"]) == 4
    assert all(f["measurement"]["flux_ujy"] is None for f in report["frames"])


def test_image_in_another_band_is_not_plotted_as_the_selected_band(tmp_path):
    manifest = synthetic_manifest(tmp_path / "inputs")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["config"] = {"low_um": 3.35, "high_um": 3.45}
    manifest.write_text(json.dumps(data), encoding="utf-8")
    for path in manifest.parent.glob("*.fits"):
        with fits.open(path, mode="update") as h:
            h["CWAVE"].data[:] = 3.0
    report = run_manifest(manifest, tmp_path / "out")
    assert not report["plotting"]["frame_ids"]
    assert all(
        e["reason"] == "mpc_position_outside_selected_band" for e in report["plotting"]["excluded"]
    )
