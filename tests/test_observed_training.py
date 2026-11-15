import pytest
from astropy import units as u
from astropy.table import Table
from astropy.time import Time

pytest.importorskip("xgboost")

from spherex_tracking.classification import FEATURES
from spherex_tracking.observed_training import acquire_catalogs, gaia_at_epoch, identity_group


def test_gaia_proper_motion_is_propagated_to_observation_epoch():
    table = Table(dict(ra=[0.0], dec=[0.0], pmra=[1000.0], pmdec=[0.0]))
    table["ra"].unit = table["dec"].unit = u.deg
    result = gaia_at_epoch(table, Time(2026.0, format="jyear").mjd)
    assert result.ra.arcsec[0] == pytest.approx(10, abs=0.001)


def test_identity_groups_stable_and_labels_excluded_from_features():
    assert identity_group("gaia:123") == identity_group("gaia:123")
    assert len({identity_group(f"gaia:{i}") for i in range(100)}) > 12
    assert not any("flag" in f or "id" == f or "label" in f for f in FEATURES)


def test_cached_observed_catalogs_do_not_require_another_remote_query(tmp_path, monkeypatch):
    from astroquery.gaia import Gaia
    from astroquery.ipac.irsa import Irsa

    Table(dict(source_id=[123], ra=[1.0])).write(tmp_path / "gaia_dr3.ecsv")
    Table(dict(obs_id=["observed"])).write(tmp_path / "spherex_astroquery.ecsv")

    def unexpected(*args, **kwargs):
        raise AssertionError("Cache should prevent a remote query")

    monkeypatch.setattr(Gaia, "launch_job", unexpected)
    monkeypatch.setattr(Irsa, "query_sia", unexpected)
    gaia, spherex = acquire_catalogs(tmp_path)
    assert len(gaia) == len(spherex) == 1
    assert (tmp_path / "gaia_query.adql").exists()
