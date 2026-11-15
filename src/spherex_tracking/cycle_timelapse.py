"""Fixed-band SPHEREx mosaics grouped into complete six-month sky cycles."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from astropy.wcs.utils import proj_plane_pixel_area
from matplotlib import animation
from matplotlib import pyplot as plt
from reproject import reproject_exact


def build_complete_cycle_gif(
    manifest="outputs/timelapse/timelapse_report.json",
    output="outputs/complete_cycles",
):
    """Coadd D6 sky images in each full six-month period and animate the cycles.

    The visit mosaics are D6-only, so the shared inferno color scale is a
    false-color intensity display, not an IRSA three-channel spectral RGB image.
    """
    report = json.loads(Path(manifest).read_text(encoding="utf-8"))
    periods = report.get("complete_six_month_periods", [])
    visits = report.get("frame_records", [])
    if not periods:
        raise ValueError("The manifest has no complete six-month periods.")

    groups = []
    for period in periods:
        start, end = period["start"][:19], period["end"][:19]
        members = [v for v in visits if start <= v["date_start"][:19] < end]
        if members:
            groups.append((period, members))
    if not groups:
        raise ValueError("No visit mosaics fall inside the reported full-cycle periods.")

    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    with fits.open(groups[0][1][0]["mosaic"], memmap=False) as hdul:
        reference = WCS(hdul[0].header, fobj=hdul).celestial
        shape = hdul[0].data.shape
    pixel_factor = float(proj_plane_pixel_area(reference)) * (np.pi / 180) ** 2 * 1e9

    images, records = [], []
    for cycle_index, (period, members) in enumerate(groups, start=1):
        numerator, denominator = np.zeros(shape), np.zeros(shape)
        for visit in members:
            with fits.open(visit["mosaic"], memmap=False) as hdul:
                data = np.asarray(hdul[0].data, dtype=float)
                wcs = WCS(hdul[0].header, fobj=hdul).celestial
                hits = np.asarray(hdul["NHITS"].data, dtype=float) if "NHITS" in hdul else np.ones_like(data)
            valid = np.isfinite(data) & np.isfinite(hits) & (hits > 0)
            projected_sum, footprint = reproject_exact(
                (np.where(valid, data * hits, 0), wcs), reference, shape_out=shape
            )
            projected_hits, _ = reproject_exact(
                (np.where(valid, hits, 0), wcs), reference, shape_out=shape
            )
            use = np.isfinite(projected_sum) & np.isfinite(projected_hits) & (projected_hits > 0) & (footprint > 0)
            numerator[use] += projected_sum[use]
            denominator[use] += projected_hits[use]

        coadd = np.divide(numerator, denominator, out=np.full(shape, np.nan), where=denominator > 0)
        if not np.isfinite(coadd).any():
            continue
        background = float(np.nanmedian(coadd))
        coadd = (coadd - background) * pixel_factor
        header = reference.to_header()
        header["BUNIT"] = "mJy/pixel"
        header["CYCLE"] = cycle_index
        header["CYCSTART"] = period["start"][:10]
        header["CYCEND"] = period["end"][:10]
        header["NVISITS"] = len(members)
        header["NEXP"] = sum(int(v["n_images"]) for v in members)
        header["BKGSUB"] = background
        image_path = output / f"cycle_{cycle_index:02d}.fits"
        fits.PrimaryHDU(coadd.astype(np.float32), header).writeto(image_path, overwrite=True)
        images.append(coadd)
        records.append({
            "cycle": cycle_index,
            "start": period["start"],
            "end": period["end"],
            "n_visits": len(members),
            "n_exposures": sum(int(v["n_images"]) for v in members),
            "dates": [v["date_start"] for v in members],
            "image": str(image_path),
            "input_mosaics": [v["mosaic"] for v in members],
            "coverage_fraction": float(np.isfinite(coadd).mean()),
        })
    if not images:
        raise ValueError("The cycle mosaics contain no valid pixels.")

    limits = np.nanpercentile(np.stack(images), [1, 99.7])
    cmap = plt.get_cmap("inferno").copy()
    cmap.set_bad("#182331")
    fig, ax = plt.subplots(figsize=(6.5, 6), subplot_kw={"projection": reference}, layout="constrained")
    artist = ax.imshow(images[0], origin="lower", cmap=cmap, vmin=limits[0], vmax=limits[1], interpolation="nearest")
    bar = fig.colorbar(artist, ax=ax, shrink=0.8)
    bar.set_label("mJy/pixel · background-subtracted")
    ax.set(xlabel="Right Ascension (ICRS)", ylabel="Declination (ICRS)")

    def update(index):
        artist.set_data(images[index])
        item = records[index]
        ax.set_title(
            f"SPHEREx D6 · complete six-month cycle {item['cycle']} · {item['start'][:10]} to {item['end'][:10]}\n"
            f"{item['n_exposures']} exposures in {item['n_visits']} visit mosaics · fixed wavelength band"
        )
        return (artist,)

    gif = output / "spherex_complete_cycles.gif"
    animation.FuncAnimation(fig, update, frames=len(images), interval=1200, blit=False).save(
        gif, writer=animation.PillowWriter(fps=1)
    )
    plt.close(fig)

    fig, axes = plt.subplots(1, len(images), figsize=(5 * len(images), 4), squeeze=False, subplot_kw={"projection": reference}, layout="constrained")
    for axis, image, item in zip(axes[0], images, records):
        axis.imshow(image, origin="lower", cmap=cmap, vmin=limits[0], vmax=limits[1], interpolation="nearest")
        axis.set_title(f"Cycle {item['cycle']} · {item['start'][:10]} to {item['end'][:10]}\n{item['n_exposures']} exposures")
        axis.set(xlabel="Right Ascension (ICRS)", ylabel="Declination (ICRS)")
    fig.savefig(output / "complete_cycles.png", dpi=140)
    plt.close(fig)

    result = {
        "animation_axis": "complete_six_month_cycle_time",
        "n_frames": len(records),
        "gif": str(gif),
        "target": report["target"],
        "wavelength_filter": report["wavelength_filter"],
        "detector": "D6",
        "display": "shared inferno intensity stretch for one fixed D6 channel",
        "display_limits_mjy_per_pixel": [float(limits[0]), float(limits[1])],
        "coadd": "celestial WCS exact reprojection, NHITS-weighted mean, median background subtraction, shared grid",
        "cycles": records,
        "limitations": "Inputs are the existing 2D D6 time-series mosaics, not 102-plane spectral cubes. This GIF follows the tutorial's single-plane display steps; it does not reconstruct the full IRSA Mosaic cube.",
    }
    (output / "report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return result
