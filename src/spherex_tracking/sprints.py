"""Hackathon Sprints 2–3: source ranking, motion links and reviewable visuals."""

import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np
from astropy.io import fits
from astropy.table import Table
from astropy.wcs import WCS

matplotlib.use("Agg")
from matplotlib import animation
from matplotlib import pyplot as plt

from .classification import finish_classification, run_classification, write_csv
from .core import Sequence, stack
from .differencing import trajectory_score
from .moving import (
    cadence_assessment,
    events_from_candidates,
    link_tracks,
    positional_crossmatch,
    unique_tracks,
    velocity_match_tracklets,
)
from .real_data import DEC, RA


def moving_template(sequence, psfs, track):
    template = np.zeros_like(sequence.images)
    for i, psf in enumerate(psfs):
        cx = int(round(track["x"] + track["vx"] * sequence.dt[i]))
        cy = int(round(track["y"] + track["vy"] * sequence.dt[i]))
        radius = psf.shape[0] // 2
        if (
            min(cx, cy) < radius
            or cx + radius >= template.shape[2]
            or cy + radius >= template.shape[1]
        ):
            continue
        template[i, cy - radius : cy + radius + 1, cx - radius : cx + radius + 1] = psf
    return template


def run_motion(output="outputs/sprints", include_controls=True):
    output = Path(output)
    ranking = json.loads((output / "candidate_ranking.json").read_text())
    upstream = json.loads(Path("outputs/zogy/report.json").read_text())
    products = dict(np.load("outputs/zogy/products.npz"))
    mjd = np.array([e["mjd_avg"] for e in upstream["exposures"]])
    times = (mjd - mjd[0]) * 24
    reference_time = float(np.median(times))
    with fits.open(upstream["exposures"][0]["path"]) as h:
        wcs = WCS(h["IMAGE"].header, naxis=2)
    cx, cy = np.rint(wcs.world_to_pixel_values(RA, DEC))
    size = products["images"].shape[1]
    offset_x, offset_y = cx - size // 2, cy - size // 2
    source_catalog = Table.read("outputs/zogy/sep_native_0.ecsv")
    catalog_ra, catalog_dec = wcs.pixel_to_world_values(source_catalog["x"], source_catalog["y"])
    ra, dec = wcs.pixel_to_world_values(
        np.array([r["x"] for r in ranking]) + offset_x,
        np.array([r["y"] for r in ranking]) + offset_y,
    )
    index, separation, matched = positional_crossmatch(ra, dec, catalog_ra, catalog_dec)
    for i, row in enumerate(ranking):
        row.update(
            ra_deg=float(ra[i]),
            dec_deg=float(dec[i]),
            nearest_reference_source_index=int(index[i]),
            nearest_reference_source_arcsec=float(separation[i]),
            overlaps_reference_source=bool(matched[i]),
        )
    write_csv(
        output / "positional_crossmatches.csv",
        [
            dict(
                candidate_id=r["candidate_id"],
                ra_deg=r["ra_deg"],
                dec_deg=r["dec_deg"],
                nearest_source=r["nearest_reference_source_index"],
                separation_arcsec=r["nearest_reference_source_arcsec"],
                positional_match=r["overlaps_reference_source"],
            )
            for r in ranking
        ],
    )
    events = events_from_candidates(ranking, times)
    cadence = cadence_assessment(times)
    group_tracklets = []
    for group in cadence["temporal_groups"]:
        selected = [e for e in events if e["epoch"] in group]
        group_tracklets.append(link_tracks(selected, reference_time, min_epochs=3, min_speed=0))
    linked = []
    for i in range(len(group_tracklets) - 1):
        linked.extend(
            velocity_match_tracklets(
                group_tracklets[i], group_tracklets[i + 1], events, reference_time
            )
        )
    direct = link_tracks(events, reference_time, min_epochs=4, min_speed=0.5, seed_baseline=0.5)
    for track in direct:
        track["link_method"] = "position seeds across temporal groups + fitted velocity"
    tracks = unique_tracks(linked + direct)
    event_lookup = {e["event_id"]: e for e in events}
    for i, track in enumerate(tracks, 1):
        track["track_id"] = i
        track["candidate_ids"] = sorted(
            {c for eid in track["event_ids"] for c in event_lookup[eid]["candidate_ids"]}
        )
        track["ra_at_reference_deg"], track["dec_at_reference_deg"] = map(
            float, wcs.pixel_to_world_values(track["x"] + offset_x, track["y"] + offset_y)
        )
        track["review_status"] = "candidato de movimento; sem identificação orbital"
    for row in ranking:
        supporting = [t for t in tracks if row["candidate_id"] in t["candidate_ids"]]
        n_epochs = max([t["n_epochs"] for t in supporting], default=0)
        row["track_ids"] = [t["track_id"] for t in supporting]
        row["motion_support_epochs"] = n_epochs
        row["priority_score"] = float(
            100
            * (
                0.7 * row["source_like_score"]
                + 0.2 * min(n_epochs / 4, 1)
                + 0.1 * row["abs_scorr"] / (row["abs_scorr"] + 5)
            )
        )
    ranking.sort(key=lambda r: r["priority_score"], reverse=True)
    for i, row in enumerate(ranking, 1):
        row["rank"] = i
    write_csv(output / "candidate_ranking.csv", ranking)
    (output / "candidate_ranking.json").write_text(json.dumps(ranking, indent=2))
    (output / "tracklets.json").write_text(json.dumps(group_tracklets, indent=2))
    (output / "velocity_matches.json").write_text(json.dumps(linked, indent=2))
    (output / "tracks.json").write_text(json.dumps(tracks, indent=2))
    write_csv(output / "events.csv", events)
    sequence = Sequence(products["images"], times, products["variances"], products["masks"])
    stacks = {}
    stack_results = []
    for track in tracks[:5] if cadence["eligible"] else []:
        drift = track["speed_pixels_hour"] * cadence["span_hours"]
        if not 1 <= drift <= size / 2:
            continue
        image, variance, coverage = stack(sequence, track["vx"], track["vy"])
        template = moving_template(sequence, products["psfs"], track)
        score = trajectory_score(sequence, template)
        track_id = track["track_id"]
        stacks[f"track{track_id}_image"] = image
        stacks[f"track{track_id}_variance"] = variance
        stacks[f"track{track_id}_coverage"] = coverage
        stack_results.append(
            dict(
                track_id=track_id,
                drift_pixels=drift,
                static_scene_projected_model_score=score,
                label="Hypothesis evaluation, not confirmation",
            )
        )
    np.savez_compressed(output / "stacks.npz", **stacks)
    control_recovered, control_tracks = None, []
    injected_sequence, control_track = None, None
    if include_controls:
        # Independent linking control: a known eight-epoch trajectory + random distractors.
        rng = np.random.default_rng(16)
        control = []
        for epoch, time in enumerate(times):
            control.append(
                dict(
                    event_id=len(control),
                    epoch=epoch,
                    time_hours=float(time),
                    x=float(40 + 3 * (time - reference_time) + rng.normal(0, 0.08)),
                    y=float(50 - 2 * (time - reference_time) + rng.normal(0, 0.08)),
                    source_like_score=0.8,
                )
            )
            for _ in range(3):
                control.append(
                    dict(
                        event_id=len(control),
                        epoch=epoch,
                        time_hours=float(time),
                        x=float(rng.uniform(10, 100)),
                        y=float(rng.uniform(10, 100)),
                        source_like_score=0.5,
                    )
                )
        control_tracks = link_tracks(
            control, reference_time, min_epochs=4, min_speed=0.5, seed_baseline=0.5
        )
        control_recovered = any(
            abs(t["vx"] - 3) < 0.3 and abs(t["vy"] + 2) < 0.3 and t["n_epochs"] >= 6
            for t in control_tracks
        )
        # A separate visual control tests stacking with a known source on real backgrounds.
        control_track = dict(x=40.0, y=50.0, vx=3.0, vy=-2.0)
        control_template = moving_template(sequence, products["psfs"], control_track)
        flux = float(
            8
            * np.sqrt(
                np.median(products["variances"])
                / np.median(np.sum(products["psfs"] ** 2, axis=(1, 2)))
            )
        )
        injected_sequence = Sequence(
            sequence.images + flux * control_template, times, sequence.variance, sequence.mask
        )
        injected_stack, _, _ = stack(injected_sequence, 3, -2)
        stacks["injected_control_stack"] = injected_stack
        np.savez_compressed(output / "stacks.npz", **stacks)
    else:
        (output / "control_blink.gif").unlink(missing_ok=True)
    summary = dict(
        cadence=cadence,
        n_positional_matches=int(matched.sum()),
        crossmatch_catalog="SEP sources in first calibrated exposure; no external identity claim",
        n_candidates=len(ranking),
        n_unique_epoch_events=len(events),
        n_tracklets_per_group=[len(g) for g in group_tracklets],
        n_velocity_matched_tracks=len(linked),
        n_combined_tracks=len(tracks),
        n_real_track_stacks=len(stack_results),
        stack_evaluations=stack_results,
        linking_control=dict(
            recovered=control_recovered,
            n_control_tracks=len(control_tracks),
            label="Known synthetic positions with distractors, not real detections",
        )
        if include_controls
        else {"executed": False},
        stack_control=dict(
            label="Artificial moving source on registered real backgrounds",
            model_score_before=trajectory_score(sequence, control_template),
            model_score_after=trajectory_score(injected_sequence, control_template),
        )
        if include_controls
        else {"executed": False},
        ranking_formula="100*(0.7*source_like_score + 0.2*min(track_epochs/4,1) + 0.1*SNR/(SNR+5))",
        limitations=[
            "ML score learned from artificial labels; actual events remain unconfirmed."
            if include_controls
            else "ML uses observed native sources/flags, not confirmed asteroid labels.",
            "Short-track velocity tolerance is a resolution heuristic, not a confidence interval.",
            "Linear tracks; parallax and LVF flux changes remain approximate.",
            "Reference/source overlap is positional only; it does not prove object identity.",
        ],
        confirmed_asteroids=0,
    )
    (output / "sprint3_report.json").write_text(json.dumps(summary, indent=2, allow_nan=False))
    render_visuals(
        output, ranking, tracks, products, upstream, times, injected_sequence, control_track
    )
    print(
        "Events:",
        len(events),
        "; tracks:",
        len(tracks),
        "; real track stacks:",
        len(stack_results),
        flush=True,
    )
    return summary


