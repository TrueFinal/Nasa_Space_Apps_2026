"""Apply the IRSA quick-look image workflow to the three original visit mosaics."""

import json
from pathlib import Path

import matplotlib
import numpy as np
from astropy.io import fits
from astropy.stats import SigmaClip
from astropy.table import Table
from astropy.wcs import WCS
from astropy.wcs.utils import proj_plane_pixel_area
from photutils.aperture import ApertureStats, CircularAnnulus, CircularAperture, aperture_photometry
from reproject import reproject_exact

matplotlib.use("Agg")
from matplotlib import animation  # noqa: E402
from matplotlib import pyplot as plt


def build_three_visits(
    manifest="outputs/timelapse/timelapse_report.json", output="outputs/three_visits"
):
    """Process EACH original visit image, then concatenate dates into one GIF.

    The input mosaics are 2D D6 images, not 102-band epoch cubes. Apply the
    tutorial's celestial WCS, flux conversion and aperture/background workflow.
    PAH 3.3 micron subtraction requires other spectral planes and is not applied.
    """
    report = json.loads(Path(manifest).read_text())
    visits = report["frame_records"]
    if len(visits) != 3:
        raise ValueError("This product requires exactly the three original visit mosaics.")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    frames, records, photometry = [], [], []
    reference = None
    for visit in visits:
        with fits.open(visit["mosaic"], memmap=False) as hdul:
            image = np.asarray(hdul[0].data, dtype=float)
            if image.ndim != 2:
                raise ValueError("Expected the original 2D visit mosaic.")
            wcs = WCS(hdul[0].header, fobj=hdul).celestial
            if reference is None:
                reference, shape = wcs, image.shape
        valid = np.isfinite(image)
        numerator, footprint = reproject_exact(
            (np.where(valid, image, 0), wcs), reference, shape_out=shape
        )
        fraction, _ = reproject_exact((valid.astype(float), wcs), reference, shape_out=shape)
        image = np.divide(
            numerator,
            fraction,
            out=np.full(shape, np.nan),
            where=(footprint > 0) & (fraction >= 0.5),
        )
        # Tutorial conversion, using the actual celestial pixel solid angle.
        factor = float(proj_plane_pixel_area(reference)) * (np.pi / 180) ** 2 * 1e9
        image *= factor  # MJy/sr -> mJy per output pixel
        ny, nx = shape
        center = ((nx - 1) / 2, (ny - 1) / 2)
        radius = min(shape) * 0.12
        aperture = CircularAperture(center, r=radius)
        annulus = CircularAnnulus(center, r_in=min(shape) * 0.32, r_out=min(shape) * 0.46)
        mask = ~np.isfinite(image)
        background = float(
            ApertureStats(
                image, annulus, mask=mask, sigma_clip=SigmaClip(sigma=3, maxiters=10)
            ).mean
        )
        measured = float(aperture_photometry(image, aperture, mask=mask)["aperture_sum"][0])
        area = float(aperture.area_overlap(image, mask=mask))
        photometry.append(
            dict(
                visit=visit["frame"],
                date=visit["date_start"],
                aperture_sum_mjy=measured,
                background_mjy_per_pixel=background,
                aperture_flux_background_subtracted_mjy=measured - background * area,
            )
        )
        # Subtract the measured background equally across each image. No separate
        # rescaling/contrast fit is used; all three frames share display limits.
        processed = image - background
        header = reference.to_header()
        header["BUNIT"] = "mJy/pixel"
        header["DATE-OBS"] = visit["date_start"]
        header["DATE-END"] = visit["date_end"]
        header["NCOMBINE"] = visit["n_images"]
        header["BKGSUB"] = background
        filename = output / f"visit_{visit['frame']:02d}_processed.fits"
        fits.PrimaryHDU(processed.astype(np.float32), header).writeto(filename, overwrite=True)
        records.append(
            dict(
                visit=visit["frame"],
                date=visit["date_start"],
                date_end=visit["date_end"],
                image=str(filename),
                input=visit["mosaic"],
                n_exposures=visit["n_images"],
                coverage_fraction=float(np.isfinite(processed).mean()),
            )
        )
        frames.append(processed)
    images = np.asarray(frames)
    vmin, vmax = np.nanpercentile(images, [1, 99.7])
    cmap = plt.get_cmap("inferno").copy()
    cmap.set_bad("#182331")
    fig, ax = plt.subplots(figsize=(6.5, 6), layout="constrained")
    artist = ax.imshow(
        images[0], origin="lower", cmap=cmap, vmin=vmin, vmax=vmax, interpolation="nearest"
    )
    fig.colorbar(artist, ax=ax, shrink=0.8, label="mJy/pixel • fundo subtraído")
    ax.set(xlabel="pixel na grade celeste comum", ylabel="pixel")

    def update(i):
        artist.set_data(images[i])
        record = records[i]
        ax.set_title(
            f"SPHEREx D6 • visita {i + 1}/3 • {record['date'][:10]}\n"
            f"Mosaico de {record['n_exposures']} exposições • mesma faixa espectral"
        )
        return (artist,)

    gif = output / "spherex_three_visits.gif"
    animation.FuncAnimation(fig, update, frames=3, interval=1000).save(
        gif, writer=animation.PillowWriter(fps=1)
    )
    plt.close(fig)
    fig, axes = plt.subplots(1, 3, figsize=(12, 4), layout="constrained")
    for i, ax in enumerate(axes):
        ax.imshow(
            images[i], origin="lower", cmap=cmap, vmin=vmin, vmax=vmax, interpolation="nearest"
        )
        ax.set_title(
            f"Visita {i + 1} • {records[i]['date'][:10]}\n{records[i]['n_exposures']} exposições"
        )
    fig.savefig(output / "three_visits.png", dpi=140)
    plt.close(fig)
    Table(rows=photometry).write(output / "photometry.csv", format="ascii.csv", overwrite=True)
    result = dict(
        animation_axis="visit_time",
        n_frames=3,
        frames=records,
        gif=str(gif),
        target=report["target"],
        wavelength_filter=report["wavelength_filter"],
        display_limits_mjy_per_pixel=[float(vmin), float(vmax)],
        input_type="three original 2D visit mosaics; not three single exposures",
        tutorial="https://caltech-ipac.github.io/irsa-tutorials/spherex-mosaic/",
        applied=[
            "celestial WCS",
            "reproject_exact",
            "MJy/sr to mJy/pixel",
            "aperture photometry",
            "annulus background subtraction",
            "shared display scale",
        ],
        limitations="D6 2D mosaics; no PAH 3.3 micron map or 102-band epoch cube inferred.",
    )
    (output / "report.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(dict(gif=str(gif), visits=records), indent=2))
    return result


def three_visit_viewer(report_path="outputs/three_visits/report.json"):
    """Choose one of the same three processed visit images in Aladin."""
    import ipywidgets as widgets
    from ipyaladin import Aladin
    from IPython.display import display

    path = Path(report_path).resolve()
    report = json.loads(path.read_text())
    root = path.parents[2]
    selector = widgets.IntSlider(
        min=1, max=3, value=1, description="Visita", continuous_update=False
    )
    caption, output = widgets.HTML(), widgets.Output()
    previous = []

    def show(change=None):
        frame = report["frames"][selector.value - 1]
        for sky in previous:
            sky.close()
        previous.clear()
        target = report["target"]
        sky = Aladin(
            target=f"{target['ra_deg']} {target['dec_deg']}", fov=176 / 3600, survey="P/DSS2/color"
        )
        sky.add_fits(root / frame["image"], name=f"Visita {frame['visit']} • {frame['date'][:10]}")
        previous.append(sky)
        caption.value = (
            f"Visita {frame['visit']}/3 • {frame['date'][:10]} • "
            f"mosaico de {frame['n_exposures']} exposições"
        )
        output.clear_output(wait=True)
        with output:
            display(sky)

    selector.observe(show, names="value")
    show()
    return widgets.VBox([selector, caption, output])
