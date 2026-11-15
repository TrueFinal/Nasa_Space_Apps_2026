"""Native-pixel infrared selection and aperture measurements; no spectral interpolation."""

from __future__ import annotations

import csv
import hashlib
import json
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path

import astropy.units as u
import numpy as np
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.time import Time
from astropy.wcs import WCS
from erfa import ErfaWarning

from .infrared_bands import DETECTOR_BANDS, MAX_EXPOSURES, detectors_for, spectral_coverage
from .infrared_display import prepare_plate

BAD_FLAGS = 0x0A02CEC7
ADVISORY_FLAGS = 0x15D80000
KNOWN_FLAGS = BAD_FLAGS | ADVISORY_FLAGS | 0x00201000
MASK_BITS = {
    "invalid": 1,
    "instrument": 2,
    "outside_band": 4,
    "gaia": 8,
    "no_calibration": 16,
    "advisory": 32,
    "target_aperture": 64,
}
REJECT_BITS = 1 | 2 | 4 | 8 | 16


@dataclass(frozen=True)
class MaskConfig:
    low_um: float = 0.75
    high_um: float = 5.0
    max_exposures: int = 12
    detector: int = 0
    aperture_px: float = 2.0
    annulus_inner_px: float = 4.0
    annulus_outer_px: float = 7.0
    gaia_radius_arcsec: float = 12.4
    gaia_max_g: float = 19.0
    subtract_zodi: bool = True

    def __post_init__(self):
        values = list(asdict(self).values())
        if not all(np.isfinite(x) for x in values):
            raise ValueError("Parâmetros devem ser finitos.")
        if not 0.75 <= self.low_um < self.high_um <= 5.0:
            raise ValueError("A janela deve estar na cobertura SPHEREx: 0,75–5,00 µm.")
        if (
            not 1 <= self.max_exposures <= MAX_EXPOSURES
            or int(self.max_exposures) != self.max_exposures
        ):
            raise ValueError(f"Selecione de uma a {MAX_EXPOSURES} exposições.")
        if self.detector not in range(7) or not detectors_for(
            self.low_um, self.high_um, self.detector
        ):
            raise ValueError("Detector não é compatível com a janela solicitada.")
        if not 0.5 <= self.aperture_px < self.annulus_inner_px < self.annulus_outer_px <= 30:
            raise ValueError("Abertura e anel de fundo inválidos.")
        if not 0 < self.gaia_radius_arcsec <= 120 or not 0 < self.gaia_max_g <= 25:
            raise ValueError("Parâmetros Gaia inválidos.")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path, value):
    Path(path).write_text(
        json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2), encoding="utf-8"
    )


def _midtime(header):
    if "MJD-AVG" in header:
        mjd = float(header["MJD-AVG"])
    elif "MJD-BEG" in header and "MJD-END" in header:
        mjd = (float(header["MJD-BEG"]) + float(header["MJD-END"])) / 2
    else:
        raise ValueError("FITS sem MJD-AVG ou MJD-BEG/END; DATE não é época da exposição.")
    scale = str(header.get("TIMESYS", "UTC")).lower()
    time = Time(mjd, format="mjd", scale=scale)
    return time


