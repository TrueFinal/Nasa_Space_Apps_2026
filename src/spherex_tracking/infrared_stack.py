"""Sky-aligned maximum-intensity trails for display, never for photometry."""
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from PIL import Image, ImageDraw


def stack_frames(report, detector, start, count):
    frames = sorted((f for f in report['frames'] if f['detector'] == detector
                     and f.get('plot', {}).get('eligible', True)), key=lambda f: f['mjd_utc'])
    if start < 0 or count < 2 or start + count > len(frames):
        raise ValueError('Choose at least two available frames within the selected detector.')
    frames = frames[start:start+count]
    reference = WCS(fits.Header.fromstring(frames[0]['wcs_header'])).celestial
    bounds, inputs, samples = [], [], []
    for f in frames:
        wcs = WCS(fits.Header.fromstring(f['wcs_header'])).celestial
        c = f['plot']['crop']
        # Use every native pixel in the selected sky cutout, not its moving target centre.
        xs = [c['x'], c['x']+c['w']-1, c['x'], c['x']+c['w']-1]
        ys = [c['y'], c['y'], c['y']+c['h']-1, c['y']+c['h']-1]
        rx, ry = reference.world_to_pixel(wcs.pixel_to_world(xs, ys))
        bounds.extend(zip(rx, ry))
        a = np.asarray(f['science'], float) - f['plot']['background']['science']
        good = np.isfinite(a) & ((np.asarray(f['mask']) & (1 | 2 | 16)) == 0)
        inside = np.zeros_like(good)
        inside[c['y']:c['y']+c['h'], c['x']:c['x']+c['w']] = True
        good &= inside
        inputs.append((wcs, a, good))
        samples.append(a[good])
    bounds = np.asarray(bounds)
    if not np.isfinite(bounds).all():
        raise ValueError('These frames cannot be aligned onto a common sky projection.')
    x0, y0 = np.floor(bounds.min(axis=0)).astype(int)-1
    x1, y1 = np.ceil(bounds.max(axis=0)).astype(int)+1
    width, height = int(x1-x0+1), int(y1-y0+1)
    if width > 2048 or height > 2048 or width*height > 1048576:
        raise ValueError('These frames span too much sky. Select a shorter interval.')
    yy, xx = np.indices((height, width))
    sky = reference.pixel_to_world(xx+x0, yy+y0)
    combined = np.full((height, width), np.nan)
    hits = np.zeros((height, width), dtype=np.uint16)
    for wcs, a, good in inputs:
        sx, sy = wcs.world_to_pixel(sky)
        finite = np.isfinite(sx) & np.isfinite(sy)
        ix = np.floor(np.where(finite, sx, 0)+.5).astype(int)
        iy = np.floor(np.where(finite, sy, 0)+.5).astype(int)
        inside = finite & (ix>=0) & (iy>=0) & (ix<a.shape[1]) & (iy<a.shape[0])
        ix = np.clip(ix, 0, a.shape[1]-1); iy = np.clip(iy, 0, a.shape[0]-1)
        accepted = inside & good[iy, ix]
        combined[accepted] = np.fmax(combined[accepted], a[iy[accepted], ix[accepted]])
        hits[accepted] += 1
    values = np.concatenate(samples)
    if not values.size:
        raise ValueError('No accepted pixels in the selected interval.')
    lo, hi = np.percentile(values, [3.35, 100-.05*10**.69])
    hi = max(hi, lo+(abs(lo) or 1)*.001)
    # One common intensity scale; maximum preserves each bright moving position.
    t = np.clip((combined-lo)/(hi-lo), 0, 1)
    t = np.log1p(1000*t)/np.log1p(1000)
    gray = np.rint(255*(1-np.nan_to_num(t))).astype('uint8')
    rgb = np.repeat(gray[..., None], 3, axis=2)
    missing = hits == 0
    rgb[missing] = np.where(((xx+yy)%4<2)[missing, None], [195,195,195], [225,225,225])
    return rgb, hits, frames


def render_stack(report, output, detector, start, count):
    rgb, hits, frames = stack_frames(report, detector, start, count)
    image = Image.fromarray(np.flipud(rgb))
    scale = 768/max(image.size)
    image = image.resize((max(1,round(image.width*scale)),max(1,round(image.height*scale))),
                         Image.Resampling.NEAREST)
    canvas = Image.new('RGB', (max(640, image.width+40), image.height+90), 'white')
    canvas.paste(image, (20,70))
    draw = ImageDraw.Draw(canvas)
    draw.text((20,10), f'D{detector} | {len(frames)} frames | sky-aligned maximum brightness', fill='black')
    draw.text((20,30), frames[0]['utc']+' to '+frames[-1]['utc']+' UTC', fill='black')
    if hits.max() < 2:
        draw.text((20,50), 'No overlapping sky coverage in these cutouts; select a shorter interval.', fill='black')
    path = Path(output)/f'stack_gray_r_D{detector}_{start}_{count}.png'
    canvas.save(path)
    return path
