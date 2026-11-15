"""Display-only infrared mosaics. Never used by native-pixel photometry.

Inspired by IRSA's SPHEREx mosaic cube (x, y, wavelength). RGB is an
explicit aesthetic compression into three broad IR windows, not a spectrum.
"""

from __future__ import annotations

import json
from pathlib import Path

import astropy.units as u
import numpy as np
from astropy.io import fits
from astropy.wcs import WCS

TUTORIAL = "https://caltech-ipac.github.io/irsa-tutorials/spherex-mosaic/"
# RGB array order: long wavelengths red, intermediate green, short blue.
CHANNELS = (("R", 3.83, 5.0), ("G", 1.63, 3.83), ("B", 0.75, 1.63))
CONTEXT_REJECT = 1 | 2 | 4 | 16  # Gaia remains visible as stellar context.


def _window(wave, low, high):
    return (wave >= low) & ((wave <= high) if high == 5.0 else (wave < high))


def rgb_from_planes(planes, counts, contrast=0.3):
    """SkyShift-style display sky removal, robust limits and asinh, per RGB plane.

    Missing channels contribute no light, never an inferred value. Alpha is
    zero only where all three are missing; coverage is returned independently.
    """
    planes = np.asarray(planes, dtype=float)
    counts = np.asarray(counts)
    if planes.ndim != 3 or planes.shape[0] != 3 or counts.shape != planes.shape:
        raise ValueError("RGB requer três planos e mapas de cobertura alinhados.")
    if not np.isfinite(contrast) or not 0 <= contrast <= 1:
        raise ValueError("Contraste deve estar entre 0 e 1.")
    valid = np.isfinite(planes) & (counts > 0)
    rgb = np.zeros((*planes.shape[1:], 4), dtype=np.uint8)
    channels = []
    for i, (name, low, high) in enumerate(CHANNELS):
        good = valid[i]
        values = planes[i][good]
        info = {
            "channel": name,
            "low_um": low,
            "high_um": high,
            "covered_pixels": int(good.sum()),
            "coverage_fraction": float(good.mean()),
        }
        if values.size:
            background = float(np.median(values))
            lo, hi = np.percentile(
                values - background, [0.5 + 9.5 * contrast, 100 - 0.05 * 10 ** (2.3 * contrast)]
            )
            hi = max(hi, lo + (abs(lo) or 1) * 0.001)
            t = np.clip((values - background - lo) / (hi - lo), 0, 1)
            rgb[..., i][good] = np.rint(255 * np.arcsinh(10 * t) / np.arcsinh(10))
            info.update(background=background, limits=[float(lo), float(hi)])
        channels.append(info)
    rgb[..., 3] = valid.any(axis=0) * 255
    return rgb, channels, valid.all(axis=0)


def mosaic_from_frames(frames):
    """Register display copies by celestial WCS onto the first eligible image.

    Nearest native pixel, equal contribution mean, bounded to the reference
    footprint. No interpolation over holes, target tracking or flux inference.
    CWAVE is sampled from that same source pixel, never from detector labels.
    """
    frames = [f for f in frames if f.get("plot", {}).get("eligible", True)]
    if not frames:
        return None
    ref = frames[0]
    shape = tuple(ref["shape"])
    reference_wcs = WCS(fits.Header.fromstring(ref["wcs_header"]))
    yy, xx = np.indices(shape)
    sky = reference_wcs.pixel_to_world(xx, yy)
    sums = np.zeros((3, *shape))
    counts = np.zeros((3, *shape), dtype=np.uint16)
    contributors = []
    for frame in frames:
        wcs = WCS(fits.Header.fromstring(frame["wcs_header"]))
        sx, sy = wcs.world_to_pixel(sky)
        height, width = frame["shape"]
        inside = (
            np.isfinite(sx)
            & np.isfinite(sy)
            & (sx >= -0.5)
            & (sy >= -0.5)
            & (sx < width - 0.5)
            & (sy < height - 0.5)
        )
        # Avoid integer casts of NaN/inf, even for unrelated sky footprints.
        ix = np.floor(np.where(inside, sx, 0) + 0.5).astype(int)
        iy = np.floor(np.where(inside, sy, 0) + 0.5).astype(int)
        data = np.asarray(frame["science"], float)
        wave = np.asarray(frame["wavelength"], float)
        mask = np.asarray(frame["mask"], np.uint16)
        values, wavelengths = data[iy, ix], wave[iy, ix]
        good = (
            inside
            & np.isfinite(values)
            & np.isfinite(wavelengths)
            & ((mask[iy, ix] & CONTEXT_REJECT) == 0)
        )
        used = []
        for i, (name, low, high) in enumerate(CHANNELS):
            selected = good & _window(wavelengths, low, high)
            sums[i][selected] += values[selected]
            counts[i][selected] += 1
            if selected.any():
                used.append(name)
        if used:
            contributors.append(
                {
                    "id": frame["id"],
                    "utc": frame["utc"],
                    "input_sha256": frame["input_sha256"],
                    "channels": used,
                }
            )
    planes = np.full_like(sums, np.nan)
    np.divide(sums, counts, out=planes, where=counts > 0)
    return planes, counts, reference_wcs, ref["id"], contributors