def spectral_maps(hdul, image_header, shape, calibration_path=None, coordinates=None):
    """Map CWAVE/CBAND to cutout pixels via the FITS alternate A WCS (origin=0).

    coordinates is required if external calibration does not declare DETCOORD.
    'cutout' means explicitly pre-aligned maps. WCS-WAVE is never a science fallback.
    """
    local = "CWAVE" in hdul and "CBAND" in hdul
    if local:
        source = hdul
    elif calibration_path:
        source = fits.open(calibration_path, memmap=False)
    else:
        raise ValueError("CWAVE e CBAND obrigatórios: WCS-WAVE serve apenas para visualização.")
    try:
        wave = np.array(source["CWAVE"].data, dtype=float)
        width = np.array(source["CBAND"].data, dtype=float)
        for name in ("CWAVE", "CBAND"):
            unit = source[name].header.get("BUNIT")
            if not unit:
                raise ValueError(f"{name} sem BUNIT: informe mapas calibrados em µm.")
            factor = u.Unit(unit).to(u.um)
            if name == "CWAVE":
                wave *= factor
            else:
                width *= factor
        if wave.shape != width.shape or wave.ndim != 2:
            raise ValueError("CWAVE/CBAND devem ser mapas bidimensionais com a mesma forma.")
        declared = source["CWAVE"].header.get("DETCOORD", source[0].header.get("DETCOORD"))
        cal_coord = str(coordinates or declared or ("cutout" if local else "")).lower()
        if declared and coordinates and str(declared).lower() != coordinates:
            raise ValueError("DETCOORD da calibração conflita com o manifesto.")
        cal_detector = source["CWAVE"].header.get("DETECTOR", source[0].header.get("DETECTOR"))
        if cal_detector is not None and int(cal_detector) != int(image_header["DETECTOR"]):
            raise ValueError("Calibração pertence a outro detector.")
        if cal_coord == "cutout":
            if wave.shape != shape:
                raise ValueError("Mapas cutout não correspondem à forma da imagem.")
            return wave, width
        image_coord = str(image_header.get("DETCOORD", "")).lower()
        if cal_coord not in ("sky", "detector") or image_coord not in ("sky", "detector"):
            raise ValueError("Declare DETCOORD: sky ou detector para alinhar a calibração.")
        if "CTYPE1A" not in image_header:
            raise ValueError("Recorte sem WCS alternativo A para localizar pixels do detector.")
        alt_header = image_header.copy()
        for key in list(alt_header):
            if key.startswith(("A_", "B_", "AP_", "BP_")):
                del alt_header[key]
        alt = WCS(alt_header, key="A", naxis=2)
        alt.sip = None
        yy, xx = np.indices(shape)
        dx, dy = alt.all_pix2world(xx, yy, 0)
        if cal_coord != image_coord and int(image_header["DETECTOR"]) in (4, 5, 6):
            dx = wave.shape[1] - 1 - dx
        ix, iy = np.rint(dx).astype(int), np.rint(dy).astype(int)
        # Calibration samples are detector pixels, not an interpolated spectral cube.
        inside = (ix >= 0) & (iy >= 0) & (ix < wave.shape[1]) & (iy < wave.shape[0])
        aligned_wave = np.full(shape, np.nan)
        aligned_width = np.full(shape, np.nan)
        aligned_wave[inside] = wave[iy[inside], ix[inside]]
        aligned_width[inside] = width[iy[inside], ix[inside]]
        return aligned_wave, aligned_width
    finally:
        if not local:
            source.close()


def gaia_positions(catalogue, time, wcs):
    """Gaia DR3 barycentric ICRS positions, propagated from the catalogue epoch."""
    output = []
    for row in catalogue:
        try:
            ra, dec = float(row["ra"]), float(row["dec"])
        except (ValueError, TypeError, KeyError):
            continue
        if not np.isfinite(ra + dec) or not 0 <= ra < 360 or not -90 <= dec <= 90:
            continue
        pmra, pmdec = row.get("pmra"), row.get("pmdec")
        has_pm = bool(
            pmra is not None
            and pmdec is not None
            and np.isfinite(float(pmra))
            and np.isfinite(float(pmdec))
        )
        if has_pm:
            coord = SkyCoord(
                ra=ra * u.deg,
                dec=dec * u.deg,
                pm_ra_cosdec=float(pmra) * u.mas / u.yr,
                pm_dec=float(pmdec) * u.mas / u.yr,
                obstime=Time(float(row.get("ref_epoch", 2016.0)), format="jyear"),
            )
            with warnings.catch_warnings():
                # Catalogue-only angular propagation has no measured distance here.
                # ERFA's distance substitution is expected; no parallax is claimed.
                warnings.filterwarnings(
                    "ignore",
                    message='ERFA function "pmsafe".*distance overridden',
                    category=ErfaWarning,
                )
                coord = coord.apply_space_motion(new_obstime=time)
        else:
            coord = SkyCoord(ra=ra * u.deg, dec=dec * u.deg)
        x, y = wcs.world_to_pixel(coord)
        if not np.isfinite(x + y):
            continue
        output.append(
            {
                "source_id": str(row.get("source_id", "")),
                "x": float(x),
                "y": float(y),
                "ra": float(coord.ra.deg),
                "dec": float(coord.dec.deg),
                "g": row.get("phot_g_mean_mag"),
                "proper_motion_applied": has_pm,
            }
        )
    return output


def _weights(shape, x, y, radius, subsamples=5):
    yy, xx = np.indices(shape)
    result = np.zeros(shape)
    for oy in (np.arange(subsamples) + 0.5) / subsamples - 0.5:
        for ox in (np.arange(subsamples) + 0.5) / subsamples - 0.5:
            result += (xx + ox - x) ** 2 + (yy + oy - y) ** 2 <= radius**2
    return result / subsamples**2


