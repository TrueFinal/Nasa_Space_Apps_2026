"""Arquivos sintéticos somente para validar integridade e contrato de extração."""

import json
from pathlib import Path

import netCDF4
import numpy as np
import pytest

from earth_detectives import nasa
from earth_detectives.cli import execute, parser, region_config
from earth_detectives.core import IngestionError, Store

REGION = {"id": "test", "bbox": [-48, -16, -47, -15], "crs": "EPSG:4326"}


def synthetic_file(path, *, grouped=False, global_grid=False, all_missing=False):
    with netCDF4.Dataset(path, "w") as root:
        group = root.createGroup("Grid") if grouped else root
        for name, values in {
            "time": [0],
            "lat": [-15.75, -15.25],
            "lon": [-170, 0] if global_grid else [-47.75, -47.25],
        }.items():
            group.createDimension(name, len(values))
            variable = group.createVariable(name, "f8", (name,))
            variable[:] = values
            variable.units = "days since 2015-12-01" if name == "time" else "degrees"
        rain = group.createVariable("precipitation", "f4", ("time", "lat", "lon"), fill_value=-9999)
        rain.units = "mm/day"
        rain[:] = np.full((1, 2, 2), -9999 if all_missing else 1)
        rain[0, 0, 0] = -9999


def test_reads_grouped_product_without_altering_values(tmp_path):
    path = tmp_path / "synthetic.nc4"
    synthetic_file(path, grouped=True)
    before = path.read_bytes()
    audit = nasa.inspect_netcdf(path, ["Grid/precipitation"], REGION)
    assert audit["missing_values"] == 1
    assert audit["temporal_records"] == 1
    assert audit["variables"]["Grid/precipitation"]["units"] == "mm/day"
    assert path.read_bytes() == before


@pytest.mark.parametrize("options", [{"global_grid": True}, {"all_missing": True}])
def test_rejects_global_or_empty_result(tmp_path, options):
    path = tmp_path / "synthetic.nc4"
    synthetic_file(path, **options)
    with pytest.raises(IngestionError):
        nasa.inspect_netcdf(path, ["precipitation"], REGION)


def test_rejects_missing_requested_variable(tmp_path):
    path = tmp_path / "synthetic.nc4"
    synthetic_file(path)
    with pytest.raises(IngestionError, match="ausente"):
        nasa.inspect_netcdf(path, ["RootMoist_inst"], REGION)


def test_polygon_envelope_is_explicit_and_identifiable(tmp_path):
    geometry = {
        "type": "Polygon",
        "coordinates": [
            [
                [-48, -16],
                [-47, -16],
                [-47, -15],
                [-48, -16],
            ]
        ],
    }
    (tmp_path / "region.geojson").write_text(json.dumps(geometry))
    region = region_config(
        "basin",
        {
            "basin": {
                "crs": "EPSG:4326",
                "geometry_file": "region.geojson",
            }
        },
        tmp_path / "regions.yaml",
    )
    assert region["bbox"] == [-48, -16, -47, -15]
    assert region["geometry"] == geometry
    assert region["extraction"] == "polygon_envelope_only"
    assert len(region["geometry_sha256"]) == 64


def test_plan_clamps_to_actual_availability(monkeypatch):
    captured = []

    def query(http, params):
        captured.append(params)
        return [], 2

    monkeypatch.setattr(nasa, "query_granules", query)
    plan = nasa.make_plan(
        "gpm_daily",
        {"product": "GPM_3IMERGDF", "version": "07", "variables": ["precipitation"]},
        {
            "collection_id": "C1",
            "doi": None,
            "available_period": {
                "start": "2000-01-01T00:00:00Z",
                "end": "2025-09-30T23:59:59Z",
            },
        },
        REGION,
        "1990-01-01T00:00:00Z",
        "2026-11-14T00:00:00Z",
        None,
    )
    assert plan["effective_query_period"]["start"].startswith("2000-01-01")
    assert plan["effective_query_period"]["end"].startswith("2025-09-30")
    assert plan["matching_granules"] == 2
    assert captured[0]["bounding_box"] == "-48,-16,-47,-15"


