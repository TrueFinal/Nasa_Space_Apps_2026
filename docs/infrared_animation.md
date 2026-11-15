# SPHEREx time player

The laboratory renders one observed exposure at a time in chronological order.
The default brightness palette is inverted grayscale: white is faint and black
is bright, in both the interactive player and downloaded GIF. The image remains
an intensity map rather than a compression of the spectral channels into RGB.

Native IMAGE − ZODI values and coverage are retained. The existing display
background is subtracted, percentile limits are shared within each detector,
and a positive pedestal permits a logarithmic display of negative residuals.
The tutorial's continuum-subtracted PAH map requires suitable spectral cube
planes and is not applied to arbitrary exposures. Display transforms never
enter aperture photometry or change the FITS data.

The player starts automatically. **View by frame** pauses it; arrows and the
slider select individual exposures. Date, detector and wavelength identify
the selected frame. **Download GIF** exports the full default sequence with
the same inverted grayscale palette, normalization and one-second frame duration. The
export does not include interactive catalogue overlays or custom display modes.
It is generated only when requested and then cached.

Interactive searches no longer generate comparison plates or RGB mosaics.
AllWISE/NEOWISE context is optional and off by default; Gaia cones are fetched
with up to three parallel requests. Identical successful queries reuse their
saved analysis. New parameters create a separate analysis. Clearing the relevant
`outputs/infrared/runs/<key>` report forces that query to be processed again.

## Stack a selected interval

Choose a detector, the first frame and a number of consecutive frames. UTC dates
show the selected interval before building the image. Each source cutout is
mapped with its celestial WCS onto a common sky grid, including RA wraparound;
nearest native pixels provide display samples. Maximum background-subtracted
brightness preserves multiple positions of moving sources while stationary
stars coincide. There is no interpolation across missing data. Gray hatching
marks pixels without coverage. The display is not a sum used for photometry.

Only one detector is combined at a time. Its exposures can still have different
CWAVE centres; changes in source brightness and instrumental artifacts can also
produce marks in a stack. Sources appear multiple times only when motion,
coverage and resolution permit. Large, disjoint fields are rejected with a
request to shorten the interval. The stack PNG can be downloaded.

Playback suspends while the browser tab is hidden and resumes on return if the
user had not explicitly paused it. Manual frame controls keep it paused.
