"""Fetch observed cutouts for all five challenge targets and prepare browser examples."""
import csv
import io
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from scipy.ndimage import map_coordinates

from spherex_tracking.quality import bad_pixel_mask
from spherex_tracking.time_lapse import _local_wavelength, _grid

ROOT = Path(__file__).resolve().parents[3]
WEB = Path(__file__).resolve().parents[1]
CONFIG = json.loads((WEB / 'worker/config.json').read_text())


def fetch(url):
    error = None
    for _ in range(2):
        try:
            with urlopen(url, timeout=40) as r:
                return r.read()
        except Exception as e:
            error = e
    raise error


def prepare(target):
    directory = ROOT / 'data/web_targets' / target['id']
    directory.mkdir(parents=True, exist_ok=True)
    ra, dec = target['ra'], target['dec']
    query = 'https://irsa.ipac.caltech.edu/SIA?' + urlencode(dict(
        COLLECTION='spherex_dr1', POS=f'CIRCLE {ra} {dec} 0.001', RESPONSEFORMAT='CSV'))
    cache = directory / 'archive.csv'
    if not cache.exists():
        cache.write_bytes(fetch(query))
    rows = list(csv.DictReader(io.StringIO(cache.read_text())))
    selected = sorted({r['access_url']: r for r in rows
                       if r.get('energy_bandpassname') == f"SPHEREx-D{target['detector']}"}.values(),
                      key=lambda r: float(r['t_min']))
    groups = []
    for row in selected:
        if not groups or float(row['t_min'])-float(groups[-1][-1]['t_min']) > 14:
            groups.append([row])
        else:
            groups[-1].append(row)
    chosen = []
    for group in groups:
        indices = np.unique(np.linspace(0, len(group)-1, min(3, len(group))).round().astype(int))
        chosen.extend(group[i] for i in indices)
    size, fov = 48, 300
    wcs = _grid(ra, dec, size, fov/size)
    yy, xx = np.indices((size, size))
    skyra, skydec = wcs.pixel_to_world_values(xx, yy)
    exposures, errors = [], []
    for row in chosen:
        try:
            obs = row['obs_id']
            path = directory / f'{obs}.fits'
            url = row['access_url'] + '?' + urlencode(dict(center=f'{ra},{dec}', size=f'{fov/3600:.6f}'))
            if not path.exists():
                path.write_bytes(fetch(url))
            with fits.open(path) as h:
                image = h['IMAGE']
                x,y = WCS(image.header, fobj=h, naxis=2).world_to_pixel_values(skyra, skydec)
                data = np.asarray(image.data, float)-h['ZODI'].data
                var = np.asarray(h['VARIANCE'].data, float)
                valid = np.isfinite(data)&np.isfinite(var)&(var>0)&~bad_pixel_mask(h['FLAGS'].data)
                weight = np.where(valid, 1/np.where(valid,var,1), 0)
                outweight = map_coordinates(weight,[y,x],order=1,mode='constant',cval=0)
                num = map_coordinates(np.where(valid,data,0)*weight,[y,x],order=1,mode='constant',cval=0)
                out = np.divide(num,outweight,out=np.full_like(num,np.nan),where=outweight>0)
                ov = np.divide(1,outweight,out=np.full_like(num,np.nan),where=outweight>0)
                wave = _local_wavelength(h, ra, dec)[2]
                clean = lambda a: [round(float(v),6) if np.isfinite(v) else None for v in a.ravel()]
                exposures.append(dict(data=clean(out),variance=clean(ov),mjd=float(image.header['MJD-AVG']),
                                      date=image.header['DATE-AVG'],wave=wave,masked=float(1-valid.mean()),
                                      detector=target['detector'],obs_id=obs,url=row['access_url']))
        except Exception as e:
            errors.append(dict(obs_id=row['obs_id'],error=str(e)))
    result = dict(target=target,ra=ra,dec=dec,size=size,fov=fov,exposures=exposures,
                  archive_count=len(selected),total_count=len(rows),query=query,errors=errors,
                  sampled=True,n_selected=len(chosen),collection='spherex_dr1')
    path = WEB / 'worker/samples' / f"{target['id']}.json"
    path.write_text(json.dumps(result, separators=(',',':'), allow_nan=False))
    print(target['id'], len(selected),'archive;',len(exposures),'downloaded;',len(errors),'errors',flush=True)
    return {k: result[k] for k in ['archive_count','n_selected','errors']} | {'target':target['id'],'downloaded':len(exposures)}


if __name__ == '__main__':
    results=[]
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures={pool.submit(prepare,t):t for t in CONFIG['targets']}
        for f in as_completed(futures):
            try: results.append(f.result())
            except Exception as e: results.append({'target':futures[f]['id'],'error':str(e)})
    (WEB / 'validation-targets.json').write_text(json.dumps(results,indent=2))
    print(json.dumps(results,indent=2))
