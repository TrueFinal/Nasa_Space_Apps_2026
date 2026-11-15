"""Quick-look analysis and wavelength animation of real IRSA mosaic cubes."""

import json
import warnings
from pathlib import Path

import matplotlib
import numpy as np
from astropy.io import fits
from astropy.stats import SigmaClip
from astropy.table import Table
from astropy.wcs import WCS
from astropy.wcs.utils import proj_plane_pixel_area
from photutils.aperture import (
    ApertureStats,
    CircularAnnulus,
    CircularAperture,
    aperture_photometry,
)

matplotlib.use("Agg")
from matplotlib import animation  # noqa: E402
from matplotlib import pyplot as plt

TUTORIAL_URL = "https://caltech-ipac.github.io/irsa-tutorials/spherex-mosaic/"


def cube_viewer(path):
    """Interactive wavelength selector; use the cube's own sky position in Aladin."""
    import ipywidgets as widgets
    from ipyaladin import Aladin
    from IPython.display import display

    cube, wave, _, _, wcs = load_cube(path)
    n, ny, nx = cube.shape
    ra, dec = wcs.pixel_to_world_values((nx - 1) / 2, (ny - 1) / 2)
    fov = max(nx, ny) * np.sqrt(float(proj_plane_pixel_area(wcs)))
    slider = widgets.IntSlider(value=1, min=1, max=n, description="Banda", continuous_update=False)
    caption = widgets.HTML()
    output = widgets.Output()
    previous = []

    def show_band(change=None):
        i = slider.value - 1
        for old in previous:
            old.close()
        previous.clear()
        sky = Aladin(target=f"{float(ra)} {float(dec)}", fov=float(fov), survey="P/DSS2/color")
        header = wcs.to_header()
        header["BUNIT"] = "MJy/sr"
        sky.add_fits(
            fits.HDUList([fits.PrimaryHDU(cube[i].astype(np.float32), header)]),
            name=f"SPHEREx banda {i + 1} • {wave[i]:.3f} µm",
        )
        caption.value = (
            f"<b>{Path(path).name}</b> — banda {i + 1}/{n}, "
            f"λ={wave[i]:.3f} µm. Cada posição do seletor é uma banda espectral."
        )
        previous.append(sky)
        output.clear_output(wait=True)
        with output:
            display(sky)

    slider.observe(show_band, names="value")
    show_band()
    return widgets.VBox([slider, caption, output])


def load_cube(path):
    """Read the spectral lookup table, coverage and celestial WCS together."""
    with fits.open(path, memmap=False) as hdul:
        cube = np.asarray(hdul["IMAGE"].data, dtype=float).copy()
        if cube.ndim != 3:
            raise ValueError("Expected IMAGE with shape (wavelength, y, x).")
        wcs = WCS(hdul["IMAGE"].header, fobj=hdul).celestial
        unit = hdul["IMAGE"].header.get("BUNIT", "").replace(" ", "").lower()
        if unit != "mjy/sr":
            raise ValueError(f"Expected MJy/sr surface brightness; got {unit!r}.")
        record = hdul["WCS-WAVE"].data[0]
        n = cube.shape[0]
        wave = np.asarray(record["WAVELENGTHS"]).reshape(n, -1)[:, 0].astype(float)
        width = np.asarray(record["BANDWIDTHS"]).reshape(n, -1)[:, 0].astype(float)
        planes = np.asarray(record["PLANE"]).reshape(-1).astype(int)
        if len(planes) != n or not np.all(np.isfinite(wave)):
            raise ValueError("Spectral lookup table does not match IMAGE planes.")
        if "NHITS" in hdul:
            cube[hdul["NHITS"].data <= 0] = np.nan
    return cube, wave, width, planes, wcs


