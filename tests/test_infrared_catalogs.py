import copy
import json
from datetime import date
from urllib.parse import parse_qs, urlsplit

import pytest
from astropy.io.votable import from_table, writeto
from astropy.table import Table

from spherex_tracking import infrared_archive as archive
from spherex_tracking.infrared import LabState, synthetic_manifest
from spherex_tracking.infrared_catalogs import (
    build_join,
    channel_for,
    channel_grid,
    fetch_wise_context,
    resolve_mpc,
    wise_bands,
)
from spherex_tracking.infrared_mask import MaskConfig, run_manifest


def test_mpc_protocol_provenance_and_cache(tmp_path, monkeypatch):
    calls = []

    class Response:
        url = "https://data.minorplanetcenter.net/api/query-identifier"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, size):
            return json.dumps(
                {"Slipher": {"found": 1, "permid": "1766", "name": "Slipher"}}
            ).encode()

    monkeypatch.setattr(archive, "_open", lambda request: calls.append(request) or Response())
    result = resolve_mpc("Slipher", tmp_path)
    assert result["status"] == "resolved"
    assert result["items"][0]["identifier"] == "1766"
    assert calls[0].method == "GET"
    assert json.loads(calls[0].data) == {"ids": ["Slipher"]}
    assert resolve_mpc("Slipher", tmp_path) == result
    assert len(calls) == 1
    assert result["provenance"]["sha256"]


@pytest.mark.parametrize(
    "found,items,status",
    [(0, [], "not_found"), (2, [{"permid": "1"}, {"permid": "2"}], "ambiguous")],
)
def test_mpc_no_invented_identity_or_silent_disambiguation(
    tmp_path, monkeypatch, found, items, status
):
    import hashlib

    path = tmp_path / (hashlib.sha256(b"name").hexdigest()[:24] + ".json")
    path.write_text(json.dumps({"name": {"found": found, "disambiguation_list": items}}))
    result = resolve_mpc("name", tmp_path)
    assert result["status"] == status
    assert len(result["items"]) == len(items)


def test_channel_grid_selection_uses_official_edges_and_preserves_102_slots():
    grid = channel_grid()
    assert [c["id"] for c in grid["channels"]] == list(range(1, 103))
    assert all(sum(c["detector"] == d for c in grid["channels"]) == 17 for d in range(1, 7))
    assert grid["source_sha256"]
    assert channel_for(3.4, 1) is None
    assert channel_for(None, 4) is None
    assert wise_bands(channel_for(1.0, 1)) == []
    assert wise_bands(channel_for(3.4, 4)) == ["W1"]
    assert wise_bands(channel_for(4.8, 6)) == ["W2"]
    _, _, _, cfg = archive.validate_request({"channel_id": 102})
    assert cfg.detector == 6
    assert cfg.low_um == pytest.approx(grid["channels"][-1]["low_um"])
    for bad in (-1, 103, 1.5):
        with pytest.raises(ValueError, match="canal"):
            archive.validate_request({"channel_id": bad})
    with pytest.raises(ValueError, match="booleano"):
        archive.validate_request({"include_context": "true"})


def test_spatial_spectral_epoch_left_join_preserves_native_data(tmp_path):
    report = run_manifest(synthetic_manifest(tmp_path / "input"), tmp_path / "out")
    before = copy.deepcopy(report["frames"])
    star = report["frames"][0]["gaia"][0]
    mjd = report["frames"][0]["mjd_utc"]
    context = {
        "allwise": {
            "status": "loaded",
            "rows": [
                {
                    "source_id": "inside",
                    "ra": star["ra"],
                    "dec": star["dec"],
                    "coadd_id": "0278p121_ac51",
                    "w1mpro": 12.3,
                    "cc_flags": "0000",
                },
                {"source_id": "outside", "ra": star["ra"] + 1, "dec": star["dec"]},
            ],
        },
        "neowise": {
            "status": "truncated",
            "rows": [
                {"source_id": "coeval", "ra": star["ra"], "dec": star["dec"], "mjd": mjd + 0.5},
                {"source_id": "historic", "ra": star["ra"], "dec": star["dec"], "mjd": mjd - 3000},
            ],
        },
        "images": {
            "status": "loaded",
            "rows": [
                {
                    "band": "W1",
                    "coadd_id": "0278p121_ac51",
                    "base_url": "https://irsa.ipac.caltech.edu/one.fits",
                },
                {
                    "band": "W2",
                    "coadd_id": "0278p121_ac51",
                    "base_url": "https://irsa.ipac.caltech.edu/two.fits",
                },
            ],
        },
    }
    joined = build_join(report, context)
    sample = next(s for s in joined["samples"] if s["kind"] == "gaia")
    assert [c["source_id"] for c in sample["allwise_candidates"]] == ["inside"]
    assert sample["allwise_candidates"][0]["w1mpro"] == 12.3
    assert {r["source_id"]: r["epoch_compatible"] for r in sample["neowise_candidates"]} == {
        "coeval": True,
        "historic": False,
    }
    assert sample["wise_bands"] == ["W1"]
    assert len(sample["wise_images"]) == 1
    assert "center=" in sample["wise_images"][0]["url"]
    assert len(joined["channels"]) == 102
    assert joined["catalogue_status"]["neowise"]["status"] == "truncated"
    assert report["frames"] == before
    assert any(
        not s["allwise_candidates"] for s in joined["samples"]
    )  # Unmatched left rows retained.


