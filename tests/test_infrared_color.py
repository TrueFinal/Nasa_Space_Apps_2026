import copy
import json

import numpy as np
import pytest
from astropy.io import fits
from astropy.wcs import WCS

from spherex_tracking.infrared import synthetic_manifest
from spherex_tracking.infrared_color import (
    colorize_irsa_cube,
    mosaic_from_frames,
    render_color_mosaic,
    rgb_from_planes,
)
from spherex_tracking.infrared_mask import run_manifest, sha256


def frame(wave, shift=0):
    wcs = WCS(naxis=2)
    wcs.wcs.crpix = [4 + shift, 4]
    wcs.wcs.crval = [359.999, 12]
    wcs.wcs.cdelt = [-6.2 / 3600, 6.2 / 3600]
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    image = np.zeros((8, 8))
    image[3, 3 + shift] = 5
    return {
        "id": str(wave),
        "shape": [8, 8],
        "wcs_header": wcs.to_header().tostring(),
        "science": image.tolist(),
        "wavelength": np.full(image.shape, wave).tolist(),
        "mask": np.zeros(image.shape, np.uint16).tolist(),
        "utc": "2026-07-20T00:00:00",
        "input_sha256": "test",
        "plot": {"eligible": True},
    }


def test_wcs_alignment_not_pixel_index_stacking_and_no_source_mutation():
    frames = [frame(1), frame(2, 1), frame(4, 2)]
    original = copy.deepcopy(frames)
    planes, counts, *_ = mosaic_from_frames(frames)
    for i in range(3):
        assert planes[i, 3, 3] == 5
        assert counts[i, 3, 3] == 1
        assert np.nanargmax(planes[i]) == 27
    assert frames == original


def test_cwave_mask_coverage_and_boundaries_control_channel_membership():
    f = frame(1)
    f["wavelength"][3] = [0.74, 0.75, 1.63, 3.83, 5.0, 5.01, 1, 1]
    f["mask"][3][6] = 2
    f["mask"][3][7] = 8  # Gaia stars stay in the visual context.
    planes, counts, *_ = mosaic_from_frames([f])
    assert counts[:, 3, 0].sum() == 0
    assert counts[:, 3, 5].sum() == 0
    assert counts[:, 3, 6].sum() == 0
    assert counts[2, 3, 1] == counts[2, 3, 7] == 1
    assert counts[1, 3, 2] == counts[0, 3, 3] == counts[0, 3, 4] == 1
    assert np.isnan(planes[0, 3, 1])


def test_unrelated_wcs_and_ineligible_frames_never_add_fake_coverage():
    a, b = frame(1), frame(4)
    h = fits.Header.fromstring(b["wcs_header"])
    h["CRVAL2"] = -30
    b["wcs_header"] = h.tostring()
    excluded = frame(2)
    excluded["plot"]["eligible"] = False
    _, counts, _, _, contributors = mosaic_from_frames([a, b, excluded])
    assert not counts[:2].any()
    assert [c["id"] for c in contributors] == [a["id"]]
    assert mosaic_from_frames([excluded]) is None


def test_missing_channels_and_pixels_are_explicit_without_interpolation():
    planes = np.array([[[0.0, 1.0, np.nan]], [[np.nan] * 3], [[0.0, 1.0, np.nan]]])
    counts = np.isfinite(planes).astype(int)
    before = planes.copy()
    rgb, channels, complete = rgb_from_planes(planes, counts)
    assert rgb[0, 1].tolist() == [255, 0, 255, 255]
    assert rgb[0, 2].tolist() == [0, 0, 0, 0]
    assert channels[1]["covered_pixels"] == 0
    assert not complete.any()
    np.testing.assert_equal(planes, before)
    # A covered zero/constant image is not absent data.
    rgb, _, complete = rgb_from_planes(np.zeros((3, 2, 2)), np.ones((3, 2, 2)))
    assert np.all(rgb[..., 3] == 255)
    assert complete.all()