def _save_preview(planes, counts, wcs, output, metadata, synthetic=False):
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    rgb, channels, complete = rgb_from_planes(planes, counts)
    # Paint absent coverage as hatch; a covered zero remains black.
    yy, xx = np.indices(rgb.shape[:2])
    backdrop = np.where(
        ((xx + yy) % 6 < 3)[..., None], np.array([19, 27, 37]), np.array([37, 49, 63])
    )
    display = np.where((rgb[..., 3] > 0)[..., None], rgb[..., :3], backdrop).astype("uint8")
    with plt.style.context("dark_background"):
        fig = plt.figure(figsize=(8, 7))
        fig.set_layout_engine("constrained", rect=(0, 0.085, 1, 0.915))
        ax = fig.add_subplot(111, projection=wcs)
        ax.imshow(display, origin="lower", interpolation="nearest")
        ax.set(xlabel="RA / ICRS", ylabel="Dec / ICRS")
        ax.set_title(
            "Mosaico IR / falsas cores / somente visual"
            + ("\nDADOS SINTETICOS" if synthetic else "")
        )
        fig.text(
            0.5,
            0.01,
            "R: 3.83-5.00 | G: 1.63-3.83 | B: 0.75-1.63 um\n"
            "Cor parcial onde faltam canais. Hachura: sem dados. Epocas combinadas.",
            ha="center",
            fontsize=8,
            color="white",
            va="bottom",
            zorder=1000,
            bbox={"facecolor": "black", "edgecolor": "none", "pad": 3},
        )
        fig.savefig(output / "color_mosaic.png", dpi=150)
        plt.close(fig)
    # Exact RGB raster for reuse; no visual scaling enters the science files.
    plt.imsave(output / "color_mosaic_rgba.png", rgb, origin="lower")
    metadata.update(
        display_only=True,
        reference=TUTORIAL,
        channels=channels,
        complete_rgb_fraction=float(complete.mean()),
        any_coverage_fraction=float((rgb[..., 3] > 0).mean()),
        shape=list(rgb.shape[:2]),
        preview="files/color_mosaic.png",
        raster="files/color_mosaic_rgba.png",
        synthetic=bool(synthetic),
        stretch="median display background / robust percentiles / asinh(10)",
        limitations=[
            "Falsas cores estéticas; não representam cores visíveis ou fluxo RGB calibrado.",
            "Canais ausentes não são interpolados; cor parcial não determina cor física.",
            "Épocas e bandas combinadas; objetos móveis podem deixar imagens múltiplas.",
            "Sem PSF matching; diferenças de PSF, ruído e cobertura também afetam as cores.",
            "Mosaico limitado ao campo de referência; não substitui fotometria nativa.",
        ],
    )
    (output / "color_mosaic.json").write_text(
        json.dumps(metadata, ensure_ascii=False, allow_nan=False, indent=2), encoding="utf-8"
    )
    return metadata


