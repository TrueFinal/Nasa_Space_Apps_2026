"""Nominal SPHEREx detector bands; actual science wavelengths come from CWAVE."""

DETECTOR_BANDS = {
    1: (0.75, 1.09),
    2: (1.10, 1.62),
    3: (1.63, 2.41),
    4: (2.42, 3.82),
    5: (3.83, 4.41),
    6: (4.42, 5.00),
}
MAX_EXPOSURES = 72


def detectors_for(low, high, detector=0):
    return [
        d
        for d, (lo, hi) in DETECTOR_BANDS.items()
        if (not detector or detector == d) and low <= hi and high > lo
    ]


def spread_indices(count):
    """Endpoints then widest remaining temporal gaps, so one band cannot monopolize a pilot."""
    if count <= 0:
        return []
    selected = [0]
    if count > 1:
        selected.append(count - 1)
    while len(selected) < count:
        ordered = sorted(selected)
        gaps = [(right - left, left, right) for left, right in zip(ordered, ordered[1:])]
        _, left, right = max(gaps)
        selected.append((left + right) // 2)
    return selected


def balanced_candidates(rows, detectors):
    groups = {
        d: sorted(
            [r for r in rows if str(r["productid"]) == f"D{d}"], key=lambda r: float(r["mjd_start"])
        )
        for d in detectors
    }
    ordered = {d: [groups[d][i] for i in spread_indices(len(groups[d]))] for d in detectors}
    return [
        ordered[d][i]
        for i in range(max((len(v) for v in ordered.values()), default=0))
        for d in detectors
        if i < len(ordered[d])
    ]


def spectral_coverage(frames, low, high, detector=0):
    coverage = []
    for d, (lo, hi) in DETECTOR_BANDS.items():
        rows = [f for f in frames if f["detector"] == d]
        centres = sorted(
            {f["central_wavelength_um"] for f in rows if f.get("central_wavelength_um") is not None}
        )
        measured = [f for f in rows if f["measurement"]["flux_ujy"] is not None]
        requested = d in detectors_for(low, high, detector)
        coverage.append(
            {
                "detector": d,
                "nominal_um": [lo, hi],
                "requested": requested,
                "exposures": len(rows),
                "measurements": len(measured),
                "centres_um": centres,
                "status": "not_requested"
                if not requested
                else "not_observed"
                if not rows
                else "covered"
                if measured
                else "no_accepted_measurement",
            }
        )
    return coverage
