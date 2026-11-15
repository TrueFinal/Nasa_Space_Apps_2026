"""Covered native-pixel plates around MPC/MOST predictions, following SkyShift's scope.

Geometry and display background are separate from the native photometry and FITS data.
See skyshift/web/src/learn/data.ts, learn/plate.ts and blink/math.ts for the reference.
"""

from __future__ import annotations

import astropy.units as u
import numpy as np


def covered(point, support, crop=None):
    """A pixel centre must lie inside the footprint, crop and an available data pixel."""
    try:
        x, y = float(point["x"]), float(point["y"])
    except (ValueError, TypeError, KeyError):
        return False
    if not np.isfinite(x + y):
        return False
    height, width = support.shape
    if not -0.5 <= x < width - 0.5 or not -0.5 <= y < height - 0.5:
        return False
    if crop and not (
        crop["x"] - 0.5 <= x < crop["x"] + crop["w"] - 0.5
        and crop["y"] - 0.5 <= y < crop["y"] + crop["h"] - 0.5
    ):
        return False
    return bool(support[int(np.floor(y + 0.5)), int(np.floor(x + 0.5))])


def crop_around(points, shape, pad=12, minimum=40):
    """Square crop around covered predictions, padded and clamped to the image."""
    height, width = shape
    if not points:
        return {"x": 0, "y": 0, "w": width, "h": height}
    xs, ys = [p["x"] for p in points], [p["y"] for p in points]
    side = int(min(max(max(np.ptp(xs), np.ptp(ys)) + 2 * pad, minimum), width, height))
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    x = int(np.clip(np.floor(cx - (side - 1) / 2 + 0.5), 0, width - side))
    y = int(np.clip(np.floor(cy - (side - 1) / 2 + 0.5), 0, height - side))
    return {"x": x, "y": y, "w": side, "h": side}


def trajectory_segments(points, support, crop, mjd):
    """Never join across an uncovered pixel, a missing prediction or a session gap."""
    segments, current = [], []
    for point in sorted(points, key=lambda p: p["mjd"]):
        nearby = abs(point["mjd"] - mjd) <= 10 / 1440
        if nearby and covered(point, support, crop):
            if current:
                # Check every intervening pixel: do not draw through a data hole.
                previous = current[-1]
                n = max(
                    2, int(np.hypot(point["x"] - previous["x"], point["y"] - previous["y"]) * 2) + 1
                )
                path = zip(
                    np.linspace(previous["x"], point["x"], n),
                    np.linspace(previous["y"], point["y"], n),
                )
                if any(not covered({"x": x, "y": y}, support, crop) for x, y in path):
                    segments.append(current)
                    current = []
            current.append(point)
        else:
            if current:
                segments.append(current)
            current = []
    if current:
        segments.append(current)
    return segments


def _backgrounds(image, science, support, crop):
    sl = np.s_[crop["y"] : crop["y"] + crop["h"], crop["x"] : crop["x"] + crop["w"]]
    valid = support[sl]
    return {
        name: float(np.median(array[sl][valid])) if valid.any() else 0.0
        for name, array in (("image", image), ("science", science))
    }