def render_color_mosaic(report, output):
    result = mosaic_from_frames(report["frames"])
    if result is None:
        report.pop("color_mosaic", None)
        return
    planes, counts, wcs, ref_id, contributors = result
    report["color_mosaic"] = _save_preview(
        planes,
        counts,
        wcs,
        output,
        {
            "source": "native_exposures",
            "reference_frame": ref_id,
            "wcs_header": wcs.to_header(relax=True).tostring(),
            "registration": "celestial WCS / nearest native pixel / equal mean / display only",
            "mask_reject_bits": CONTEXT_REJECT,
            "gaia": "stellar context retained",
            "contributors": contributors,
        },
        report.get("synthetic", False),
    )


def colorize_irsa_cube(path, output):
    """Colour an existing IRSA cube using WCS-WAVE, NHITS and SkyShift flag policy.

    No optical/UV data, aperture spectra or continuum subtraction are required.
    No dependence on the optional photutils/reproject analysis workflow.
    """
    from .infrared_mask import BAD_FLAGS, sha256

    path, output = Path(path).resolve(), Path(output).resolve()
    if output == path.parent or output in path.parents:
        raise ValueError("A saída deve ficar separada do cubo original.")
    with fits.open(path, memmap=False) as hdul:
        cube = np.array(hdul["IMAGE"].data, float)
        header = hdul["IMAGE"].header
        if cube.ndim != 3:
            raise ValueError("IMAGE deve ter eixos (comprimento de onda, y, x).")
        cube *= u.Unit(header.get("BUNIT", "")).to(u.MJy / u.sr)
        wcs = WCS(header, fobj=hdul).celestial
        table = hdul["WCS-WAVE"].data
        record = table[0]
        waves = np.asarray(record["WAVELENGTHS"], float).reshape(-1)
        planes = np.asarray(record["PLANE"]).reshape(-1)
        unit = hdul["WCS-WAVE"].columns["WAVELENGTHS"].unit
        waves *= u.Unit(unit or "um").to(u.um)
        if (
            len(waves) != len(cube)
            or len(planes) != len(cube)
            or not np.all(np.isfinite(waves))
            or not np.array_equal(np.sort(planes), np.arange(1, len(cube) + 1))
        ):
            raise ValueError("WCS-WAVE não corresponde aos planos IMAGE.")
        # Rows can be shuffled; PLANE is one based and identifies IMAGE's z index.
        waves = waves[np.argsort(planes)]
        valid = np.isfinite(cube)
        for name in ("NHITS", "FLAGS"):
            if name not in hdul or hdul[name].data.shape != cube.shape:
                raise ValueError(f"Cubo requer {name} alinhado com IMAGE.")
        valid &= np.isfinite(hdul["NHITS"].data) & (hdul["NHITS"].data > 0)
        valid &= (hdul["FLAGS"].data.astype(np.uint32) & BAD_FLAGS) == 0
        synthetic = bool(hdul[0].header.get("SYNTHET", header.get("SYNTHET", False)))
        rgb_planes = np.full((3, *cube.shape[1:]), np.nan)
        counts = np.zeros(rgb_planes.shape, dtype=np.uint32)
        channels_used = []
        for i, (name, low, high) in enumerate(CHANNELS):
            selected = _window(waves, low, high)
            good = valid[selected]
            counts[i] = good.sum(axis=0)
            total = np.where(good, cube[selected], 0).sum(axis=0)
            np.divide(total, counts[i], out=rgb_planes[i], where=counts[i] > 0)
            channels_used.append({"channel": name, "wavelengths_um": waves[selected].tolist()})
    return _save_preview(
        rgb_planes,
        counts,
        wcs,
        output,
        {
            "source": "irsa_mosaic_cube",
            "input_file": path.name,
            "input_sha256": sha256(path),
            "wcs_header": wcs.to_header(relax=True).tostring(),
            "registration": "existing IRSA celestial grid / equal mean of covered spectral planes",
            "mask_reject_bits": BAD_FLAGS,
            "spectral_planes": channels_used,
        },
        synthetic,
    )
