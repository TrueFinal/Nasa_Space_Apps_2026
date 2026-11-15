"""WISEview-style, fixed-band SPHEREx time lapse for one sky position."""

import csv
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

import matplotlib
import numpy as np
from astropy.io import fits
from astropy.table import Table
from astropy.time import Time
from astropy.wcs import WCS
from reproject import reproject_exact
from scipy.interpolate import RegularGridInterpolator

matplotlib.use("Agg")
from matplotlib import animation  # noqa: E402
from matplotlib import pyplot as plt

from .quality import bad_pixel_mask

RA_DEFAULT = 133.786245
DEC_DEFAULT = -7.244372
HALF_YEAR_DAYS = 365.2425 / 2


def _query(ra, dec, band):
    from astroquery.ipac.irsa import Irsa

    Irsa.TIMEOUT = 90
    result = Irsa.query_sia(pos=(ra, dec, 0.02), collection="spherex_dr1")
    table = result if isinstance(result, Table) else result.to_table()
    table = table[np.asarray(table["energy_bandpassname"]).astype(str) == band]
    # SIA can return duplicate rows for a product. One FITS per observation.
    unique = {}
    for row in table:
        obs = str(row["obs_id"])
        if obs not in unique or float(row["t_min"]) < float(unique[obs]["t_min"]):
            unique[obs] = row
    rows = sorted(unique.values(), key=lambda row: float(row["t_min"]))
    if not rows:
        raise RuntimeError(f"IRSA returned no SPHEREx {band} images at this position.")
    return rows


def _local_wavelength(hdu, ra, dec):
    image = hdu["IMAGE"]
    x, y = WCS(image.header, naxis=2).world_to_pixel_values(ra, dec)
    record = hdu["WCS-WAVE"].data[0]
    # WCS-WAVE coordinates are in the original detector frame, not cutout pixels.
    ox = x + 2 - image.header["CRPIX1A"]
    oy = y + 2 - image.header["CRPIX2A"]
    wave = RegularGridInterpolator(
        (record["Y"], record["X"]),
        np.asarray(record["VALUES"], dtype=float)[:, :, 0],
        bounds_error=False,
        fill_value=np.nan,
    )([[oy, ox]])[0]
    return float(x), float(y), float(wave)


def _download(row, directory, ra, dec, size_arcsec):
    obs_id = str(row["obs_id"])
    path = directory / f"{obs_id}.fits"
    url = (
        str(row["access_url"])
        + "?"
        + urlencode({"center": f"{ra:.8f},{dec:.8f}", "size": f"{size_arcsec / 3600:.6f}"})
    )
    if not path.exists():
        last_error = None
        for attempt in range(4):
            try:
                with urlopen(url, timeout=90) as response:
                    payload = response.read()
                partial = path.with_suffix(".partial")
                partial.write_bytes(payload)
                with fits.open(partial) as hdus:
                    if "IMAGE" not in hdus or "WCS-WAVE" not in hdus:
                        raise ValueError("IRSA response lacks IMAGE/WCS-WAVE.")
                partial.replace(path)
                last_error = None
                break
            except Exception as exc:  # IRSA sometimes briefly returns HTTP 503.
                last_error = exc
                time.sleep(2**attempt)
        if last_error is not None:
            raise last_error
    with fits.open(path) as hdus:
        x, y, wave = _local_wavelength(hdus, ra, dec)
        mjd = float(hdus["IMAGE"].header["MJD-AVG"])
    return dict(
        obs_id=obs_id,
        path=str(path),
        url=url,
        mjd=mjd,
        date=Time(mjd, format="mjd").isot,
        target_x=x,
        target_y=y,
        target_wavelength_um=wave,
        size_bytes=path.stat().st_size,
    )


def _grid(ra, dec, size, pixel_scale_arcsec):
    wcs = WCS(naxis=2)
    wcs.wcs.crpix = [(size + 1) / 2, (size + 1) / 2]
    wcs.wcs.crval = [ra, dec]
    wcs.wcs.cdelt = [-pixel_scale_arcsec / 3600, pixel_scale_arcsec / 3600]
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    return wcs


def _resample(record, output_wcs, size):
    with fits.open(record["path"]) as hdus:
        image = hdus["IMAGE"]
        wcs = WCS(image.header, fobj=hdus, naxis=2)
        data = np.asarray(image.data, dtype=float) - np.asarray(hdus["ZODI"].data, dtype=float)
        variance = np.asarray(hdus["VARIANCE"].data, dtype=float)
        flags = np.asarray(hdus["FLAGS"].data)
        mask = bad_pixel_mask(flags) | ~np.isfinite(data) | ~np.isfinite(variance) | (variance <= 0)
        projected, footprint = reproject_exact(
            (np.where(mask, np.nan, data), wcs),
            output_wcs,
            shape_out=(size, size),
            return_footprint=True,
        )
        projected_var, var_footprint = reproject_exact(
            (np.where(mask, np.nan, variance), wcs),
            output_wcs,
            shape_out=(size, size),
            return_footprint=True,
        )
        valid = (
            (footprint > 0)
            & (var_footprint > 0)
            & np.isfinite(projected)
            & np.isfinite(projected_var)
            & (projected_var > 0)
        )
        return (
            np.where(valid, projected, np.nan),
            np.where(valid, projected_var, np.inf),
            valid,
        )


