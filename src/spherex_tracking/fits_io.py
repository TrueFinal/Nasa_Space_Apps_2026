"""Read-only FITS inventory. No assumed time axis, registration or flag policy."""

from pathlib import Path

from astropy.io import fits


def inventory(path):
    """Inspect headers and dimensions without loading science arrays or PSF tables."""
    path = Path(path)
    hdus = []
    with fits.open(path, memmap=True, lazy_load_hdus=True) as handle:
        for i, hdu in enumerate(handle):
            header = hdu.header
            metadata = {}
            for key, value in header.items():
                if key and (
                    key.startswith(("DATE", "MJD", "TIME", "CTYPE", "CUNIT"))
                    or key
                    in {
                        "EXPTIME",
                        "TELAPSE",
                        "TIMESYS",
                        "TSTART",
                        "TSTOP",
                        "DETECTOR",
                        "DET_ID",
                        "OBS_ID",
                        "OBSID",
                        "BUNIT",
                        "CRVAL1",
                        "CRVAL2",
                        "RA",
                        "DEC",
                    }
                ):
                    metadata[key] = value
            naxis = header.get("NAXIS", 0)
            shape = [header.get(f"NAXIS{j}") for j in range(naxis, 0, -1)]
            hdus.append(
                dict(
                    index=i,
                    name=hdu.name,
                    type=type(hdu).__name__,
                    fits_axes_reversed=shape,
                    metadata=metadata,
                )
            )
    return dict(path=str(path.resolve()), hdus=hdus)


def inventory_path(path):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Caminho não encontrado: {path}")
    paths = sorted(
        p
        for p in path.rglob("*")
        if p.is_file() and p.name.lower().endswith((".fits", ".fits.gz", ".fits.fz"))
    )
    if path.is_file():
        paths = [path]
    return [inventory(p) for p in paths]
