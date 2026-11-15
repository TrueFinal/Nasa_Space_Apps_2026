import pytest

pytest.importorskip("xgboost")

from spherex_tracking.classification import FEATURES, fit_bounded
from spherex_tracking.expanded_training import field_split


def test_field_holdout_excludes_repeated_observed_identities():
    rows = []
    for field in range(8):
        for label in [0, 1]:
            rows.append(dict(field_id=field, identity=f"unique:{field}:{label}", label=label))
    rows.extend([dict(field_id=f, identity="same_hardware_pixel", label=0) for f in [0, 5, 6]])
    kept, partitions, excluded = field_split(rows, list(range(8)))
    assert partitions == dict(train=[0, 1, 2, 3, 4], validation=[5], test=[6, 7])
    identities = {
        part: {r["identity"] for r in kept if r["partition"] == part} for part in partitions
    }
    assert identities["train"].isdisjoint(identities["validation"])
    assert identities["train"].isdisjoint(identities["test"])
    assert identities["validation"].isdisjoint(identities["test"])
    assert excluded == 2
    assert [r["sample_id"] for r in kept] == list(range(len(kept)))


def test_explicit_sky_groups_keep_training_timeout(tmp_path):
    rows = []
    for field in range(8):
        for label in [0, 1]:
            rows.append(
                dict(
                    spatial_group=field,
                    label=label,
                    **{name: float(field + label) for name in FEATURES},
                )
            )
    partitions = dict(train=[0, 1, 2, 3, 4], validation=[5], test=[6, 7])
    result = fit_bounded(rows, tmp_path, 0.00001, group_partitions=partitions)
    assert result["status"] == "timeout"
    assert result["split"]["test_groups"] == [6, 7]
    assert result["wall_seconds"] < 5
    with pytest.raises(ValueError, match="disjoint"):
        fit_bounded(rows, tmp_path, group_partitions=dict(train=[0, 1], validation=[1], test=[2]))
