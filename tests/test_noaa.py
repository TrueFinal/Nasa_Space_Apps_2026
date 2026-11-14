import pytest

from earth_detectives.core import IngestionError, Store
from earth_detectives.noaa import inspect_classification, inspect_roni


def test_roni_preserves_missing_and_overlapping_seasons(tmp_path):
    p = tmp_path / "roni.txt"
    p.write_text("SEAS YR ANOM\nNDJ 2001 -0.50\nDJF 2002 -99.90\nJFM 2002 0.6\n")
    audit = inspect_roni(p)
    assert audit["missing_values"] == 1
    assert audit["observation_period"] == {"start": "2001-12", "end": "2002-02"}
    assert p.read_text().endswith("JFM 2002 0.6\n")
    assert "phase" not in audit


@pytest.mark.parametrize(
    "content",
    [
        "<html>login</html>",
        "SEAS YR ANOM\nDJF 2000 NaN\n",
        "SEAS YR ANOM\nDJF 2000 1\nDJF 2000 1\n",
        "SEAS YR ANOM\n",
    ],
)
def test_rejects_invalid_roni(tmp_path, content):
    p = tmp_path / "bad.txt"
    p.write_text(content)
    with pytest.raises(IngestionError):
        inspect_roni(p)


def test_rejects_login_page_as_classification(tmp_path):
    p = tmp_path / "bad.html"
    p.write_text("<html>Login</html>")
    with pytest.raises(IngestionError):
        inspect_classification(p)


def test_manifest_detects_corruption_and_saves_timezones(tmp_path):
    store = Store(tmp_path)
    path = tmp_path / "raw.txt"
    path.write_text("original")
    entry = store.record("key", path, {}, {"dataset": "noaa_roni"})
    assert entry["retrieved_at_utc"].endswith("+00:00")
    assert entry["retrieved_at_local"].endswith("-03:00")
    assert store.cached("key")
    path.write_text("modified")
    assert store.cached("key") is None
