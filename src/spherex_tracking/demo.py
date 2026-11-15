"""End-to-end injection and independent null-field checks with reviewable artifacts."""

import json
from dataclasses import asdict
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402

from .core import prepare, refine, search, stack
from .simulation import simulate


def detect(sequence):
    # Public fixed search box: never centered on the injected true velocity.
    candidates = search(sequence, np.arange(-8, 9), np.arange(-5, 6), threshold=0, max_candidates=3)
    refined = [refine(sequence, c, velocity_radius=1.0) for c in candidates]
    # Different coarse hypotheses can converge to the same refined trajectory.
    unique = []
    for candidate in sorted(refined, key=lambda c: c.snr, reverse=True):
        duplicate = any(
            np.max(
                np.hypot(
                    candidate.x - other.x + (candidate.vx - other.vx) * sequence.dt,
                    candidate.y - other.y + (candidate.vy - other.vy) * sequence.dt,
                )
            )
            < 2
            for other in unique
        )
        if not duplicate:
            unique.append(candidate)
    return unique


def run_demo(output="outputs/demo", seed=42, null_trials=8):
    if null_trials < 1:
        raise ValueError("É necessário pelo menos um ensaio nulo.")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    simulation = simulate(seed)
    clean = prepare(simulation.sequence)
    candidates = detect(clean)
    if not candidates:
        raise RuntimeError("A busca não retornou candidatos com cobertura suficiente.")
    best, truth = candidates[0], simulation.truth
    null_maxima = []
    for i in range(null_trials):
        null = prepare(simulate(seed + 1000 + i, single_snr=0).sequence)
        found = detect(null)
        null_maxima.append(found[0].snr if found else 0.0)
    position_error = float(np.hypot(best.x - truth["x"], best.y - truth["y"]))
    velocity_error = float(np.hypot(best.vx - truth["vx"], best.vy - truth["vy"]))
    report = {
        "experiment": "synthetic Gaussian noise; NOT SPHEREx data",
        "seed": seed,
        "n_exposures": len(clean.images),
        "time_span_hours": float(np.ptp(clean.times_hours)),
        "reference_time_hours": clean.reference_time,
        "truth": truth,
        "best_candidate": asdict(best),
        "candidates": [asdict(c) for c in candidates],
        "expected_single_frame_snr_median": float(np.median(simulation.expected_single_snr)),
        "measured_forced_single_frame_snr_median": float(np.median(simulation.measured_single_snr)),
        "ideal_combined_snr_at_true_path": float(np.linalg.norm(simulation.expected_single_snr)),
        "position_error_pixels": position_error,
        "velocity_error_pixels_per_hour": velocity_error,
        "null_trials": null_trials,
        "null_maximum_snrs": list(map(float, null_maxima)),
        "empirical_null_tail_fraction_plus_one": float(
            (1 + np.sum(np.array(null_maxima) >= best.snr)) / (1 + null_trials)
        ),
        "null_check_note": "Same coarse+refined search on independent star+noise fields. "
        "Few trials: a smoke check, not calibrated discovery significance.",
        "recovered_within_tolerance": position_error < 1 and velocity_error < 1,
        "limitations": [
            "Gaussian independent noise and PSF; no source photon noise or trailing model.",
            "Scalar sky subtraction and heuristic bright-star masking.",
            "Grid paths are rounded to integer pixels; refinement fits native pixels.",
            "No WCS registration, SPHEREx spectral calibration or ephemeris validation yet.",
            "This single injection does not measure population completeness or purity.",
        ],
    }
    untracked, _, _ = stack(clean, 0, 0)
    tracked, tracked_var, coverage = stack(clean, best.vx, best.vy)
    np.savez_compressed(
        output / "experiment.npz",
        images=simulation.sequence.images,
        times_hours=clean.times_hours,
        variance=clean.variance,
        mask=clean.mask,
        residuals=clean.images,
        tracked=tracked,
        tracked_variance=tracked_var,
        coverage=coverage,
    )
    with (output / "report.json").open("w") as handle:
        json.dump(report, handle, indent=2, allow_nan=False)
    fig, axes = plt.subplots(1, 3, figsize=(12, 4), layout="constrained")
    titles = ["Uma exposição", "Empilhamento sem movimento", "Empilhamento com trajetória"]
    for ax, data, title in zip(axes, [clean.images[0], untracked, tracked], titles):
        ax.imshow(data, origin="lower", cmap="gray", vmin=-0.7, vmax=0.7)
        ax.set(title=title, xlabel="x [pixel]", ylabel="y [pixel]")
    axes[0].plot(
        truth["x"] + truth["vx"] * clean.dt[0],
        truth["y"] + truth["vy"] * clean.dt[0],
        "o",
        mfc="none",
        mec="cyan",
        ms=15,
    )
    axes[2].plot(best.x, best.y, "o", mfc="none", mec="cyan", ms=15)
    fig.suptitle(
        f"Simulação — SNR recuperado: {best.snr:.1f}; erro de posição: {position_error:.2f} pixel"
    )
    fig.savefig(output / "comparison.png", dpi=160)
    plt.close(fig)
    return report