def build_spectral_cube(path, output="outputs/spectral_cube", label="M101"):
    """Apply the tutorial's aperture spectrum and continuum subtraction; animate bands."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    cube, wave, width, planes, wcs = load_cube(path)
    n, ny, nx = cube.shape
    # Exact MJy/sr -> mJy/pixel conversion from the celestial pixel solid angle.
    area_deg2 = float(proj_plane_pixel_area(wcs))
    factor = area_deg2 * (np.pi / 180) ** 2 * 1e9
    flux = cube * factor
    center = ((nx - 1) / 2, (ny - 1) / 2)
    radius = min(nx, ny) * 20 / 267
    aperture = CircularAperture(center, r=radius)
    annulus = CircularAnnulus(center, r_in=radius * 3, r_out=radius * 5)
    spectrum = []
    valid_pixels = []
    for image in flux:
        mask = ~np.isfinite(image)
        valid_pixels.append(int((~mask).sum()))
        if mask.all():
            spectrum.append(np.nan)
            continue
        background = ApertureStats(
            image, annulus, mask=mask, sigma_clip=SigmaClip(sigma=3, maxiters=10)
        ).mean
        measured = aperture_photometry(image, aperture, mask=mask)["aperture_sum"][0]
        area = aperture.area_overlap(image, mask=mask)
        spectrum.append(float(measured - background * area))
    Table(
        [planes, wave, width, spectrum, valid_pixels],
        names=["plane", "wavelength_um", "bandwidth_um", "aperture_flux_mjy", "valid_pixels"],
    ).write(output / "spectrum.csv", format="ascii.csv", overwrite=True)

    feature = int(np.argmin(abs(wave - 3.3)))
    if feature < 2 or feature + 2 >= n:
        raise ValueError("Cube lacks continuum neighbors for the 3.3 micron feature.")
    neighbors = [feature - 2, feature - 1, feature + 1, feature + 2]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        continuum = np.nanmedian(flux[neighbors], axis=0)
    feature_map = flux[feature] - continuum
    # Require all four continuum bands to avoid changing the estimator by pixel.
    feature_map[~np.all(np.isfinite(flux[neighbors]), axis=0)] = np.nan
    header = wcs.to_header()
    header["BUNIT"] = "mJy/pixel"
    header["WAVELEN"] = float(wave[feature])
    header["HISTORY"] = "Feature minus median of the four neighboring continuum planes."
    fits.PrimaryHDU(feature_map.astype(np.float32), header).writeto(
        output / "pah_3p3_continuum_subtracted.fits", overwrite=True
    )
    fig, (ax, map_ax) = plt.subplots(1, 2, figsize=(11, 4.5), layout="constrained")
    ax.plot(wave, spectrum, ".-", ms=3)
    ax.axvline(wave[feature], color="red", alpha=0.6)
    ax.set(
        xlabel="Comprimento de onda [µm]",
        ylabel="Fluxo na abertura [mJy]",
        title=f"{label} • espectro com subtração do fundo",
    )
    limit = np.nanpercentile(np.abs(feature_map), 99)
    map_ax.imshow(feature_map, origin="lower", cmap="RdBu_r", vmin=-limit, vmax=limit)
    map_ax.set_title(f"{label} • {wave[feature]:.3f} µm − contínuo")
    fig.savefig(output / "spectrum_and_pah.png", dpi=140)
    plt.close(fig)

    # Each band gets its own explicit display limits, never a flux renormalization.
    limits = []
    for image in cube:
        good = image[np.isfinite(image)]
        limits.append(np.percentile(good, [5, 99.5]).tolist() if good.size else [0, 1])
    fig, ax = plt.subplots(figsize=(6, 6), layout="constrained")
    cmap = plt.get_cmap("inferno").copy()
    cmap.set_bad("#1b2332")
    artist = ax.imshow(cube[0], origin="lower", cmap=cmap, interpolation="nearest")
    ax.set(xlabel="pixel na grade celeste do mosaico", ylabel="pixel")
    note = ax.text(
        0.02,
        0.02,
        "",
        transform=ax.transAxes,
        color="white",
        fontsize=9,
        bbox={"facecolor": "black", "alpha": 0.7},
    )

    def update(i):
        artist.set_data(cube[i])
        lo, hi = limits[i]
        artist.set_clim(lo, hi if hi > lo else lo + 1)
        ax.set_title(
            f"SPHEREx • {label} • banda {i + 1}/{n}\n"
            f"λ = {wave[i]:.3f} µm • largura {width[i]:.4f} µm"
        )
        note.set_text(
            "Sequência espectral • contraste por banda\n"
            + (
                "Sem cobertura nesta banda"
                if valid_pixels[i] == 0
                else f"Pixels válidos: {100 * valid_pixels[i] / (nx * ny):.1f}%"
            )
        )
        return artist, note

    animation.FuncAnimation(fig, update, frames=n, interval=250, blit=False).save(
        output / "spherex_102_bands.gif", writer=animation.PillowWriter(fps=4)
    )
    plt.close(fig)
    report = dict(
        input=str(Path(path).resolve()),
        label=label,
        shape=list(cube.shape),
        tutorial=TUTORIAL_URL,
        animation_axis="wavelength, not observation time",
        wavelength_um=wave.tolist(),
        planes=planes.tolist(),
        valid_pixels=valid_pixels,
        display_limits_mjy_sr=limits,
        display="5th–99.5th percentiles per band",
        feature_plane=int(planes[feature]),
        continuum_planes=planes[neighbors].tolist(),
        mjy_per_pixel_conversion=factor,
    )
    (output / "report.json").write_text(json.dumps(report, indent=2))
    print(f"{label}: {n} bandas; GIF em {output / 'spherex_102_bands.gif'}", flush=True)
    return report
