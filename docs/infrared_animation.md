# SPHEREx time player

The laboratory renders one observed exposure at a time in chronological order.
Its default brightness display uses the Matplotlib `inferno` lookup table
(purple through orange to yellow), following the display palette in the
[IRSA mosaic tutorial](https://caltech-ipac.github.io/irsa-tutorials/spherex-mosaic/).
This is an intensity map for each image; the 102 spectral channels are not
combined into an RGB image.

Native IMAGE − ZODI values and coverage are retained. The existing display
background is subtracted, percentile limits are shared within each detector,
and a positive pedestal permits a logarithmic display of negative residuals.
The tutorial's continuum-subtracted PAH map requires suitable spectral cube
planes and is not applied to arbitrary exposures. Display transforms never
enter aperture photometry or change the FITS data.

The player starts automatically. **View by frame** pauses it; arrows and the
slider select individual exposures. Date, detector and wavelength identify
the selected frame. **Download GIF** exports the full default sequence with
the same inferno palette, normalization and one-second frame duration. The
export does not include interactive catalogue overlays or custom display modes.
It is generated only when requested and then cached.

Interactive searches no longer generate comparison plates or RGB mosaics.
AllWISE/NEOWISE context is optional and off by default; Gaia cones are fetched
with up to three parallel requests. Identical successful queries reuse their
saved analysis. New parameters create a separate analysis. Clearing the relevant
`outputs/infrared/runs/<key>` report forces that query to be processed again.
