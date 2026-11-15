"""Animate observations at a fixed SPHEREx spectral channel, never along wavelength."""

import csv
import json
from pathlib import Path

import matplotlib
import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from reproject import reproject_exact
from scipy.interpolate import RegularGridInterpolator

from .quality import bad_pixel_mask
from .time_lapse import _grid

matplotlib.use("Agg")
from matplotlib import animation  # noqa: E402
from matplotlib import pyplot as plt


def temporal_viewer(report_path="outputs/temporal_band/report.json"):
    """Select observation dates in Aladin while holding the spectral channel fixed."""
    import ipywidgets as widgets
    from ipyaladin import Aladin
    from IPython.display import display

    report_path = Path(report_path).resolve()
    report = json.loads(report_path.read_text())
    root = report_path.parents[2]
    frames = report["frames"]
    slider = widgets.IntSlider(
        min=1, max=len(frames), value=1, description="Imagem", continuous_update=False
    )
    caption, output = widgets.HTML(), widgets.Output()
    previous = []

    def show_image(change=None):
        frame = frames[slider.value - 1]
        for widget in previous:
            widget.close()
        previous.clear()
        sky = Aladin(
            target=f"{report['target']['ra']} {report['target']['dec']}",
            fov=176 / 3600,
            survey="P/DSS2/color",
        )
        image = Path(frame["image"])
        if not image.is_absolute():
            image = root / image
        sky.add_fits(image, name=f"Banda {report['plane']} • {frame['date']}")
        caption.value = (
            f"Banda fixa {report['plane']} — {report['wavelength_um']:.3f} µm"
            f"<br>{frame['date']} • cobertura {frame['coverage_fraction']:.0%}"
        )
        previous.append(sky)
        output.clear_output(wait=True)
        with output:
            display(sky)

    slider.observe(show_image, names="value")
    show_image()
    return widgets.VBox([slider, caption, output])