def test_coordinate_sia_handles_field_names_distinct_from_ids_and_records_both_releases(
    tmp_path, monkeypatch
):
    table = Table(
        {
            "obs_id": ["2026W30_1B_0022_1"],
            "energy_bandpassname": ["SPHEREx-D5"],
            "t_min": [61241.1],
            "t_max": [61241.2],
            "access_url": ["https://irsa.ipac.caltech.edu/image.fits"],
        }
    )
    votable = from_table(table)
    for i, field in enumerate(votable.get_first_table().fields):
        field.ID = f"col_{i}"
    path = tmp_path / "response.xml"
    writeto(votable, str(path))
    queries = []
    monkeypatch.setattr(
        archive, "download", lambda url, *a: queries.append(parse_qs(urlsplit(url).query)) or path
    )
    rows, provenance = archive.coordinate_candidates(
        {"ra": 359.999, "dec": 12}, date(2026, 7, 20), date(2026, 7, 25), MaskConfig(), tmp_path
    )
    assert len(rows) == len(provenance) == 2
    assert rows[0]["productid"] == "D5"
    assert rows[0]["ra_obj"] == 359.999
    assert {q["COLLECTION"][0] for q in queries} == {"spherex_dr1", "spherex_qr3"}
    assert [float(v) for v in queries[0]["BAND"][0].split()] == pytest.approx([0.75e-6, 5e-6])


def test_wise_failures_are_explicit_and_valid_catalogue_builds_only_official_image_links(
    tmp_path, monkeypatch
):
    path = tmp_path / "allwise.tbl"
    Table(
        {"source_id": ["id"], "coadd_id": ["0278p121_ac51"], "ra": [27.75], "dec": [11.65]}
    ).write(path, format="ascii.ipac")

    def download(url, *args):
        if "neowiser" in url:
            raise OSError("service unavailable")
        return path

    monkeypatch.setattr(archive, "download", download)
    context = fetch_wise_context(27.75, 11.65, tmp_path)
    assert context["neowise"]["status"] == "unavailable"
    assert context["neowise"]["rows"] == []
    assert [r["band"] for r in context["images"]["rows"]] == ["W1", "W2"]
    assert all("/02/0278/0278p121_ac51/" in r["base_url"] for r in context["images"]["rows"])


def test_sample_requests_use_only_trusted_report_coordinates(tmp_path, monkeypatch):
    from spherex_tracking import infrared

    output = tmp_path / "out"
    report = run_manifest(synthetic_manifest(tmp_path / "input"), output)
    state = LabState(output)
    calls = []
    monkeypatch.setattr(infrared, "available_calibrations", lambda _: [4])
    monkeypatch.setattr(state.executor, "submit", lambda *args: calls.append(args))
    sample = report["dataset_join"]["samples"][0]
    try:
        with pytest.raises(ValueError, match="amostra"):
            state.submit({"sample_id": "forged", "detector": 4, "low_um": 3.3, "high_um": 3.5})
        state.submit({"sample_id": sample["id"], "detector": 4, "low_um": 3.3, "high_um": 3.5})
        assert calls[0][3]["ra"] == sample["ra"]
        assert calls[0][3]["dec"] == sample["dec"]
        with pytest.raises(ValueError, match="desconhecido"):
            archive.validate_request({"sample_id": sample["id"], "ra": 1})
    finally:
        state.executor.shutdown()