def _cluster_visits(records, gap_days=14):
    visits = []
    for record in records:
        if not visits or record["mjd"] - visits[-1][-1]["mjd"] > gap_days:
            visits.append([record])
        else:
            visits[-1].append(record)
    return visits


def build_timelapse(
    output="outputs/timelapse",
    data_dir="data/timelapse_fov176as",
    ra=RA_DEFAULT,
    dec=DEC_DEFAULT,
    band="SPHEREx-D6",
    size_arcsec=176,
    native_pixel_scale_arcsec=6.2,
    wavelength_um=None,
    wavelength_tolerance_um=0.12,
):
    """Fetch a fixed SPHEREx detector band and make one frame per observing visit.

    Only complete consecutive half-year intervals from the first available epoch
    are included. A half-year interval with no matching images is reported.
    """
    output, cache = Path(output), Path(data_dir)
    output.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    query_cache = cache / "archive_query.ecsv"
    old_report_path = output / "timelapse_report.json"
    cached_summary = None
    if query_cache.exists():
        rows = list(Table.read(query_cache, format="ascii.ecsv"))
    else:
        try:
            rows = _query(ra, dec, band)
            Table(rows=rows).write(query_cache, format="ascii.ecsv", overwrite=True)
        except Exception:
            # IRSA can be briefly unavailable; reuse the already downloaded query.
            selected_cache = cache / "query.ecsv"
            if not selected_cache.exists() or not old_report_path.exists():
                raise
            cached_summary = json.loads(old_report_path.read_text())
            rows = list(Table.read(selected_cache, format="ascii.ecsv"))
            print("IRSA is unavailable; reusing the cached 40-image query.", flush=True)
    mjds = np.asarray([float(row["t_min"]) for row in rows])
    start_mjd = float(mjds.min())
    archive_observation_count = len(rows)
    archive_last_mjd = float(mjds.max())
    if cached_summary is not None:
        archive_observation_count = cached_summary["n_archive_observations"]
        complete_periods = cached_summary["complete_half_year_count"]
        archive_last_mjd = Time(cached_summary["available_range"]["last"], format="isot").mjd
    else:
        complete_periods = int(np.floor((archive_last_mjd - start_mjd) / HALF_YEAR_DAYS))
    if complete_periods < 1:
        raise RuntimeError("SPHEREx archive has less than one complete six-month period here.")
    end_mjd = start_mjd + complete_periods * HALF_YEAR_DAYS
    selected = (
        rows
        if cached_summary is not None
        else [row for row in rows if start_mjd <= float(row["t_min"]) <= end_mjd]
    )
    Table(rows=selected).write(cache / "query.ecsv", format="ascii.ecsv", overwrite=True)

    downloaded, errors = [], []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            pool.submit(_download, row, cache, ra, dec, size_arcsec): row for row in selected
        }
        for future in as_completed(futures):
            try:
                downloaded.append(future.result())
            except Exception as exc:
                errors.append({"obs_id": str(futures[future]["obs_id"]), "error": str(exc)})
    downloaded.sort(key=lambda record: record["mjd"])
    periods = []
    for i in range(complete_periods):
        left, right = start_mjd + i * HALF_YEAR_DAYS, start_mjd + (i + 1) * HALF_YEAR_DAYS
        periods.append(
            dict(
                index=i + 1,
                start=Time(left, format="mjd").isot,
                end=Time(right, format="mjd").isot,
            )
        )
    # D6 spans 4.4–5.0 µm and is a linear-variable filter: the central pixel's
    # effective wavelength changes with scan position. Choose the narrow slice
    # with the most balanced coverage across all complete half-year periods.
    # WISE W2 (4.6 µm) is used only as a tie-break preference; exact W2-like
    # coverage is absent in the first six-month period at this target.
    available_waves = np.asarray(
        [r["target_wavelength_um"] for r in downloaded if np.isfinite(r["target_wavelength_um"])]
    )
    if wavelength_um is None:
        best = None
        for center in np.linspace(float(available_waves.min()), float(available_waves.max()), 301):
            counts = [
                sum(
                    left <= r["mjd"] < right
                    and abs(r["target_wavelength_um"] - center) <= wavelength_tolerance_um
                    for r in downloaded
                )
                for left, right in [
                    (start_mjd + i * HALF_YEAR_DAYS, start_mjd + (i + 1) * HALF_YEAR_DAYS)
                    for i in range(complete_periods)
                ]
            ]
            score = (min(counts), sum(counts), -abs(center - 4.6))
            if best is None or score > best[0]:
                best = (score, float(center), counts)
        wavelength_um = best[1]
    matched = [
        record
        for record in downloaded
        if np.isfinite(record["target_wavelength_um"])
        and abs(record["target_wavelength_um"] - wavelength_um) <= wavelength_tolerance_um
    ]
    for period in periods:
        left = Time(period["start"], format="isot").mjd
        right = Time(period["end"], format="isot").mjd
        period["n_images"] = int(sum(left <= r["mjd"] < right for r in matched))
    coverage = dict(
        complete_six_month_periods=periods,
        target_wavelengths_um=[r["target_wavelength_um"] for r in downloaded],
        downloads=len(downloaded),
        failures=errors,
    )
    (output / "wavelength_coverage.json").write_text(json.dumps(coverage, indent=2))
    if any(period["n_images"] == 0 for period in periods):
        raise RuntimeError(
            "At least one complete six-month period has no wavelength-matched SPHEREx image; "
            "see outputs/timelapse/timelapse_report.json for wavelength coverage."
        )

    # WiseView's `size=176` is a 176-arcsecond field of view, not 176 pixels.
    # Keep SPHEREx at native sampling rather than inventing pixels by upsampling.
    image_size = max(1, int(round(size_arcsec / native_pixel_scale_arcsec)))
    pixel_scale_arcsec = size_arcsec / image_size
    output_wcs = _grid(ra, dec, image_size, pixel_scale_arcsec)
    visits = _cluster_visits(matched)
    epoch_frames, frame_records = [], []
    mosaic_dir = output / "mosaics"
    mosaic_dir.mkdir(parents=True, exist_ok=True)
    for visit_index, visit in enumerate(visits, 1):
        samples, variances, footprints = [], [], []
        for record in visit:
            data, var, footprint = _resample(record, output_wcs, image_size)
            samples.append(data)
            variances.append(var)
            footprints.append(footprint)
        cube, varcube = np.asarray(samples), np.asarray(variances)
        weights = np.where(np.isfinite(cube) & np.isfinite(varcube) & (varcube > 0), 1 / varcube, 0)
        numerator = np.sum(np.nan_to_num(cube) * weights, axis=0)
        total_weight = weights.sum(axis=0)
        coadd = np.divide(
            numerator,
            total_weight,
            out=np.full((image_size, image_size), np.nan),
            where=total_weight > 0,
        )
        nhits = np.sum(np.asarray(footprints), axis=0).astype(np.uint16)
        epoch_frames.append(coadd)
        mosaic_header = output_wcs.to_header()
        mosaic_header["BUNIT"] = "MJy/sr"
        mosaic_header["DATE-OBS"] = Time(visit[0]["mjd"], format="mjd").isot
        mosaic_header["DATE-END"] = Time(visit[-1]["mjd"], format="mjd").isot
        mosaic_header["WAVELEN"] = float(np.mean([r["target_wavelength_um"] for r in visit]))
        mosaic_header["NCOMBINE"] = len(visit)
        mosaic_header["REPROJ"] = "reproject_exact"
        mosaic_path = mosaic_dir / f"visit_{visit_index:02d}.fits"
        fits.HDUList(
            [
                fits.PrimaryHDU(data=coadd.astype(np.float32), header=mosaic_header),
                fits.ImageHDU(data=nhits, name="NHITS"),
            ]
        ).writeto(mosaic_path, overwrite=True)
        frame_records.append(
            dict(
                frame=visit_index,
                date_start=Time(visit[0]["mjd"], format="mjd").isot,
                date_end=Time(visit[-1]["mjd"], format="mjd").isot,
                mjd=float(np.mean([r["mjd"] for r in visit])),
                n_images=len(visit),
                mean_wavelength_um=float(np.mean([r["target_wavelength_um"] for r in visit])),
                obs_ids=[r["obs_id"] for r in visit],
                mosaic=str(mosaic_path),
            )
        )
        for record in visit:
            record["gif_frame"] = visit_index
            record["included_in_gif"] = True
            record["exclusion_reason"] = ""
    matched_ids = {record["obs_id"] for record in matched}
    for record in downloaded:
        if record["obs_id"] not in matched_ids:
            record["gif_frame"] = ""
            record["included_in_gif"] = False
            record["exclusion_reason"] = "effective wavelength outside selected comparable range"
    cube = np.asarray(epoch_frames)
    finite = cube[np.isfinite(cube)]
    vmin, vmax = map(float, np.percentile(finite, [1, 99.7]))
    if vmax <= vmin:
        raise RuntimeError("No displayable variation in the aligned time-series coadds.")

    gif = output / "spherex_wiseview.gif"
    fig, ax = plt.subplots(figsize=(6, 6), layout="constrained")
    artist = ax.imshow(
        cube[0], origin="lower", cmap="gray_r", vmin=vmin, vmax=vmax, interpolation="bilinear"
    )
    ax.set_xlabel("pixel (common sky grid)")
    ax.set_ylabel("pixel (common sky grid)")

    def update(i):
        artist.set_data(cube[i])
        frame = frame_records[i]
        ax.set_title(
            f"SPHEREx {band} • {frame['date_start'][:10]}–{frame['date_end'][:10]}\n"
            f"Visita {i + 1}/{len(frame_records)} • coadd de {frame['n_images']} imagens • "
            f"λ={frame['mean_wavelength_um']:.3f} µm"
        )
        return (artist,)

    animation.FuncAnimation(fig, update, frames=len(frame_records), interval=750, blit=False).save(
        gif, writer=animation.PillowWriter(fps=1.5)
    )
    plt.close(fig)

    # Fixed-scale contact sheet makes the complete sequence inspectable without animation.
    cols = min(4, len(cube))
    rows_n = int(np.ceil(len(cube) / cols))
    fig, axes = plt.subplots(
        rows_n, cols, figsize=(4 * cols, 4 * rows_n), squeeze=False, layout="constrained"
    )
    for i, ax in enumerate(axes.flat):
        if i >= len(cube):
            ax.axis("off")
            continue
        ax.imshow(
            cube[i],
            origin="lower",
            cmap="gray_r",
            vmin=vmin,
            vmax=vmax,
            interpolation="bilinear",
        )
        f = frame_records[i]
        ax.set_title(f"{f['date_start'][:10]}–{f['date_end'][:10]}\n{f['n_images']} exposições")
        ax.set_xticks([])
        ax.set_yticks([])
    sheet = output / "spherex_wiseview_frames.png"
    fig.savefig(sheet, dpi=150)
    plt.close(fig)

    inventory = output / "observations.csv"
    with inventory.open("w", newline="", encoding="utf-8") as handle:
        columns = [
            "obs_id",
            "date",
            "target_wavelength_um",
            "included_in_gif",
            "gif_frame",
            "exclusion_reason",
            "path",
            "url",
        ]
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows({key: record.get(key, "") for key in columns} for record in downloaded)

    report = dict(
        source="SPHEREx DR1 via Astroquery IRSA SIA",
        wiseview_reference=(
            "WISEview-style: 176-arcsecond field, inverted grayscale, fixed display stretch"
        ),
        target=dict(ra_deg=ra, dec_deg=dec),
        spherex_band=band,
        wavelength_filter=dict(
            center_um=wavelength_um,
            tolerance_um=wavelength_tolerance_um,
            selection=(
                "Most balanced coverage across all full six-month periods; 4.6 µm preferred on ties"
            ),
        ),
        output_pixel_grid=dict(
            size_pixels=image_size,
            field_of_view_arcsec=size_arcsec,
            pixel_scale_arcsec=pixel_scale_arcsec,
            aligned_to_fixed_sky=True,
            reprojection=(
                "reproject_exact area-overlap before inverse-variance coaddition"
            ),
            note="Native-sampling grid; SPHEREx pixels are larger than WISE pixels",
        ),
        available_range=dict(
            start=Time(start_mjd, format="mjd").isot,
            last=Time(archive_last_mjd, format="mjd").isot,
        ),
        complete_six_month_periods=periods,
        complete_half_year_count=complete_periods,
        n_archive_observations=archive_observation_count,
        n_period_observations=len(selected),
        n_archive_observations_outside_complete_periods=archive_observation_count - len(selected),
        n_downloaded=len(downloaded),
        n_wavelength_matched=len(matched),
        n_downloaded_not_in_gif=len(downloaded) - len(matched),
        n_visits=len(frame_records),
        frame_records=frame_records,
        observations=downloaded,
        errors=errors,
        fixed_linear_display_limits=[vmin, vmax],
        files=dict(
            gif=str(gif),
            contact_sheet=str(sheet),
            epoch_mosaics=str(mosaic_dir),
            manifest=str(output / "timelapse_report.json"),
            exposure_inventory=str(inventory),
        ),
    )
    (output / "timelapse_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    np.savez_compressed(output / "timelapse_frames.npz", images=cube, vmin=vmin, vmax=vmax)
    print(
        json.dumps(
            {
                k: report[k]
                for k in [
                    "complete_six_month_periods",
                    "n_archive_observations",
                    "n_downloaded",
                    "n_wavelength_matched",
                    "files",
                    "n_visits",
                ]
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return report