def prepare_plate(image, science, mask, wcs, target, trajectory, stars, mjd):
    # A flagged instrument pixel is not usable image coverage. Gaia and band
    # rejection are separate layers: a star can still exist in the context image.
    support = (mask & (1 | 2 | 16)) == 0
    full = {"x": 0, "y": 0, "w": image.shape[1], "h": image.shape[0]}
    position_covered = covered(target, support)
    target_in_band = bool(
        position_covered
        and not mask[int(np.floor(target["y"] + 0.5)), int(np.floor(target["x"] + 0.5))] & 4
    )
    eligible = position_covered and target_in_band
    nearby = [p for p in trajectory if abs(p["mjd"] - mjd) <= 10 / 1440 and covered(p, support)]
    crop = crop_around([target, *nearby], image.shape) if eligible else full
    field_stars = [s for s in stars if covered(s, support)]
    crop_stars = [s for s in field_stars if covered(s, support, crop)]
    for star in field_stars:
        ix, iy = int(np.floor(star["x"] + 0.5)), int(np.floor(star["y"] + 0.5))
        star["in_band"] = not bool(mask[iy, ix] & 4)
    center = wcs.pixel_to_world(target["x"], target["y"]) if eligible else None
    compass = {}
    if center is not None:
        for direction, angle in (("N", 0), ("E", 90)):
            offset = center.directional_offset_by(angle * u.deg, 30 * u.arcsec)
            x, y = wcs.world_to_pixel(offset)
            dx, dy = float(x - target["x"]), float(y - target["y"])
            length = np.hypot(dx, dy)
            if np.isfinite(length) and length > 0:
                compass[direction] = {"x": dx / length, "y": dy / length}
        pixel_arcsec = float(
            center.separation(wcs.pixel_to_world(target["x"] + 1, target["y"])).arcsec
        )
    else:
        pixel_arcsec = None
    corners = wcs.pixel_to_world(
        [
            crop["x"] - 0.5,
            crop["x"] + crop["w"] - 0.5,
            crop["x"] + crop["w"] - 0.5,
            crop["x"] - 0.5,
        ],
        [
            crop["y"] - 0.5,
            crop["y"] - 0.5,
            crop["y"] + crop["h"] - 0.5,
            crop["y"] + crop["h"] - 0.5,
        ],
    )
    return {
        "eligible": eligible,
        "reason": (
            None
            if eligible
            else "mpc_position_outside_selected_band"
            if position_covered
            else "mpc_position_without_image_coverage"
        ),
        "crop": crop,
        "full_crop": full,
        "gaia": crop_stars,
        "field_gaia": field_stars,
        "trajectory_segments": trajectory_segments(trajectory, support, crop, mjd),
        "field_trajectory_segments": trajectory_segments(trajectory, support, full, mjd),
        "target_in_band": target_in_band,
        "background": _backgrounds(image, science, support, crop),
        "field_background": _backgrounds(image, science, support, full),
        "pixel_arcsec": pixel_arcsec,
        "compass": compass,
        "footprint_icrs": [{"ra": float(c.ra.deg), "dec": float(c.dec.deg)} for c in corners],
        "counts": {
            "catalogue_projected": len(stars),
            "inside_image": len(field_stars),
            "inside_crop": len(crop_stars),
            "excluded_from_image": len(stars) - len(field_stars),
        },
    }


def display_normalization(lo, hi):
    from astropy.visualization import AsinhStretch, ImageNormalize

    # ImageNormalize(clip=True) turns masked pixels into white data. Preserve
    # the mask; the colormap itself clips valid intensities to its end colours.
    return ImageNormalize(vmin=lo, vmax=hi, stretch=AsinhStretch(0.1), clip=False)