def test_rendering_preserves_native_science_measurements_and_fits(tmp_path):
    manifest = synthetic_manifest(tmp_path / "inputs")
    output = tmp_path / "out"
    report = run_manifest(manifest, output)
    before = copy.deepcopy(report["frames"])
    hashes = {p.name: sha256(p) for p in output.glob("*.fits")}
    csv_before = (output / "measurements.csv").read_bytes()
    render_color_mosaic(report, output)
    assert report["frames"] == before
    assert hashes == {p.name: sha256(p) for p in output.glob("*.fits")}
    assert (output / "measurements.csv").read_bytes() == csv_before
    meta = report["color_mosaic"]
    assert meta["display_only"] and meta["synthetic"]
    assert meta["complete_rgb_fraction"] == 0  # D4-only fixture -> green only.
    assert [c["covered_pixels"] > 0 for c in meta["channels"]] == [False, True, False]
    assert (output / "color_mosaic.png").read_bytes().startswith(b"\x89PNG")
    assert json.loads((output / "color_mosaic.json").read_text("utf-8")) == meta


def make_cube(path, unit="um"):
    wcs = WCS(naxis=3)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN", "WAVE"]
    wcs.wcs.crpix = [4, 4, 1]
    wcs.wcs.crval = [359.999, 12, 1]
    wcs.wcs.cdelt = [-0.002, 0.002, 1]
    header = wcs.to_header()
    header["BUNIT"] = "MJy/sr"
    image = np.tile(np.arange(64).reshape(8, 8), (4, 1, 1)).astype(float)
    wave = np.array([4.0, 0.5, 1.0, 2.0])  # Shuffled PLANE table and an optical plane.
    if unit == "m":
        wave *= 1e-6
    table = fits.BinTableHDU.from_columns(
        [
            fits.Column(name="PLANE", format="4J", array=[[4, 1, 2, 3]]),
            fits.Column(name="WAVELENGTHS", format="4D", unit=unit, array=[wave]),
        ],
        name="WCS-WAVE",
    )
    flags = np.zeros(image.shape, np.uint32)
    flags[1, 1, 1] = 1 << 10  # Mask hot pixel using SkyShift policy.
    flags[1, 1, 2] = 1 << 21  # Retain SOURCE.
    hits = np.ones(image.shape, np.int32)
    hits[:, 0, 0] = 0
    fits.HDUList(
        [
            fits.PrimaryHDU(header=fits.Header({"SYNTHET": True})),
            fits.ImageHDU(image, header, name="IMAGE"),
            fits.ImageHDU(hits, name="NHITS"),
            fits.ImageHDU(flags, name="FLAGS"),
            table,
        ]
    ).writeto(path)


@pytest.mark.parametrize("unit", ["um", "m"])
def test_irsa_cube_uses_lookup_units_flags_hits_and_only_infrared(tmp_path, unit):
    path = tmp_path / "cube.fits"
    make_cube(path, unit)
    before = sha256(path)
    result = colorize_irsa_cube(path, tmp_path / "out")
    assert sha256(path) == before
    assert result["synthetic"]
    for row, expected in zip(result["spectral_planes"], [4, 2, 1]):
        assert row["wavelengths_um"] == pytest.approx([expected])
    assert [c["covered_pixels"] for c in result["channels"]] == [63, 63, 62]
    assert result["complete_rgb_fraction"] == 62 / 64


def test_irsa_cube_rejects_mismatched_planes_and_output_with_original(tmp_path):
    path = tmp_path / "cube.fits"
    make_cube(path)
    with pytest.raises(ValueError, match="separada"):
        colorize_irsa_cube(path, tmp_path)
    with fits.open(path, mode="update") as hdul:
        hdul["WCS-WAVE"].data["PLANE"][0][0] = 1
    with pytest.raises(ValueError, match="WCS-WAVE"):
        colorize_irsa_cube(path, tmp_path / "out")
