import copy

import numpy as np
import pytest
from astropy.wcs import WCS

from spherex_tracking.infrared_stack import stack_frames


def moving_frames():
    frames = []
    for i in range(3):
        wcs = WCS(naxis=2)
        wcs.wcs.crpix = [16+i,16]
        wcs.wcs.crval = [0,0]
        wcs.wcs.cdelt = [-.001,.001]
        wcs.wcs.ctype = ['RA---TAN','DEC--TAN']
        a = np.zeros((32,32))
        a[8,8+i] = 10  # Fixed star, detector pointing changes.
        a[20,15+3*i+i] = 10  # Moving source plus pointing change.
        frames.append({'detector':4, 'mjd_utc':60000+i,
            'wcs_header':wcs.to_header().tostring(), 'science':a.tolist(),
            'mask':np.zeros_like(a, dtype=int).tolist(),
            'plot':{'eligible':True, 'crop':{'x':0,'y':0,'w':32,'h':32},
                    'background':{'science':0}}})
    return {'frames':frames}


def test_sky_alignment_keeps_one_star_and_all_three_moving_positions():
    report = moving_frames()
    before = copy.deepcopy(report)
    rgb, hits, frames = stack_frames(report, 4, 0, 3)
    dark = (rgb[...,0] == 0) & (hits > 0)
    assert dark.sum() == 4  # One stationary star and three moving positions.
    assert len(frames) == 3
    assert np.array_equal(rgb[...,0], rgb[...,1])
    assert np.any(hits == 0)  # Coverage gaps remain distinguishable.
    assert report == before


def test_stack_selection_does_not_include_unselected_positions():
    rgb, hits, frames = stack_frames(moving_frames(), 4, 1, 2)
    assert ((rgb[...,0] == 0) & (hits>0)).sum() == 3
    assert [f['mjd_utc'] for f in frames] == [60001,60002]
    for detector, start, count in [(4,-1,2),(4,0,1),(4,1,3),(6,0,2)]:
        with pytest.raises(ValueError):
            stack_frames(moving_frames(),detector,start,count)