def render_visuals(output, ranking, tracks, products, upstream, times, injected, control_track):
    fig, axes = plt.subplots(2, 3, figsize=(11, 7), layout="constrained")
    for ax, row in zip(axes.flat, ranking[:6]):
        x, y = int(row["x"]), int(row["y"])
        data = products[f"pair{row['pair']}_scorr"][y - 6 : y + 7, x - 6 : x + 7]
        valid = products[f"pair{row['pair']}_valid"][y - 6 : y + 7, x - 6 : x + 7]
        cmap = plt.get_cmap("RdBu_r").copy()
        cmap.set_bad("#777777")
        ax.imshow(np.where(valid, data, np.nan), origin="lower", cmap=cmap, vmin=-8, vmax=8)
        ax.set_title(
            f"#{row['rank']} • prioridade {row['priority_score']:.0f}/100\n"
            f"{row['predicted_class'].replace('_', ' ')}"
        )
        ax.set_xticks([])
        ax.set_yticks([])
    fig.suptitle("Ranking dos candidatos reais — classes previstas para revisão")
    fig.savefig(output / "ranking.png", dpi=150)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(7, 5), layout="constrained")
    ax.imshow(products["images"][4], origin="lower", cmap="gray", vmin=-0.05, vmax=0.2)
    for track in tracks[:8]:
        dt = times - np.median(times)
        ax.plot(
            track["x"] + track["vx"] * dt,
            track["y"] + track["vy"] * dt,
            "o-",
            ms=3,
            label=f"Trajetória {track['track_id']}",
        )
    ax.set(
        title="Trajetórias propostas sobre exposição real", xlabel="x [pixel]", ylabel="y [pixel]"
    )
    if tracks:
        ax.legend(loc="upper left", fontsize=8)
    fig.savefig(output / "tracks.png", dpi=150)
    plt.close(fig)
    # Side-by-side stack views, with the artificial control clearly labeled.
    original = Sequence(products["images"], times, products["variances"], products["masks"])
    cases = (
        [(injected, control_track, "Controle artificial sobre fundo real")]
        if injected is not None
        else []
    )
    if tracks:
        cases.insert(0, (original, tracks[0], "Hipótese em candidatos reais"))
    if not cases:
        cases = [(original, dict(x=56.0, y=56.0, vx=0.0, vy=0.0), "Sem trajetória compatível")]
    fig, axes = plt.subplots(
        len(cases), 2, figsize=(8, 4 * len(cases)), layout="constrained", squeeze=False
    )
    for row, (sequence, track, title) in enumerate(cases):
        stationary = stack(sequence, 0, 0)[0]
        tracked = stack(sequence, track["vx"], track["vy"])[0]
        cx, cy = int(round(track["x"])), int(round(track["y"]))
        lo_x, hi_x = max(0, cx - 12), min(stationary.shape[1], cx + 13)
        lo_y, hi_y = max(0, cy - 12), min(stationary.shape[0], cy + 13)
        for ax, data, label in zip(
            axes[row],
            [stationary, tracked],
            ["Sem acompanhar movimento", "Acompanhando trajetória"],
        ):
            ax.imshow(
                data[lo_y:hi_y, lo_x:hi_x],
                origin="lower",
                cmap="gray",
                vmin=-0.03,
                vmax=0.15,
                extent=(lo_x, hi_x, lo_y, hi_y),
            )
            ax.plot(track["x"], track["y"], "o", mfc="none", mec="cyan", ms=18)
            ax.set(title=f"{title}\n{label}", xlabel="x [pixel]", ylabel="y [pixel]")
    fig.savefig(output / "stack_comparison.png", dpi=150)
    plt.close(fig)
    # Use the best real hypothesis; keep a clearly labeled control GIF separately.
    clips = []
    if injected is not None:
        clips.append(
            (
                "control_blink.gif",
                injected.images,
                control_track,
                "Controle: fonte artificial sobre fundo real",
            )
        )
    if tracks:
        clips.append(
            (
                "candidate_blink.gif",
                products["images"],
                tracks[0],
                "Trajetória candidata em dados reais",
            )
        )
    for filename, image_cube, track, title in clips:
        fig, ax = plt.subplots(figsize=(5, 5), layout="constrained")
        artist = ax.imshow(image_cube[0], origin="lower", cmap="gray", vmin=-0.05, vmax=0.2)
        (marker,) = ax.plot([], [], "o", mfc="none", mec="cyan", ms=18)

        def update(i):
            artist.set_data(image_cube[i])
            dt = times[i] - np.median(times)
            marker.set_data([track["x"] + track["vx"] * dt], [track["y"] + track["vy"] * dt])
            ax.set_title(f"{title}\nExposição {i + 1}/8 • t={times[i]:.2f} h", fontsize=10)
            return artist, marker

        animation.FuncAnimation(fig, update, frames=len(times), interval=450).save(
            output / filename, writer=animation.PillowWriter(fps=2)
        )
        plt.close(fig)


def run_sprints(output="outputs/sprints", samples=900, timeout=120.0, reuse_training=False):
    output = Path(output)
    if reuse_training:
        summary = json.loads((output / "sprint2_report.json").read_text())
        for file, key in [
            ("products.npz", "upstream_products_sha256"),
            ("report.json", "upstream_report_sha256"),
        ]:
            if (
                hashlib.sha256((Path("outputs/zogy") / file).read_bytes()).hexdigest()
                != summary[key]
            ):
                raise ValueError("ZOGY inputs changed; rerun without --reuse-training.")
        finish_classification(output)
    else:
        run_classification(output, samples, timeout)
    return run_motion(output)


if __name__ == "__main__":
    run_motion()
