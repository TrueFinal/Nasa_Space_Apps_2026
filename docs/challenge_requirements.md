# SPHEREx challenge: implemented and verified

The main application is **`/lab`**, a coordinate-based sky explorer. It is the only web frontend: `/` and `/lab` open the same explorer. The older landing page and MPC web interface have been removed; native-pixel analysis remains available through the Python CLI.

```bash
uv sync
uv run python -m spherex_tracking.infrared serve
# Open http://127.0.0.1:8766/lab
```

## User workflow

Enter RA and declination in decimal degrees or sexagesimal form, choose the field
of view (60–1200 arcsec), detector and spectral range, and optionally restrict
UTC dates. Search current SPHEREx data or load one of the five observed examples.
Playback shows a fixed, north-up celestial grid at different times. The default
palette is white for fainter pixels and black for brighter pixels. Manual frame
controls, GIF and PNG export are available. Dates group by individual exposure,
visit or calendar half-year; spectral channels never become time frames.

For example, WISE 0855 accepts `08h55m10.831s`, `-07:14:42.53` or
`133.7951291667`, `-7.2451472222`. The Barnard and Epsilon Indi B field centres
are approximately propagated to 2026 and are labelled accordingly.

Select a first frame and frame count for a maximum-brightness motion trail or
variance-weighted mean stack. Difference subtracts a selected reference frame.
These products share celestial coordinates and retain missing data as holes.
A position clicked in the sky image generates an exploratory aperture spectrum
and CSV. It uses the exposure's field-centre wavelength and mixes observation
times, so it is not the mission's calibrated spectrophotometry.

## Requirement evidence

| Objective or consideration | Implementation |
| --- | --- |
| RA/Dec sky search and time animation | `/lab`, fixed TAN-SIP celestial projection, date-ordered observations |
| Five named challenge targets | Visible example buttons; 52 real exposures verified against original FITS |
| Current releases | Explicit DR1/QR3 wide and deep collection selectors, metadata refresh and versioned FITS caching |
| 102 bands | Six detectors with official channel lookup and per-pixel wavelength masking for new cutouts |
| Add/subtract images | Variance-weighted mean, maximum-intensity trail, reference subtraction |
| Select field of view | 60–1200 arcsec; transfer cost explained |
| Context | Optional Aladin SPHEREx overlay with WISE/DSS and Gaia DR3 positions |
| URL queries | RA/Dec/FOV/detector/band/collection/date parameters; explicit `example=` for saved datasets |
| Metadata and contamination | Observation IDs, dates, wavelength ranges, rejected-pixel fraction, coverage and source links |
| Public deployment | `--host 0.0.0.0`; Dockerfile; sky viewer allows iframe embedding |

## Verification

The original observations and SHA-256 values are recorded in
[sky-targets.json](validation/sky-targets.json). The saved cutouts are a labelled
subset of the archive, not synthetic scenes or complete mission coverage.

| Target | Saved real exposures | Browser checks |
| --- | ---: | --- |
| Barnard’s Star | 10 | Animation, stack, difference, aperture spectrum, GIF |
| Epsilon Indi B | 15 | Same |
| WISE 0855 | 12 | Same |
| RW Aurigae | 6 | Same |
| R Draconis | 9 | Same |

[Browser results](validation/sky-browser.json) also include mobile layout checks.
Fresh SIA checks returned data for Barnard, RW Aur and Epsilon Indi B in at least
one release; other requests returned upstream HTTP 502. Every live check is
recorded individually in the FITS audit report. The UI reports failed releases
and partial downloads; saved observations remain usable during archive outages.
Aladin initialized in the local browser, but a remote map resource returned a DNS failure; context tiles therefore remain dependent on external service availability. The tests establish correct rendering and data handling, not confirmed detections
of proper motion, variability, or a resolved brown-dwarf pair.

To repeat checks:

```bash
uv run python scripts/validate_sky_targets.py --live
cd web/sky-explorer
npm ci
npm run build
npm test
npx playwright test  # CHROME_PATH can select an installed Chromium
```

## Deploy on a public host

```bash
docker build -t zephyr .
docker run --rm -p 8766:8766 -v zephyr-cache:/app/data zephyr
```

Serve `/lab` behind an HTTPS reverse proxy on a Python/container host. The
repository includes code and configuration; pushing it does not publish a
hosted service. The coordinate viewer requires no archive credentials or model
training. The saved examples are included in the image; large FITS and calibration
caches are excluded. Native-pixel MPC CLI analysis needs its existing calibration setup.

The independent Cloudflare-compatible Worker source in `web/sky-explorer` uses
the same frontend and can also be built with `npm run build`. Neither deployment
path requires browser requests to expose credentials.

## Scientific limits

The sky images use TAN-SIP astrometry, masked resampling and zodiacal-model
subtraction. Different wavelength coverage, noise, instrumental artifacts and PSF
changes can mimic temporal changes. There is no PSF-matched transient classifier.
Broad detector combinations mix wavelengths; narrow channels can have sparse
coverage. Gaia is a positional catalogue, not infrared image data. A clean
animation or a trail is a candidate for inspection, not a confirmed discovery.

Primary references: [IRSA data access](https://irsa.ipac.caltech.edu/spherex-archive-documentation/spherex-data-access/),
[IRSA mosaic tutorial](https://caltech-ipac.github.io/irsa-tutorials/spherex-mosaic/),
[IRSA cutouts](https://irsa.ipac.caltech.edu/ibe/cutouts.html).

## Contextual glossary

Eight subtle question-mark buttons explain sky coordinates, field of view, detectors, spectral channels, motion trails, astronomical surveys and spectra. Generic interface actions have no glossary icons. Hover or keyboard focus opens a brief explanation; tap works on mobile. Escape, a second tap or clicking outside closes it.