def _solid_angles(wcs, shape):
    yy, xx = np.indices(shape)
    center = wcs.pixel_to_world(xx, yy)
    right = wcs.pixel_to_world(xx + 0.5, yy)
    left = wcs.pixel_to_world(xx - 0.5, yy)
    top = wcs.pixel_to_world(xx, yy + 0.5)
    bottom = wcs.pixel_to_world(xx, yy - 0.5)
    dx1, dy1 = center.spherical_offsets_to(right)
    dx0, dy0 = center.spherical_offsets_to(left)
    ex1, ey1 = center.spherical_offsets_to(top)
    ex0, ey0 = center.spherical_offsets_to(bottom)
    return np.abs((dx1 - dx0).rad * (ey1 - ey0).rad - (dy1 - dy0).rad * (ex1 - ex0).rad)


def aperture_measure(science, variance, mask, wave, width, wcs, x, y, cfg):
    """Uncorrected aperture flux in µJy. No PSF correction or detection claim."""
    empty = {
        "flux_ujy": None,
        "error_ujy": None,
        "snr": None,
        "background_mjysr": None,
        "lambda_um": None,
        "bandwidth_um": None,
        "coverage": 0.0,
    }
    if not np.isfinite(x + y) or x < 0 or y < 0 or x >= science.shape[1] or y >= science.shape[0]:
        return {**empty, "status": "target_outside_image"}
    if (
        x - cfg.annulus_outer_px < -0.5
        or y - cfg.annulus_outer_px < -0.5
        or x + cfg.annulus_outer_px > science.shape[1] - 0.5
        or y + cfg.annulus_outer_px > science.shape[0] - 0.5
    ):
        return {**empty, "status": "aperture_or_background_at_edge"}
    ap = _weights(science.shape, x, y, cfg.aperture_px)
    accepted = (mask & REJECT_BITS) == 0
    coverage = float(np.clip(ap[accepted].sum() / ap.sum(), 0, 1))
    empty["coverage"] = coverage
    # Do not inflate partial-aperture flux into an apparent total flux.
    if coverage < 0.999:
        return {**empty, "status": "masked_aperture"}
    yy, xx = np.indices(science.shape)
    rr = np.hypot(xx - x, yy - y)
    ann = (rr >= cfg.annulus_inner_px) & (rr <= cfg.annulus_outer_px) & accepted
    if ann.sum() < 20:
        return {**empty, "status": "insufficient_background"}
    bkg = float(np.median(science[ann]))
    robust_sigma = float(1.4826 * np.median(np.abs(science[ann] - bkg)))
    # Median uncertainty under independent Gaussian noise, conservatively using
    # the larger empirical scatter or supplied per-pixel variance in the annulus.
    bkg_var = np.pi / 2 * max(robust_sigma**2, float(np.median(variance[ann]))) / ann.sum()
    inside = ap > 0
    conversion = _solid_angles(wcs, science.shape) * 1e12  # MJy/sr -> µJy/pixel
    weights = ap[inside] * conversion[inside]
    flux = float(np.sum(weights * (science[inside] - bkg)))
    var = float(np.sum(weights**2 * variance[inside]) + weights.sum() ** 2 * bkg_var)
    err = float(np.sqrt(var))
    return {
        "status": "aperture_measurement",
        "coverage": coverage,
        "flux_ujy": flux,
        "error_ujy": err,
        "snr": flux / err if err > 0 else None,
        "background_mjysr": bkg,
        "lambda_um": float(np.average(wave[inside], weights=ap[inside])),
        "bandwidth_um": float(np.average(width[inside], weights=ap[inside])),
    }


def _array_json(array):
    # JSON has no NaN. Invalid pixels stay null, never zero-valued observations.
    a = np.asarray(array)
    return np.where(np.isfinite(a), a, None).tolist()


