"""Position matching, unique-epoch tracklets, velocity matching and stack demos."""

import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord


def positional_crossmatch(ra, dec, catalog_ra, catalog_dec, radius_arcsec=6.15):
    """Spherical nearest-source match; a positional match is not identification."""
    if not len(ra):
        return np.array([], int), np.array([], float), np.array([], bool)
    if not len(catalog_ra):
        return np.full(len(ra), -1), np.full(len(ra), np.inf), np.zeros(len(ra), bool)
    index, sep, _ = SkyCoord(ra * u.deg, dec * u.deg).match_to_catalog_sky(
        SkyCoord(catalog_ra * u.deg, catalog_dec * u.deg)
    )
    return index, sep.arcsec, sep.arcsec <= radius_arcsec


def events_from_candidates(candidates, times_hours, merge_radius=0.75):
    """Negative residual belongs to the reference epoch, positive to science.

    Merge multiple appearances of one position in the same exposure. Repeated
    subtraction pairs never count as independent temporal detections.
    """
    events = []
    for c in sorted(candidates, key=lambda r: r["source_like_score"], reverse=True):
        epoch = int(c["science"] if c["sign"] > 0 else c["reference"])
        existing = next(
            (
                e
                for e in events
                if e["epoch"] == epoch
                and np.hypot(e["x"] - c["x"], e["y"] - c["y"]) <= merge_radius
            ),
            None,
        )
        if existing is not None:
            existing["candidate_ids"].append(c["candidate_id"])
            existing["pairs"].append(c["pair"])
            continue
        events.append(
            dict(
                event_id=len(events),
                epoch=epoch,
                time_hours=float(times_hours[epoch]),
                x=float(c["x"]),
                y=float(c["y"]),
                source_like_score=float(c["source_like_score"]),
                candidate_ids=[c["candidate_id"]],
                pairs=[c["pair"]],
            )
        )
    return events


def fit_track(events, reference_time, tolerance=1.25):
    """Fit a constant velocity; reject outliers and retain only one point/epoch."""
    selected = list(events)
    for _ in range(4):
        if len({e["epoch"] for e in selected}) < 3:
            return None
        times = np.array([e["time_hours"] for e in selected])
        xy = np.array([[e["x"], e["y"]] for e in selected])
        design = np.column_stack((np.ones(len(times)), times - reference_time))
        coefficients = np.linalg.lstsq(design, xy, rcond=None)[0]
        residual = np.linalg.norm(xy - design @ coefficients, axis=1)
        kept = [e for e, r in zip(selected, residual) if r <= tolerance]
        if len(kept) == len(selected):
            break
        selected = kept
    if len({e["epoch"] for e in selected}) < 3 or len({e["epoch"] for e in selected}) != len(
        selected
    ):
        return None
    times = np.array([e["time_hours"] for e in selected])
    xy = np.array([[e["x"], e["y"]] for e in selected])
    design = np.column_stack((np.ones(len(times)), times - reference_time))
    coefficients = np.linalg.lstsq(design, xy, rcond=None)[0]
    errors = np.linalg.norm(xy - design @ coefficients, axis=1)
    if errors.max() > tolerance:
        return None
    vx, vy = coefficients[1]
    baseline = float(np.ptp(times))
    speed = float(np.hypot(vx, vy))
    return dict(
        x=float(coefficients[0, 0]),
        y=float(coefficients[0, 1]),
        vx=float(vx),
        vy=float(vy),
        speed_pixels_hour=speed,
        reference_time_hours=float(reference_time),
        rms_pixels=float(np.sqrt(np.mean(errors**2))),
        baseline_hours=baseline,
        event_ids=[e["event_id"] for e in selected],
        epochs=sorted(e["epoch"] for e in selected),
        n_epochs=len(selected),
        mean_source_like_score=float(np.mean([e["source_like_score"] for e in selected])),
        velocity_tolerance_pixels_hour=float(tolerance / max(baseline, 1e-6)),
        velocity_resolved=bool(speed * baseline >= 2 * tolerance),
    )