def render_comparison(report, output):
    """A shareable scientific plate, with native pixels and the same display policy."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle

    all_frames = [f for f in report["frames"] if f["plot"]["eligible"]]
    if not all_frames:
        return
    from .infrared_bands import spread_indices

    groups = {
        d: sorted([f for f in all_frames if f["detector"] == d], key=lambda f: f["mjd_utc"])
        for d in sorted({f["detector"] for f in all_frames})
    }
    order = {d: [rows[i] for i in spread_indices(len(rows))] for d, rows in groups.items()}
    frames = [
        order[d][i]
        for i in range(max(map(len, order.values())))
        for d in order
        if i < len(order[d])
    ][:12]
    frames.sort(key=lambda f: (f["detector"], f["mjd_utc"]))
    arrays = {}
    for frame in all_frames:
        c = frame["plot"]["crop"]
        sl = np.s_[c["y"] : c["y"] + c["h"], c["x"] : c["x"] + c["w"]]
        data = np.array(frame["science"], dtype=float)[sl]
        valid = (np.array(frame["mask"])[sl] & (1 | 2 | 16)) == 0
        arrays[frame["id"]] = np.where(valid, data - frame["plot"]["background"]["science"], np.nan)
    norms = {}
    for detector, group in groups.items():
        sample = np.concatenate([arrays[f["id"]][np.isfinite(arrays[f["id"]])] for f in group])
        lo, hi = np.percentile(sample, [3.35, 100 - 0.05 * 10**0.69])
        norms[detector] = display_normalization(lo, max(hi, lo + 1e-6))
    with plt.style.context("dark_background"):
        cmap = plt.get_cmap("gray").copy()
        cmap.set_bad("#24313f")
        columns = min(3, len(frames))
        blocks = int(np.ceil(len(frames) / columns))
        fig, axes = plt.subplots(
            2 * blocks, columns, figsize=(5 * columns, 8 * blocks), squeeze=False
        )
        for ax in axes.flat:
            ax.set_visible(False)
        for i, frame in enumerate(frames):
            c = frame["plot"]["crop"]
            for row in range(2):
                data = arrays[frame["id"]].copy()
                if row == 1:
                    sl = np.s_[c["y"] : c["y"] + c["h"], c["x"] : c["x"] + c["w"]]
                    data[(np.array(frame["mask"])[sl] & report["reject_bits"]) != 0] = np.nan
                ax = axes[2 * (i // columns) + row, i % columns]
                ax.set_visible(True)
                ax.set_facecolor("#19232d")
                ax.imshow(
                    np.ma.masked_invalid(data),
                    origin="lower",
                    cmap=cmap,
                    norm=norms[frame["detector"]],
                    interpolation="nearest",
                    extent=(
                        c["x"] - 0.5,
                        c["x"] + c["w"] - 0.5,
                        c["y"] - 0.5,
                        c["y"] + c["h"] - 0.5,
                    ),
                )
                for star in frame["plot"]["gaia"]:
                    if row == 0 or star["in_band"]:
                        ax.add_patch(
                            Circle(
                                (star["x"], star["y"]),
                                0.6,
                                fill=False,
                                color="#f4ce75",
                                linewidth=0.7,
                            )
                        )
                support = (np.array(frame["mask"]) & (1 | 2 | 16 | (4 if row else 0))) == 0
                for group in frame["plot"]["trajectory_segments"]:
                    for segment in trajectory_segments(group, support, c, frame["mjd_utc"]):
                        ax.plot(
                            [p["x"] for p in segment],
                            [p["y"] for p in segment],
                            color="#72d9ee",
                            linewidth=1,
                        )
                if covered(frame["target"], support, c):
                    ax.add_patch(
                        Circle(
                            (frame["target"]["x"], frame["target"]["y"]),
                            report["config"]["aperture_px"],
                            fill=False,
                            color="#72d9ee",
                            linewidth=0.9,
                        )
                    )
                ax.set_xlim(c["x"] - 0.5, c["x"] + c["w"] - 0.5)
                ax.set_ylim(c["y"] - 0.5, c["y"] + c["h"] - 0.5)
                ax.set_xlabel("X nativo (pixel)")
                ax.set_ylabel("Y nativo (pixel)")
                title = "Contexto SPHEREx - ZODI" if row == 0 else "Faixa e qualidade aplicadas"
                lam = frame.get("central_wavelength_um")
                label = f"D{frame['detector']} / {lam:.4f} um" if lam else f"D{frame['detector']}"
                ax.set_title(f"{title} / {label}\n{frame['utc']} UTC", fontsize=9)
        band = report["config"]
        kind = "DADOS SINTETICOS" if report["synthetic"] else "SPHEREx real"
        fig.suptitle(
            f"Zephyr / {report['object']} / "
            f"{band['low_um']:.2f}-{band['high_um']:.2f} um / {kind}\n"
            f"Recortes MPC/MOST | asinh por detector | {len(frames)}/{len(all_frames)} imagens",
            fontsize=13,
        )
        fig.text(
            0.5,
            0.015,
            "Fundo removido apenas no display. Ciano: posicao prevista, nao deteccao. "
            "Dourado: Gaia DR3. Cinza: sem dado aceito. Observador MOST nao verificado.",
            ha="center",
            fontsize=8,
        )
        fig.tight_layout(rect=(0, 0.04, 1, 0.92))
        fig.savefig(output / "comparison.png", dpi=150)
        plt.close(fig)
    report["plotting"]["preview"] = "files/comparison.png"
    report["plotting"]["preview_frame_ids"] = [f["id"] for f in frames]