def process_frame(entry, cfg, base, output, gaia):
    path = (base / entry["fits"]).resolve()
    cal_path = (base / entry["calibration"]).resolve() if entry.get("calibration") else None
    with fits.open(path, memmap=False) as hdul:
        image = np.array(hdul["IMAGE"].data, dtype=float)
        h = hdul["IMAGE"].header.copy()
        if image.ndim != 2 or max(image.shape) > 256:
            raise ValueError("Use recortes bidimensionais de até 256 × 256 pixels.")
        detector = int(h.get("DETECTOR", -1))
        if detector not in DETECTOR_BANDS:
            raise ValueError("FITS deve identificar um detector SPHEREx D1–D6.")
        if cfg.detector and detector != cfg.detector:
            raise ValueError("O detector do FITS difere do detector solicitado.")
        if not u.Unit(h.get("BUNIT", "")).is_equivalent(u.MJy / u.sr):
            raise ValueError("IMAGE deve informar BUNIT de brilho superficial (MJy/sr).")
        factor = u.Unit(h["BUNIT"]).to(u.MJy / u.sr)
        image *= factor
        variance = np.array(hdul["VARIANCE"].data, dtype=float) * factor**2
        if hdul["VARIANCE"].header.get("BUNIT"):
            variance = np.array(hdul["VARIANCE"].data, dtype=float) * u.Unit(
                hdul["VARIANCE"].header["BUNIT"]
            ).to((u.MJy / u.sr) ** 2)
        flags = np.array(hdul["FLAGS"].data).astype(np.uint32)
        if variance.shape != image.shape or flags.shape != image.shape:
            raise ValueError("IMAGE, VARIANCE e FLAGS devem estar alinhados.")
        time = _midtime(h)
        wcs = WCS(h).celestial
        if not wcs.has_celestial:
            raise ValueError("WCS celeste ausente.")
        wave, width = spectral_maps(
            hdul, h, image.shape, cal_path, entry.get("calibration_coordinates")
        )
        science = image.copy()
        zodi_subtracted = cfg.subtract_zodi and "ZODI" in hdul
        if zodi_subtracted:
            zodi = np.array(hdul["ZODI"].data, dtype=float)
            zunit = hdul["ZODI"].header.get("BUNIT", h["BUNIT"])
            if zodi.shape != image.shape:
                raise ValueError("ZODI não está alinhado com IMAGE.")
            science -= zodi * u.Unit(zunit).to(u.MJy / u.sr)
        mask = np.zeros(image.shape, np.uint16)
        mask[~np.isfinite(science) | ~np.isfinite(variance) | (variance <= 0)] |= 1
        mask[(flags & BAD_FLAGS) != 0] |= 2
        cal_valid = np.isfinite(wave) & np.isfinite(width) & (width > 0) & (wave > 0)
        mask[~cal_valid] |= 16
        mask[(wave < cfg.low_um) | (wave >= cfg.high_um)] |= 4
        mask[(flags & ADVISORY_FLAGS) != 0] |= 32
        stars = gaia_positions(gaia, time, wcs)
        yy, xx = np.indices(image.shape)
        sky = wcs.pixel_to_world(xx, yy)
        for star in stars:
            if star["g"] is None or star["g"] <= cfg.gaia_max_g:
                coord = SkyCoord(star["ra"] * u.deg, star["dec"] * u.deg)
                mask[sky.separation(coord).arcsec <= cfg.gaia_radius_arcsec] |= 8
        target = entry["target"]
        if target.get("frame", "ICRS").upper() != "ICRS":
            raise ValueError("O manifesto deve fornecer posições do alvo em ICRS.")
        if (
            not np.isfinite(float(target["mjd"]))
            or abs(float(target["mjd"]) - time.utc.mjd) * 86400 > 60
        ):
            raise ValueError(
                "Posição prevista deve corresponder ao ponto médio da exposição (tolerância 60 s)."
            )
        ra, dec = float(target["ra"]), float(target["dec"])
        if not np.isfinite(ra + dec) or not 0 <= ra < 360 or not -90 <= dec <= 90:
            raise ValueError("Coordenadas ICRS do alvo inválidas.")
        x, y = (float(v) for v in wcs.world_to_pixel(SkyCoord(ra * u.deg, dec * u.deg)))
        mask[_weights(image.shape, x, y, cfg.aperture_px) > 0] |= 64
        measurement = aperture_measure(science, variance, mask, wave, width, wcs, x, y, cfg)
        valid = (mask & REJECT_BITS) == 0
        idx = int(entry["index"])
        stem = f"exposure_{idx:02d}"
        h["BUNIT"] = "MJy/sr"
        h["BANDLO"] = cfg.low_um
        h["BANDHI"] = cfg.high_um
        h["ZODISUB"] = zodi_subtracted
        h["BADBITS"] = BAD_FLAGS
        h["REJBITS"] = REJECT_BITS
        h["HISTORY"] = "Zephyr: native pixel CWAVE selection, not a monochromatic reconstruction."
        hdus = [fits.PrimaryHDU(), fits.ImageHDU(image.astype("f4"), h, name="IMAGE")]
        for name, array, unit in (
            ("SCIENCE", science, "MJy/sr"),
            ("MASKED", np.where(valid, science, np.nan), "MJy/sr"),
            ("VARIANCE", variance, "(MJy/sr)^2"),
            ("CWAVE", wave, "um"),
            ("CBAND", width, "um"),
        ):
            hdr = h.copy()
            hdr["BUNIT"] = unit
            hdus.append(fits.ImageHDU(array.astype("f4"), hdr, name=name))
        mh = h.copy()
        mh["BUNIT"] = "bitmask"
        for name, bit in MASK_BITS.items():
            mh[f"HIERARCH MASK {name}"] = bit
        hdus.extend([fits.ImageHDU(mask, mh, name="MASK"), fits.ImageHDU(flags, name="FLAGS")])
        fits_path = output / f"{stem}.fits"
        fits.HDUList(hdus).writeto(fits_path, overwrite=True, checksum=True)
        trajectory = []
        for point in entry.get("trajectory", []):
            tx, ty = wcs.world_to_pixel(
                SkyCoord(float(point["ra"]) * u.deg, float(point["dec"]) * u.deg)
            )
            if np.isfinite(tx + ty):
                trajectory.append({"x": float(tx), "y": float(ty), "mjd": point["mjd"]})
        plate = prepare_plate(
            image, science, mask, wcs, {"x": x, "y": y}, trajectory, stars, float(time.utc.mjd)
        )
        frame = {
            "id": stem,
            "source": path.name,
            "input_sha256": sha256(path),
            "output_sha256": sha256(fits_path),
            "fits": f"files/{stem}.fits",
            "mjd_utc": float(time.utc.mjd),
            "utc": time.utc.isot,
            "detector": detector,
            "instrument": "SPHEREx",
            "nominal_band_um": list(DETECTOR_BANDS[detector]),
            "central_wavelength_um": (
                float(wave[int(np.floor(y + 0.5)), int(np.floor(x + 0.5))])
                if -0.5 <= x < image.shape[1] - 0.5
                and -0.5 <= y < image.shape[0] - 0.5
                and np.isfinite(wave[int(np.floor(y + 0.5)), int(np.floor(x + 0.5))])
                else None
            ),
            "shape": list(image.shape),
            "wcs_header": wcs.to_header(relax=True).tostring(),
            "zodi_subtracted": zodi_subtracted,
            "target": {**target, "x": x, "y": y},
            "trajectory": [p for segment in plate["field_trajectory_segments"] for p in segment],
            "gaia": plate["field_gaia"],
            "plot": plate,
            "measurement": measurement,
            "accepted_fraction": float(valid.mean()),
            "advisory_fraction": float(((mask & 32) != 0).mean()),
            "unknown_flags_fraction": float(
                ((flags & np.uint32(~KNOWN_FLAGS & 0xFFFFFFFF)) != 0).mean()
            ),
            "mask_counts": {
                name: int(((mask & bit) != 0).sum()) for name, bit in MASK_BITS.items()
            },
            "calibration": {
                "source": cal_path.name if cal_path else "embedded CWAVE/CBAND",
                "sha256": sha256(cal_path) if cal_path else sha256(path),
                "coordinates": entry.get("calibration_coordinates", "header"),
            },
            "image": _array_json(image),
            "science": _array_json(science),
            "masked": _array_json(np.where(valid, science, np.nan)),
            "mask": mask.tolist(),
            "wavelength": _array_json(wave),
        }
        return frame