def test_granules_pages_and_detects_catalog_changes(monkeypatch):
    pages = []

    def query(http, params):
        pages.append(params["page_num"])
        return ([{"id": "G1"}] if params["page_num"] == 1 else [{"id": "G2"}]), 2

    monkeypatch.setattr(nasa, "query_granules", query)
    assert len(list(nasa.granules(None, {"cmr_parameters": {}, "matching_granules": 2}))) == 2
    assert pages == [1, 2]
    with pytest.raises(IngestionError, match="Catálogo mudou"):
        list(nasa.granules(None, {"cmr_parameters": {}, "matching_granules": 3}))


def test_dry_run_cannot_submit_or_download(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("dry-run attempted data transfer")

    monkeypatch.setattr("earth_detectives.cli.fetch_noaa", forbidden)
    monkeypatch.setattr("earth_detectives.cli.fetch_nasa", forbidden)
    args = parser().parse_args(["--datasets", "noaa_roni", "--dry-run", "--output", str(tmp_path)])
    assert execute(args) == 0
    assert Store(tmp_path).data["files"] == []
    assert not (tmp_path / "raw").exists()


def test_saved_job_resumes_without_submission_and_preserves_source(tmp_path, monkeypatch):
    source = tmp_path / "synthetic.nc4"
    synthetic_file(source)
    granule = {
        "id": "G1-GES_DISC",
        "time_start": "2015-12-01T00:00:00Z",
        "time_end": "2015-12-01T23:59:59Z",
        "links": [],
    }
    monkeypatch.setattr(nasa, "granules", lambda *_: iter([granule]))
    plan = {
        "dataset": "gpm_daily",
        "matching_granules": 1,
        "collection_id": "C1-GES_DISC",
        "variables_requested": ["precipitation"],
        "region": REGION,
        "effective_query_period": {
            "start": granule["time_start"],
            "end": granule["time_end"],
        },
    }
    store = Store(tmp_path / "data")

    class HTTP:
        submitted = 0
        ready = False

        def json(self, url, **kwargs):
            if "rangeset" in url:
                assert "/collections/parameter_vars/" in url
                assert ("variable", "precipitation") in kwargs["params"]
                assert not any(
                    key == "subset" and value.startswith("time(") for key, value in kwargs["params"]
                )
                self.submitted += 1
                return {"jobID": "aabb-1234", "status": "running"}
            assert kwargs["headers"]["Authorization"] == "Bearer test-secret"
            return {
                "status": "successful" if self.ready else "running",
                "links": [
                    {"rel": "data", "href": "https://example.org/file.nc4?secret=signed"},
                ],
            }

        def download(self, url, path, validator):
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_bytes(source.read_bytes())
            return Path(path), validator(Path(path))

    http = HTTP()
    dataset = {
        "product": "GPM_3IMERGDF",
        "organization": "NASA",
        "spatial_resolution": "0.1",
        "temporal_resolution": "daily",
    }
    with pytest.raises(IngestionError, match="pendente"):
        nasa.fetch_nasa(dataset, plan, http, store, "test-secret", wait_seconds=0)
    assert http.submitted == 1
    http.ready = True
    result = nasa.fetch_nasa(dataset, plan, http, Store(store.root), "test-secret")
    assert len(result) == 1
    assert http.submitted == 1
    saved = store.path.read_text()
    assert "signed" not in saved
    assert "test-secret" not in saved


def test_limit_refuses_large_collection_without_submitting(tmp_path):
    with pytest.raises(IngestionError, match="excedem"):
        nasa.fetch_nasa({}, {"matching_granules": 51}, None, Store(tmp_path), "token")


def test_multiple_variables_use_repeated_parameters():
    params = nasa.harmony_parameters(
        {"region": REGION, "variables_requested": ["U10M", "V10M", "SLP"]}, {"id": "G1"}
    )
    assert [value for key, value in params if key == "variable"] == ["U10M", "V10M", "SLP"]
