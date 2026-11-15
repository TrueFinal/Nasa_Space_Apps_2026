"""Audit the five observed examples against original SPHEREx FITS; optionally query live SIA."""
import argparse
import csv
import io
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from astropy.io import fits

from spherex_tracking.infrared_mask import sha256
from spherex_tracking.sky_proxy import proxy

ROOT=Path(__file__).resolve().parents[1]


def validate(target, live=False):
    sample=ROOT/'web/sky-explorer/worker/samples'/f"{target['id']}.json"
    d=json.loads(sample.read_text())
    frames=[]
    for e in d['exposures']:
        path=ROOT/'data/web_targets'/target['id']/f"{e['obs_id']}.fits"
        with fits.open(path,memmap=False) as h:
            assert h['IMAGE'].header['DETECTOR']==target['detector']
            assert abs(float(h['IMAGE'].header['MJD-AVG'])-e['mjd'])<1e-8
            assert np.isfinite(h['IMAGE'].data).any()
        frames.append({'observation':e['obs_id'],'url':e['url'],'sha256':sha256(path),'mjd':e['mjd'],
                       'covered_pixels':sum(v is not None for v in e['data'])})
    assert len({f['mjd'] for f in frames})>1
    result={'id':target['id'],'name':target['name'],'ra':target['ra'],'dec':target['dec'],
            'detector':target['detector'],'saved_exposures':len(frames),
            'sample_sha256':sha256(sample),'frames':frames,'live_queries':[]}
    if live:
        for collection in ['spherex_dr1','spherex_qr3']:
            try:
                data,_=proxy('archive',{'ra':target['ra'],'dec':target['dec'],'fov':300,
                    'collection':collection,'refresh':'1'},ROOT/'data/sky_proxy')
                rows=list(csv.DictReader(io.StringIO(data.decode())))
                result['live_queries'].append({'collection':collection,'rows':len(rows),
                    'detector_rows':sum(r.get('energy_bandpassname')==f"SPHEREx-D{target['detector']}" for r in rows),
                    'status':'ok'})
            except Exception as exc:
                result['live_queries'].append({'collection':collection,'status':'unavailable','error':str(exc)})
    print(target['id'],len(frames),'verified original exposures',result['live_queries'],flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--live',action='store_true');args=parser.parse_args()
    targets=json.loads((ROOT/'web/sky-explorer/worker/config.json').read_text())['targets']
    with ThreadPoolExecutor(max_workers=3) as pool:
        results=list(pool.map(lambda t:validate(t,args.live),targets))
    output=ROOT/'docs/validation/sky-targets.json';output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps({'checked_at':datetime.now(timezone.utc).isoformat(),'targets':results},indent=2)+'\n')