def run_manifest(manifest_path, output_dir, config=None, progress=lambda text: None):
    path = Path(manifest_path).resolve()
    manifest = json.loads(path.read_text(encoding="utf-8"))
    cfg = config or MaskConfig(**manifest.get("config", {}))
    entries = manifest.get("exposures", [])
    if not entries or len(entries) > cfg.max_exposures:
        raise ValueError(f"Manifesto deve conter de 1 a {cfg.max_exposures} exposições.")
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    # Resolve inputs before writing anything: never overwrite an original exposure.
    inputs = [path]
    hashes = []
    for entry in entries:
        image_path = (path.parent / entry["fits"]).resolve()
        inputs.append(image_path)
        hashes.append(sha256(image_path))
        if entry.get("calibration"):
            inputs.append((path.parent / entry["calibration"]).resolve())
    if len(set(hashes)) != len(hashes):
        raise ValueError("Exposições duplicadas não são observações independentes.")
    if any(output in source.parents for source in inputs):
        raise ValueError("A saída deve ficar separada dos FITS originais, calibração e manifesto.")
    frames = []
    gaia = manifest.get("gaia", [])
    gaia_status = manifest.get("gaia_status", "provided" if gaia else "not_supplied")
    catalogue_state = gaia_status.get("status") if isinstance(gaia_status, dict) else gaia_status
    if catalogue_state in ("unavailable", "not_supplied", "error"):
        gaia = []
    trajectory = [
        {"ra": e["target"]["ra"], "dec": e["target"]["dec"], "mjd": e["target"]["mjd"]}
        for e in entries
    ]
    for i, entry in enumerate(entries):
        progress(f"Processando exposição {i + 1}/{len(entries)}")
        frame = process_frame(
            {**entry, "index": i, "trajectory": trajectory},
            cfg,
            path.parent,
            output,
            gaia,
        )
        frames.append(frame)
    frames.sort(key=lambda f: f["mjd_utc"])
    finite = np.concatenate([np.array(f["science"], dtype=float).ravel() for f in frames])
    finite = finite[np.isfinite(finite)]
    contrast = np.percentile(finite, [2, 99.5]).tolist() if len(finite) else [0, 1]
    report = {
        "schema_version": 3,
        "synthetic": bool(manifest.get("synthetic", False)),
        "object": manifest.get("object", "MPC target"),
        "config": asdict(cfg),
        "created_utc": Time.now().utc.isot,
        "manifest_sha256": sha256(path),
        "provenance": manifest.get("provenance", {}),
        "gaia_status": gaia_status,
        "spectral_coverage": spectral_coverage(frames, cfg.low_um, cfg.high_um, cfg.detector),
        "plotting": {
            "method": "SkyShift-style covered MPC crop / shared asinh / display-only sky removal",
            "reference": [
                "skyshift/web/src/learn/data.ts",
                "skyshift/web/src/learn/plate.ts",
                "skyshift/web/src/blink/math.ts",
            ],
            "frame_ids": [f["id"] for f in frames if f["plot"]["eligible"]],
            "excluded": [
                {"id": f["id"], "reason": f["plot"]["reason"]}
                for f in frames
                if not f["plot"]["eligible"]
            ],
            "photometry_resampled": False,
        },
        "mask_bits": MASK_BITS,
        "reject_bits": REJECT_BITS,
        "bad_flags": BAD_FLAGS,
        "advisory_flags": ADVISORY_FLAGS,
        "contrast": contrast,
        "limitations": [
            "MPC fornece órbitas/identificações; as imagens são do arquivo SPHEREx/IRSA.",
            "Janela seleciona o centro CWAVE do pixel; CBAND é a largura efetiva do instrumento.",
            "Fluxo de abertura sem correção de PSF; erros condicionais a pixels independentes, "
            "sem erro sistemático de calibração/ZODI/astrometria.",
            "Posições MOST exigem validação do observador; "
            "medidas na posição prevista não confirmam uma detecção.",
            "Gaia não é um catálogo infravermelho completo; "
            "ausência de associação não prova ausência de contaminação.",
            "As imagens no painel usam pixels nativos; cada exposição tem seu próprio WCS, "
            "sem reamostragem para fotometria.",
            "WISE W1 é uma banda larga e não equivale a esta janela SPHEREx; "
            "não há subtração WISE/SPHEREx.",
            "Detectores e centros de banda diferentes "
            "não constituem uma curva de luz em banda fixa. "
            "O espectro é amostrado em épocas distintas, sem interpolação em lacunas.",
        ],
        "frames": frames,
    }
    from .infrared_catalogs import build_join

    report["dataset_join"] = build_join(report, manifest.get("context_catalogues"))
    report["request_selection"] = manifest.get("request_selection", {})
    write_json(output / "joined_samples.json", report["dataset_join"])
    from .skyshift import enrich_report

    enrich_report(report)
    if "skyshift_context" in report:
        write_json(output / "skyshift_context.json", report["skyshift_context"])
    write_json(output / "report.json", report)
    write_json(output / "manifest.json", manifest)
    rows = [
        {
            "exposure": f["source"],
            "utc": f["utc"],
            "ra": f["target"]["ra"],
            "dec": f["target"]["dec"],
            "detector": f["detector"],
            "central_wavelength_um": f["central_wavelength_um"],
            "ephemeris_provider": f["target"].get("provider", "supplied"),
            "position_status": f["target"].get("position_status", "unverified"),
            **f["measurement"],
        }
        for f in frames
    ]
    with (output / "measurements.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return report
