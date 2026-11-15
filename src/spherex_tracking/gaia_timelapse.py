"""Gaia DR3 catalog-position animation (astrometric model, not images)."""

import json
from pathlib import Path

import matplotlib
import numpy as np
from astropy.table import Table
from astropy.time import Time

matplotlib.use("Agg")
from matplotlib import animation  # noqa: E402
from matplotlib import pyplot as plt

RA_DEFAULT = 133.786245
DEC_DEFAULT = -7.244372
FOV_ARCSEC = 176.0
GAIA_DR3_START = "2014-07-25"
GAIA_DR3_END = "2017-05-28"


def _query_sources(ra, dec, fov_arcsec):
    from astroquery.gaia import Gaia

    radius = fov_arcsec / 2 / 3600
    query = f"""
        SELECT source_id, ra, dec, ref_epoch, pmra, pmdec,
               phot_g_mean_mag, ruwe
        FROM gaiadr3.gaia_source
        WHERE 1=CONTAINS(POINT('ICRS', ra, dec),
                         CIRCLE('ICRS', {ra}, {dec}, {radius}))
          AND phot_g_mean_mag < 20
    """
    job = Gaia.launch_job_async(query, dump_to_file=False)
    return job.get_results(), query


def build_gaia_timelapse(
    output="outputs/gaia_timelapse",
    data_dir="data/gaia_timelapse",
    ra=RA_DEFAULT,
    dec=DEC_DEFAULT,
    fov_arcsec=FOV_ARCSEC,
    n_frames=8,
):
    """Animate actual Gaia DR3 proper-motion solutions over its 34-month span."""
    output, data_dir = Path(output), Path(data_dir)
    output.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    catalog_path = data_dir / "gaia_dr3_sources.ecsv"
    query_path = data_dir / "gaia_query.adql"
    if catalog_path.exists() and query_path.exists():
        catalog = Table.read(catalog_path, format="ascii.ecsv")
        query = query_path.read_text()
    else:
        catalog, query = _query_sources(ra, dec, fov_arcsec)
        catalog.write(catalog_path, format="ascii.ecsv", overwrite=True)
        query_path.write_text(query)
    if len(catalog) == 0:
        raise RuntimeError("Gaia DR3 returned no G<20 sources in this field.")

    ra0, dec0 = float(ra), float(dec)
    source_ra = np.asarray(catalog["ra"], dtype=float)
    source_dec = np.asarray(catalog["dec"], dtype=float)
    pmra = np.nan_to_num(np.asarray(catalog["pmra"], dtype=float), nan=0.0)
    pmdec = np.nan_to_num(np.asarray(catalog["pmdec"], dtype=float), nan=0.0)
    ref_epoch = np.asarray(catalog["ref_epoch"], dtype=float)
    gmag = np.asarray(catalog["phot_g_mean_mag"], dtype=float)
    # Tangent-plane positions around the user-provided coordinates, in arcsec.
    x0 = (source_ra - ra0) * np.cos(np.deg2rad(dec0)) * 3600
    y0 = (source_dec - dec0) * 3600
    dates = Time([GAIA_DR3_START, GAIA_DR3_END], format="iso")
    years = np.linspace(dates[0].jyear, dates[1].jyear, n_frames)
    x_frames = np.array([x0 + pmra * (year - ref_epoch) / 1000 for year in years])
    y_frames = np.array([y0 + pmdec * (year - ref_epoch) / 1000 for year in years])

    speed = np.hypot(pmra, pmdec)
    fastest = int(np.argmax(speed))
    displacement = float(speed[fastest] * (years[-1] - years[0]) / 1000)
    g = np.where(np.isfinite(gmag), gmag, np.nanmax(gmag))
    marker_sizes = 18 + 50 * np.clip((20 - g) / 12, 0, 1)

    gif = output / "gaia_dr3_motion.gif"
    fig, (field_ax, zoom_ax) = plt.subplots(1, 2, figsize=(10, 5), layout="constrained")
    fig.patch.set_facecolor("#080b12")
    for ax in (field_ax, zoom_ax):
        ax.set_facecolor("#080b12")
        ax.tick_params(colors="#dce5f5", labelsize=8)
        for spine in ax.spines.values():
            spine.set_color("#64748b")
        ax.xaxis.label.set_color("#dce5f5")
        ax.yaxis.label.set_color("#dce5f5")
        ax.title.set_color("#f8fafc")
    field_scatter = field_ax.scatter(
        x_frames[0], y_frames[0], s=marker_sizes, c=gmag, cmap="plasma_r", vmin=8, vmax=20
    )
    field_ax.set_xlim(-fov_arcsec / 2, fov_arcsec / 2)
    field_ax.set_ylim(-fov_arcsec / 2, fov_arcsec / 2)
    field_ax.set_aspect("equal")
    field_ax.set_xlabel("ΔRA cos(dec) [arcsec]")
    field_ax.set_ylabel("ΔDec [arcsec]")
    field_ax.set_title(f"Campo Gaia DR3 • {fov_arcsec:.0f}″ • {len(catalog)} fontes")
    field_note = field_ax.text(
        0.02,
        0.98,
        "Posições do catálogo, não fotos por época\nMovimento quase invisível nesta escala",
        transform=field_ax.transAxes,
        va="top",
        fontsize=8,
        color="#cbd5e1",
        bbox={"facecolor": "#111827", "alpha": 0.8, "edgecolor": "none"},
    )

    zoom_x = pmra[fastest] * (years - ref_epoch[fastest]) / 1000
    zoom_y = pmdec[fastest] * (years - ref_epoch[fastest]) / 1000
    pad = max(displacement * 0.25, 0.002)
    zoom_ax.plot(zoom_x, zoom_y, color="#64748b", lw=1, zorder=1)
    (zoom_marker,) = zoom_ax.plot(
        [zoom_x[0]], [zoom_y[0]], marker="o", ms=10, color="#38bdf8", mec="white", zorder=2
    )
    zoom_ax.set_xlim(float(zoom_x.min() - pad), float(zoom_x.max() + pad))
    zoom_ax.set_ylim(float(zoom_y.min() - pad), float(zoom_y.max() + pad))
    zoom_ax.set_aspect("equal", adjustable="datalim")
    zoom_ax.set_xlabel("ΔRA cos(dec) desde J2016 [arcsec]")
    zoom_ax.set_ylabel("ΔDec desde J2016 [arcsec]")
    short_id = str(int(catalog["source_id"][fastest]))[-6:]
    zoom_ax.set_title(
        f"Zoom: fonte Gaia …{short_id}\n"
        f"µ={speed[fastest]:.1f} mas/ano • deslocamento={displacement:.3f}″"
    )
    title = fig.suptitle(
        "Gaia DR3 • movimento próprio projetado ao longo de 34 meses", color="#f8fafc"
    )

    def update(i):
        field_scatter.set_offsets(np.column_stack((x_frames[i], y_frames[i])))
        zoom_marker.set_data([zoom_x[i]], [zoom_y[i]])
        field_ax.set_title(
            f"Campo Gaia DR3 • {fov_arcsec:.0f}″ • {len(catalog)} fontes • "
            f"{Time(years[i], format='jyear').isot[:10]}"
        )
        return field_scatter, zoom_marker, field_note, title

    animation.FuncAnimation(fig, update, frames=len(years), interval=500, blit=False).save(
        gif, writer=animation.PillowWriter(fps=2)
    )
    plt.close(fig)

    report = dict(
        source="Gaia DR3 gaiadr3.gaia_source via Astroquery Gaia TAP",
        target=dict(ra_deg=ra0, dec_deg=dec0),
        field_of_view_arcsec=fov_arcsec,
        gaia_dr3_observation_span=dict(start=GAIA_DR3_START, end=GAIA_DR3_END, months=34),
        n_sources=int(len(catalog)),
        source_ids=[int(value) for value in catalog["source_id"]],
        fastest_source_id=int(catalog["source_id"][fastest]),
        fastest_pm_mas_per_year=float(speed[fastest]),
        fastest_displacement_arcsec_over_span=displacement,
        visualization=(
            "Catalogue positions propagated from Gaia DR3 proper motions; not epoch images"
        ),
        files=dict(gif=str(gif), catalog=str(catalog_path), query=str(query_path)),
    )
    (output / "gaia_timelapse_report.json").write_text(json.dumps(report, indent=2))
    summary_keys = [
        "n_sources",
        "gaia_dr3_observation_span",
        "fastest_pm_mas_per_year",
        "fastest_displacement_arcsec_over_span",
        "files",
    ]
    print(json.dumps({key: report[key] for key in summary_keys}, indent=2))
    return report
