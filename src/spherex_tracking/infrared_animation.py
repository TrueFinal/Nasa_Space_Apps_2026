"""Inverted grayscale display per exposure; never alters native photometry."""
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


def render_animation(report, output):
    """Export the default player: chronological exposures, shared scale per detector.

    Reuse its native cutout/background, percentile limits and logarithmic stretch.
    A positive pedestal supports background-subtracted negative intensities.
    """
    frames = sorted((f for f in report['frames'] if f.get('plot', {}).get('eligible', True)),
                    key=lambda f: f['mjd_utc'])
    if not frames:
        raise ValueError('No covered frames to animate.')
    arrays, groups = [], {}
    for f in frames:
        c = f['plot']['crop']
        sl = np.s_[c['y']:c['y']+c['h'], c['x']:c['x']+c['w']]
        a = np.asarray(f['science'], float)[sl]
        good = np.isfinite(a) & ((np.asarray(f['mask'])[sl] & (1 | 2 | 16)) == 0)
        a = np.where(good, a - f['plot']['background']['science'], np.nan)
        arrays.append(a)
        groups.setdefault(f['detector'], []).append(a[np.isfinite(a)])
    limits = {}
    for d, values in groups.items():
        values = np.concatenate(values)
        lo, hi = np.percentile(values, [3.35, 100 - .05 * 10 ** .69]) if values.size else (0., 1.)
        limits[d] = (lo, max(hi, lo + (abs(lo) or 1) * .001))
    images = []
    for f, a in zip(frames, arrays):
        lo, hi = limits[f['detector']]
        t = np.clip((a - lo) / (hi - lo), 0, 1)
        t = np.log1p(1000 * t) / np.log1p(1000)
        gray = np.rint(255 * (1 - np.nan_to_num(t))).astype('uint8')
        rgb = np.repeat(gray[..., None], 3, axis=2)
        yy, xx = np.indices(a.shape)
        rgb[~np.isfinite(a)] = np.where(((xx+yy)%4 < 2)[~np.isfinite(a), None],
                                       [195, 195, 195], [225, 225, 225])
        image = Image.fromarray(np.flipud(rgb)).resize((600, 600), Image.Resampling.NEAREST)
        canvas = Image.new('RGB', (640, 668), '#080e15')
        canvas.paste(image, (20, 48))
        ImageDraw.Draw(canvas).text((20, 12),
            f"{f['utc']} UTC | D{f['detector']} | {f.get('central_wavelength_um', 0):.4f} um",
            fill='white')
        images.append(canvas)
    path = Path(output) / 'animation_gray_r.gif'
    temporary = path.with_suffix('.gif.part')
    images[0].save(temporary, format='GIF', save_all=True, append_images=images[1:],
                   duration=1000, loop=0, disposal=2)
    temporary.replace(path)
    return path
