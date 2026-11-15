"""Execute upstream scripts/science/phot.py on our native FITS as a separate analysis.

The primary aperture measurements remain unchanged. The upstream method recentres,
rejects instrumental masks/saturation and applies its own aperture correction.
CWAVE/CBAND maps supply the same local calibration already used by our processor.
"""

import argparse
import dataclasses
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from scipy.ndimage import map_coordinates


class WaveMap:
    def __init__(self, wave, band):
        self.wave, self.band = wave, band

    @staticmethod
    def sample(array, x, y):
        x, y = np.broadcast_arrays(np.asarray(x, float), np.asarray(y, float))
        result = map_coordinates(
            array, [y.ravel(), x.ravel()], order=1, mode="constant", cval=np.nan
        )
        return result.reshape(x.shape)

    def wavelength(self, x, y):
        return self.sample(self.wave, x, y)

    def bandwidth(self, x, y):
        return self.sample(self.band, x, y)


def clean(value):
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, (float, np.floating)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, np.generic):
        return value.item()
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    sys.path[:0] = [str(args.source / "scripts/science"), str(args.source / "core/src")]
    from phot import measure
    from skyshift_core import Level2

    report = json.loads(args.report.read_text(encoding="utf-8"))
    rows = []
    for frame in report["frames"]:
        path = (args.report.parent / f"{frame['id']}.fits").resolve()
        if not path.is_relative_to(args.report.parent.resolve()):
            raise ValueError("FITS fora do relatório")
        file_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if file_hash != frame["output_sha256"]:
            raise ValueError(f"FITS alterado desde a fotometria primária: {frame['id']}")
        with fits.open(path) as hdus:
            header = hdus["IMAGE"].header
            l2 = Level2(
                data=np.asarray(hdus["SCIENCE"].data, dtype="float32"),
                flags=np.asarray(hdus["FLAGS"].data, dtype="int32"),
                variance=np.asarray(hdus["VARIANCE"].data, dtype="float32"),
                wcs=WCS(header).celestial,
                mjd_avg=frame["mjd_utc"],
                mjd_beg=None,
                mjd_end=None,
                detector=frame["detector"],
                obsid=header.get("OBSID", frame["id"]),
                header=header,
                wave=WaveMap(
                    np.array(hdus["CWAVE"].data, float), np.array(hdus["CBAND"].data, float)
                ),
            )
            target = frame["target"]
            point = measure(l2, target["ra"], target["dec"], radii=(2.0, 3.0))
            rows.append(
                {
                    "frame_id": frame["id"],
                    "fits_sha256": file_hash,
                    "detector": frame["detector"],
                    "mjd": frame["mjd_utc"],
                    "point": dataclasses.asdict(point),
                    "primary_measurement": frame["measurement"],
                }
            )
    out = {
        "report_manifest_sha256": report["manifest_sha256"],
        "method": "scripts/science/phot.py:measure",
        "input": "native SCIENCE/FLAGS/VARIANCE",
        "calibration": "bilinear CWAVE/CBAND maps, no synthetic wavelengths",
        "annulus_px": [4, 9],
        "recentre": True,
        "max_offset_px": 1.5,
        "gaia_mask_applied": False,
        "aperture_correction_r2": 1.033,
        "scope": "independent_photometry_not_identity_or_orbit_validation",
        "primary_measurements_changed": False,
        "rows": rows,
        "accepted": sum(r["point"]["ok"] for r in rows),
        "total": len(rows),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(clean(out), ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )
    print(f"Upstream photometry: {out['accepted']}/{out['total']} accepted; primary unchanged")


if __name__ == "__main__":
    main()
