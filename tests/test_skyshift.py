import json

import numpy as np
import pytest

from spherex_tracking import skyshift


@pytest.fixture
def imported(tmp_path, monkeypatch):
    root = tmp_path / "source"
    public = root / "web/public/data"
    (public / "star/frames").mkdir(parents=True)
    raw = np.array([0, 1, 2, 65535], dtype="<u2")
    raw.tofile(public / "star/frames/one.bin")
    skyshift.save(
        public / "star/frames.json",
        {
            "size": [2, 2],
            "clock": "months",
            "center": {"ra": 0, "dec": 0},
            "epochs": [{"data_url": "frames/one.bin", "scale": 0.01, "zero": -0.5}],
        },
    )
    skyshift.save(
        public / "star/object.json",
        {
            "spectrum": [
                {"um": 0.7, "flux_ujy": 2, "saturated": False},
                {"um": 1, "flux_ujy": -1, "saturated": False},
            ],
        },
    )
    skyshift.save(
        public / "candidates.json",
        {
            "candidates": [
                {
                    "id": "moving",
                    "kind": "mover",
                    "ra": 359.9999,
                    "dec": 0,
                    "mjd": 60000,
                    "det": 1,
                    "grade": "B",
                    "frames_url": None,
                },
                {
                    "id": "far",
                    "kind": "spectral",
                    "ra": 100,
                    "dec": 20,
                    "mjd": 60000,
                    "det": 1,
                    "grade": None,
                    "frames_url": None,
                },
            ]
        },
    )
    skyshift.save(public / "distant.json", {"control": {"beyond_chance": False}})
    monkeypatch.setattr(
        skyshift,
        "source_git",
        lambda source, *args: (
            skyshift.REPOSITORY + ".git"
            if args[0] == "remote"
            else ""
            if args[0] == "status"
            else "a" * 40
        ),
    )
    dest = tmp_path / "cache"
    skyshift.import_public_data(root, dest)
    return root, dest


def test_import_decodes_inventory_and_preserves_units_and_missing_pixels(imported):
    _, dest = imported
    data = skyshift.PublicData(dest)
    assert data.manifest["summary"]["no_data_pixels"] == 1
    assert data.manifest["summary"]["pixels"] == 4
    obj = data.object("star")
    assert obj["object"]["spectrum"] == [{"um": 1, "flux_ujy": -1, "saturated": False}]
    assert obj["frames"]["epochs"][0]["data_url"] == "/skyshift-data/star/frames/one.bin"
    assert obj["frames"]["epochs"][0]["zero"] == -0.5


def test_out_of_tree_paths_and_modified_data_are_rejected(imported):
    _, dest = imported
    data = skyshift.PublicData(dest)
    for name in ["../manifest.json", "C:/x", "star\\frames.json"]:
        with pytest.raises(ValueError):
            skyshift.inside(dest, name)
        with pytest.raises(ValueError):
            data.file(name)
    path = dest / "public/star/frames/one.bin"
    path.write_bytes(b"wrong")
    with pytest.raises(ValueError, match="modified"):
        data.file("star/frames/one.bin")


def test_import_rejects_wrong_binary_length_before_publishing_manifest(imported):
    source, dest = imported
    before = (dest / "manifest.json").read_bytes()
    (source / "web/public/data/star/frames/one.bin").write_bytes(b"short")
    with pytest.raises(ValueError, match="tamanho"):
        skyshift.import_public_data(source, dest)
    assert (dest / "manifest.json").read_bytes() == before


def test_context_left_association_handles_ra_wrap_epochs_and_preserves_photometry(imported):
    _, dest = imported
    data = skyshift.PublicData(dest)
    samples = [
        {"id": "near-old", "ra": 0.0001, "dec": 0, "mjd": 60002, "detector": 1},
        {"id": "near-now", "ra": 0.0001, "dec": 0, "mjd": 60000.5, "detector": 2},
        {"id": "no-match", "ra": 60, "dec": -20, "mjd": 60000, "detector": 1},
    ]
    report = {"frames": [{"measurement": {"flux_ujy": -2}}], "dataset_join": {"samples": samples}}
    before = json.dumps(report, sort_keys=True)
    result = data.context(report)
    assert json.dumps(report, sort_keys=True) == before
    assert result["samples_checked"] == 3
    assert [r["sample_id"] for r in result["matches"]] == ["near-old", "near-now"]
    assert result["matches"][0]["separation_arcsec"] == pytest.approx(0.72)
    assert result["matches"][0]["epoch_compatible"] is False
    assert result["matches"][1]["epoch_compatible"] is True
    assert result["matches"][1]["same_detector"] is False
    report["synthetic"] = True
    assert data.context(report)["matches"] == []


def test_spectrum_only_objects_remain_available(imported):
    source, dest = imported
    p = source / "web/public/data/cand/only/object.json"
    skyshift.save(p, {"spectrum": []})
    skyshift.import_public_data(source, dest)
    assert skyshift.PublicData(dest).object("cand/only")["frames"] is None


def test_native_photometry_is_attached_only_to_its_own_manifest_and_source_revision(imported):
    _, dest = imported
    analysis = {
        "commit": "a" * 40,
        "native_photometry": {
            "report_manifest_sha256": "local-one",
            "accepted": 1,
            "rows": [
                {
                    "frame_id": "f1",
                    "fits_sha256": "fits-one",
                    "primary_measurement": {"flux_ujy": 2},
                }
            ],
        },
    }
    skyshift.save(dest / "analysis.json", analysis)
    report = {
        "manifest_sha256": "local-one",
        "dataset_join": {"samples": []},
        "frames": [{"id": "f1", "output_sha256": "fits-one", "measurement": {"flux_ujy": 2}}],
    }
    assert skyshift.enrich_report(report, dest)["skyshift_photometry"]["accepted"] == 1
    report["frames"][0]["output_sha256"] = "changed-fits"
    assert "skyshift_photometry" not in skyshift.enrich_report(report, dest)
    report["frames"][0]["output_sha256"] = "fits-one"
    report["manifest_sha256"] = "other-object"
    assert "skyshift_photometry" not in skyshift.enrich_report(report, dest)
    report["manifest_sha256"] = "local-one"
    analysis["commit"] = "b" * 40
    skyshift.save(dest / "analysis.json", analysis)
    assert "skyshift_photometry" not in skyshift.enrich_report(report, dest)
    assert skyshift.PublicData(dest).summary()["analysis"] is None