def build_temporal_band(
    inventory="outputs/timelapse/observations.csv",
    channel_cube="data/spectral_cube/M101_irsa.fits",
    output="outputs/temporal_band",
    plane=99,
    ra=133.786245,
    dec=-7.244372,
    size_arcsec=176.0,
):
    """Select the SAME channel per detector pixel, then animate individual exposures.

    The cube supplies only the standard spectral channel boundaries. The image
    pixels and observation times come from the local temporal exposure inventory.
    """
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    with fits.open(channel_cube) as hdul:
        channels = hdul["SPECTRAL_CHANNELS"].data
        if not 1 <= plane <= len(channels):
            raise ValueError("Plane is outside the spectral channel table.")
        band = channels[plane - 1]
        lo, hi, center = [float(band[k]) for k in ["WL_MIN", "WL_MAX", "WAVELENGTH"]]
        detector = int(band["DETECTOR"])
    with Path(inventory).open(newline="") as handle:
        records = list(csv.DictReader(handle))
    records.sort(key=lambda row: row["date"])
    size = round(size_arcsec / 6.2)
    output_wcs = _grid(ra, dec, size, size_arcsec / size)
    frames, frame_info, rejected = [], [], []
    mosaics = output / "images"
    mosaics.mkdir(exist_ok=True)
    for record in records:
        with fits.open(record["path"]) as hdul:
            hdu = hdul["IMAGE"]
            if int(hdu.header["DETECTOR"]) != detector:
                rejected.append(dict(obs_id=record["obs_id"], reason="different detector"))
                continue
            wcs = WCS(hdu.header, fobj=hdul, naxis=2)
            y, x = np.indices(hdu.data.shape)
            lookup = hdul["WCS-WAVE"].data[0]
            # Same original-detector coordinate convention as the archived cutouts.
            points = np.column_stack(
                [
                    (y + 2 - hdu.header["CRPIX2A"]).ravel(),
                    (x + 2 - hdu.header["CRPIX1A"]).ravel(),
                ]
            )
            wavelength = RegularGridInterpolator(
                (lookup["Y"], lookup["X"]),
                np.asarray(lookup["VALUES"], dtype=float)[:, :, 0],
                bounds_error=False,
                fill_value=np.nan,
            )(points).reshape(x.shape)
            data = np.asarray(hdu.data, dtype=float) - hdul["ZODI"].data
            valid = (
                (wavelength >= lo)
                & (wavelength < hi)
                & np.isfinite(data)
                & ~bad_pixel_mask(hdul["FLAGS"].data)
            )
            if not valid.any():
                rejected.append(dict(obs_id=record["obs_id"], reason="no valid pixels in band"))
                continue
            # Reproject zero-filled numerator and validity separately so NaNs at a
            # channel boundary do not discard neighboring usable pixel overlaps.
            numerator, footprint = reproject_exact(
                (np.where(valid, data, 0), wcs), output_wcs, shape_out=(size, size)
            )
            fraction, _ = reproject_exact(
                (valid.astype(float), wcs), output_wcs, shape_out=(size, size)
            )
            keep = (footprint > 0) & (fraction >= 0.5)
            image = np.divide(numerator, fraction, out=np.full((size, size), np.nan), where=keep)
            if not np.isfinite(image).any():
                rejected.append(dict(obs_id=record["obs_id"], reason="no reprojected coverage"))
                continue
            header = output_wcs.to_header()
            header["BUNIT"] = "MJy/sr"
            header["DATE-OBS"] = record["date"]
            header["OBSID"] = record["obs_id"]
            header["BAND"] = plane
            header["WLMIN"], header["WLMAX"] = lo, hi
            path = mosaics / f"{record['obs_id']}.fits"
            fits.PrimaryHDU(image.astype(np.float32), header).writeto(path, overwrite=True)
            frame_info.append(
                dict(
                    obs_id=record["obs_id"],
                    date=record["date"],
                    image=str(path),
                    coverage_fraction=float(np.isfinite(image).mean()),
                    input_wavelength_range_um=[
                        float(wavelength[valid].min()),
                        float(wavelength[valid].max()),
                    ],
                )
            )
            frames.append(image)
    if len(frames) < 2:
        raise ValueError("Fewer than two observations cover this channel.")
    cube = np.asarray(frames)
    vmin, vmax = np.nanpercentile(cube, [1, 99.7])
    cmap = plt.get_cmap("gray_r").copy()
    cmap.set_bad("#344459")
    fig, ax = plt.subplots(figsize=(6, 6), layout="constrained")
    artist = ax.imshow(
        cube[0], origin="lower", cmap=cmap, vmin=vmin, vmax=vmax, interpolation="nearest"
    )
    ax.set(xlabel="pixel na mesma grade celeste", ylabel="pixel")
    ax.text(
        0.02,
        0.02,
        "Azul: sem cobertura nesta banda\nContraste fixo em toda a sequência",
        transform=ax.transAxes,
        fontsize=8,
        color="white",
        bbox={"facecolor": "black", "alpha": 0.75},
    )

    def update(i):
        artist.set_data(cube[i])
        ax.set_title(
            f"SPHEREx • banda fixa {plane} • {center:.3f} µm\n"
            f"{frame_info[i]['date']}\nImagem {i + 1}/{len(frames)} • "
            f"cobertura {frame_info[i]['coverage_fraction']:.0%}"
        )
        return (artist,)

    gif = output / "spherex_fixed_band_observations.gif"
    animation.FuncAnimation(fig, update, frames=len(frames), interval=700).save(
        gif, writer=animation.PillowWriter(fps=1.5)
    )
    plt.close(fig)
    report = dict(
        animation_axis="observation_time",
        plane=plane,
        wavelength_um=center,
        wavelength_range_um=[lo, hi],
        target=dict(ra=ra, dec=dec),
        channel_table_source=str(channel_cube),
        n_input=len(records),
        n_frames=len(frames),
        frames=frame_info,
        rejected=rejected,
        display_limits_mjy_sr=[float(vmin), float(vmax)],
        gif=str(gif),
        note="M101 cube supplies channel definitions only; pixels are from the WiseView target.",
    )
    (output / "report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({k: report[k] for k in ["n_frames", "plane", "wavelength_range_um", "gif"]}))
    return report
