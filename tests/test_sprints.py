import numpy as np
import pytest

from spherex_tracking.classification import (
    FEATURES,
    extract_features,
    fit_bounded,
    rank_real,
    write_csv,
)
from spherex_tracking.core import gaussian_psf
from spherex_tracking.moving import (
    cadence_assessment,
    events_from_candidates,
    link_tracks,
    positional_crossmatch,
    velocity_match_tracklets,
)
from spherex_tracking.zogy import zogy_subtract


def test_negative_residual_gets_reference_time_and_duplicates_do_not_add_epochs():
    candidates = [
        dict(
            candidate_id=1,
            source_like_score=0.8,
            science=4,
            reference=0,
            sign=-1,
            pair=0,
            x=20,
            y=30,
        ),
        dict(
            candidate_id=2,
            source_like_score=0.7,
            science=5,
            reference=0,
            sign=-1,
            pair=1,
            x=20,
            y=30,
        ),
        dict(
            candidate_id=3,
            source_like_score=0.7,
            science=4,
            reference=0,
            sign=1,
            pair=0,
            x=24,
            y=28,
        ),
    ]
    events = events_from_candidates(candidates, np.arange(8))
    assert len(events) == 2
    assert events[0]["epoch"] == 0
    assert events[0]["time_hours"] == 0
    assert events[0]["candidate_ids"] == [1, 2]
    assert events[1]["epoch"] == 4


def test_spherical_matching_handles_ra_wrap():
    index, separation, matched = positional_crossmatch(
        np.array([359.9999]), np.array([0.0]), np.array([0.0001]), np.array([0.0]), radius_arcsec=1
    )
    assert index[0] == 0
    assert separation[0] == pytest.approx(0.72)
    assert matched[0]


def test_tracklets_and_velocity_matching_recover_known_motion_with_distractors():
    rng = np.random.default_rng(27)
    times = np.array([0, 0.0358, 0.0716, 0.1074, 1.6, 1.6358, 1.6716, 1.7074])
    reference = np.median(times)
    events = []
    for epoch, t in enumerate(times):
        for x, y in [(40 + 3 * (t - reference), 50 - 2 * (t - reference)), (80, 80)]:
            events.append(
                dict(
                    event_id=len(events),
                    epoch=epoch,
                    time_hours=float(t),
                    x=float(x + rng.normal(0, 0.01)),
                    y=float(y + rng.normal(0, 0.01)),
                    source_like_score=0.8,
                )
            )
        events.append(
            dict(
                event_id=len(events),
                epoch=epoch,
                time_hours=float(t),
                x=float(rng.uniform(5, 100)),
                y=float(rng.uniform(5, 100)),
                source_like_score=0.3,
            )
        )
    first = link_tracks([e for e in events if e["epoch"] < 4], reference)
    second = link_tracks([e for e in events if e["epoch"] >= 4], reference)
    linked = velocity_match_tracklets(first, second, events, reference)
    recovered = [t for t in linked if abs(t["vx"] - 3) < 0.1 and abs(t["vy"] + 2) < 0.1]
    assert recovered
    assert recovered[0]["n_epochs"] == 8
    assert all(len(t["epochs"]) == len(set(t["epochs"])) for t in linked)


def test_cadence_rejects_months_and_accepts_short_sequence():
    assert cadence_assessment([0, 1, 2])["eligible"]
    assert not cadence_assessment([0, 24 * 180, 24 * 360])["eligible"]


def test_features_are_sign_invariant_and_finite():
    image = np.zeros((48, 48))
    psf = gaussian_psf(0.8, 4)
    image[20:29, 20:29] = 50 * psf
    result = zogy_subtract(image, np.zeros_like(image), psf, psf, 1, 1)
    positive = extract_features(result, 24, 24)
    negative_result = dict(result, difference=-result["difference"], scorr=-result["scorr"])
    negative = extract_features(negative_result, 24, 24, sign=-1)
    assert positive is not None
    for key in FEATURES:
        assert np.isfinite(positive[key])
        assert positive[key] == pytest.approx(negative[key])


def test_training_hard_timeout_and_disjoint_spatial_splits(tmp_path):
    rows = []
    for group in range(16):
        for label in [0, 1]:
            rows.append(
                dict(
                    spatial_group=group,
                    label=label,
                    **{feature: float(group + label) for feature in FEATURES},
                )
            )
    result = fit_bounded(rows, tmp_path, timeout=0.00001)
    assert result["status"] == "timeout"
    assert not result["model_used"]
    assert result["wall_seconds"] < 5
    split = result["split"]
    assert not set(split["train_groups"]) & set(split["validation_groups"])
    assert not set(split["train_groups"]) & set(split["test_groups"])
    assert not set(split["validation_groups"]) & set(split["test_groups"])


def test_reranking_preserves_human_review_labels(tmp_path):
    psf = gaussian_psf(0.8, 4)
    image = np.zeros((48, 48))
    image[20:29, 20:29] = 50 * psf
    result = zogy_subtract(image, np.zeros_like(image), psf, psf, 1, 1)
    write_csv(
        tmp_path / "review_labels.csv",
        [
            dict(
                candidate_id=0,
                pair=0,
                x=24,
                y=24,
                human_label="artifact",
                notes="Reviewed manually",
            )
        ],
    )
    report = dict(candidates=[dict(pair=0, x=24, y=24, sign=1, abs_scorr=10)])
    ranked = rank_real(report, [result], dict(status="timeout"), tmp_path)
    assert ranked[0]["human_label"] == "artifact"
    assert ranked[0]["review_notes"] == "Reviewed manually"
    assert ranked[0]["label_status"] == "human-reviewed"
