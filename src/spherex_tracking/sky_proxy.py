"""Bounded, credential-free IRSA/Gaia proxy for the public coordinate explorer."""
from __future__ import annotations

import hashlib
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .infrared_archive import _context

COLLECTIONS = {'spherex_dr1', 'spherex_qr3', 'spherex_dr1_deep', 'spherex_qr3_deep', 'spherex_dr1_cube'}


def coordinates(params):
    ra, dec, fov = (float(params[k]) for k in ('ra','dec','fov'))
    if not all(math.isfinite(v) for v in (ra,dec,fov)) or not 0<=ra<360 or not -90<=dec<=90 or not 30<=fov<=1200:
        raise ValueError('Use RA 0–360°, Dec −90–90°, and field of view 30–1200 arcsec.')
    return ra,dec,fov


def upstream_request(route, params):
    if route == 'archive':
        ra,dec,fov = coordinates(params)
        collection = params.get('collection','spherex_dr1')
        if collection not in COLLECTIONS:
            raise ValueError('Unknown SPHEREx release.')
        query = {'COLLECTION':collection,'POS':f'CIRCLE {ra} {dec} {fov/7200}', 'RESPONSEFORMAT':'CSV'}
        if params.get('start') or params.get('end'):
            from datetime import date
            from astropy.time import Time
            start = date.fromisoformat(params.get('start') or '2025-03-01')
            end = date.fromisoformat(params.get('end') or date.today().isoformat())
            if end < start:
                raise ValueError('End date must follow the start date.')
            query['TIME'] = f'{Time(start.isoformat()).mjd} {Time(end.isoformat()).mjd+1}'
        return 'https://irsa.ipac.caltech.edu/SIA?'+urllib.parse.urlencode(query), 'text/csv; charset=utf-8', 600
    if route == 'cutout':
        url = urllib.parse.urlsplit(params.get('url',''))
        if url.scheme!='https' or url.netloc!='irsa.ipac.caltech.edu' or not url.path.startswith('/ibe/data/spherex/') or not url.path.endswith('.fits'):
            raise ValueError('Only public SPHEREx FITS URLs from IRSA are supported.')
        ra,dec = params.get('center','').split(',')
        ra,dec,_ = coordinates({'ra':ra,'dec':dec,'fov':float(params['size'])*3600})
        query = urllib.parse.urlencode({'center':f'{ra},{dec}','size':params['size']})
        return urllib.parse.urlunsplit(('https',url.netloc,url.path,query,'')), 'application/fits', 7*86400
    if route == 'gaia':
        ra,dec,fov = coordinates(params)
        query = f"SELECT TOP 2000 ra,dec,2016.0 AS ref_epoch,pmra,pmdec,phot_g_mean_mag FROM gaia.dr3lite WHERE 1=CONTAINS(POINT('ICRS',ra,dec),CIRCLE('ICRS',{ra},{dec},{fov/7200+.05})) ORDER BY phot_g_mean_mag ASC"
        url = 'https://dc.g-vo.org/tap/sync?'+urllib.parse.urlencode({'REQUEST':'doQuery','LANG':'ADQL','FORMAT':'json','QUERY':query})
        return url,'application/json',86400
    raise ValueError('Unknown sky data endpoint.')


def proxy(route, params, cache):
    url,kind,ttl = upstream_request(route,params)
    directory = Path(cache); directory.mkdir(parents=True,exist_ok=True)
    key = hashlib.sha256(url.encode()).hexdigest()
    path = directory/key
    if path.is_file() and time.time()-path.stat().st_mtime<ttl and not (route=='archive' and params.get('refresh')=='1'):
        return path.read_bytes(),kind
    last = None
    for attempt in range(2):
        request_url = url.replace('irsa.ipac.caltech.edu','irsaproxy1.ipac.caltech.edu') if attempt else url
        try:
            request = urllib.request.Request(request_url,headers={'User-Agent':'Zephyr-Sky-Explorer/1.0'})
            with urllib.request.urlopen(request, timeout=25, context=_context()) as response:
                if urllib.parse.urlsplit(response.url).hostname not in {'irsa.ipac.caltech.edu','irsaproxy1.ipac.caltech.edu','dc.g-vo.org'}:
                    raise ValueError('Unexpected archive redirect.')
                data = response.read(32*1024*1024+1)
                if len(data)>32*1024*1024:
                    raise ValueError('Archive response exceeds 32 MB. Reduce the field of view.')
            # A unique temporary name avoids races between browser sessions.
            import tempfile
            with tempfile.NamedTemporaryFile(dir=directory,delete=False) as stream:
                stream.write(data); temporary=Path(stream.name)
            temporary.replace(path)
            return data,kind
        except (OSError,TimeoutError) as exc:
            last=exc
    raise OSError(f'Archive unavailable: {last}. Saved observed examples remain available.')