def unique_tracks(tracks, max_tracks=30):
    tracks = sorted(
        tracks, key=lambda t: (-t["n_epochs"], t["rms_pixels"], -t["mean_source_like_score"])
    )
    kept, used = [], set()
    for track in tracks:
        ids = set(track["event_ids"])
        if ids & used:
            continue
        kept.append(track)
        used |= ids
        if len(kept) == max_tracks:
            break
    return kept


def link_tracks(
    events,
    reference_time,
    min_epochs=3,
    min_speed=0.0,
    max_speed=12.0,
    seed_baseline=0.03,
    tolerance=1.25,
):
    if len(events) < min_epochs:
        return []
    xy = np.array([[e["x"], e["y"]] for e in events])
    times = np.array([e["time_hours"] for e in events])
    epochs = np.array([e["epoch"] for e in events])
    proposals, seen = [], set()
    for i in range(len(events)):
        for j in range(i + 1, len(events)):
            delta = times[j] - times[i]
            if abs(delta) < seed_baseline or epochs[j] == epochs[i]:
                continue
            velocity = (xy[j] - xy[i]) / delta
            if np.linalg.norm(velocity) > max_speed:
                continue
            distances = np.linalg.norm(
                xy - (xy[i] + (times - times[i])[:, None] * velocity), axis=1
            )
            selected = []
            for epoch in np.unique(epochs):
                indices = np.flatnonzero((epochs == epoch) & (distances <= tolerance))
                if len(indices):
                    k = indices[np.argmin(distances[indices])]
                    selected.append(events[k])
            key = tuple(sorted(e["event_id"] for e in selected))
            if len(selected) < min_epochs or key in seen:
                continue
            seen.add(key)
            track = fit_track(selected, reference_time, tolerance)
            if (
                track
                and min_speed <= track["speed_pixels_hour"] <= max_speed
                and track["n_epochs"] >= min_epochs
            ):
                proposals.append(track)
    return unique_tracks(proposals)


def velocity_match_tracklets(first, second, events, reference_time, tolerance=1.25):
    lookup = {e["event_id"]: e for e in events}
    matches = []
    for a in first:
        for b in second:
            ta = np.mean([lookup[i]["time_hours"] for i in a["event_ids"]])
            tb = np.mean([lookup[i]["time_hours"] for i in b["event_ids"]])
            if tb - ta < 0.3:
                continue
            pa = np.array([a["x"], a["y"]]) + np.array([a["vx"], a["vy"]]) * (ta - reference_time)
            pb = np.array([b["x"], b["y"]]) + np.array([b["vx"], b["vy"]]) * (tb - reference_time)
            between_velocity = (pb - pa) / (tb - ta)
            if not 0.5 <= np.linalg.norm(between_velocity) <= 12:
                continue
            if (
                np.linalg.norm(between_velocity - [a["vx"], a["vy"]])
                > 2 + a["velocity_tolerance_pixels_hour"]
                or np.linalg.norm(between_velocity - [b["vx"], b["vy"]])
                > 2 + b["velocity_tolerance_pixels_hour"]
            ):
                continue
            selected = [lookup[i] for i in a["event_ids"] + b["event_ids"]]
            track = fit_track(selected, reference_time, tolerance)
            if track and track["n_epochs"] >= 4:
                track.update(
                    link_method="short tracklets + velocity consistency",
                    velocity_difference_pixels_hour=float(
                        np.hypot(a["vx"] - b["vx"], a["vy"] - b["vy"])
                    ),
                )
                matches.append(track)
    return unique_tracks(matches)


def cadence_assessment(times_hours):
    times = np.unique(np.asarray(times_hours, float))
    if len(times) < 2:
        return dict(eligible=False, reason="Fewer than two distinct epochs")
    intervals = np.diff(times)
    groups = np.split(np.arange(len(times)), np.flatnonzero(intervals > 0.5) + 1)
    return dict(
        eligible=bool(len(times) >= 3 and 0 < np.ptp(times) <= 3),
        n_epochs=len(times),
        span_hours=float(np.ptp(times)),
        median_interval_seconds=float(np.median(intervals) * 3600),
        largest_gap_minutes=float(intervals.max() * 60),
        temporal_groups=[g.tolist() for g in groups],
        assumption="Linear trajectories in pixels; spectral/PSF changes remain",
    )
