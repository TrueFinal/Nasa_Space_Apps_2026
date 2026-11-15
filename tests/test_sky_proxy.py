from urllib.parse import parse_qs, urlsplit

import pytest

from spherex_tracking.sky_proxy import upstream_request


def test_coordinate_query_filters_position_release_and_utc_dates():
    url,kind,_=upstream_request('archive',{'ra':'133.7951291667','dec':'-7.2451472222','fov':'300',
        'collection':'spherex_dr1','start':'2025-05-01','end':'2026-06-01'})
    q=parse_qs(urlsplit(url).query)
    assert q['COLLECTION']==['spherex_dr1']
    assert q['POS'][0].startswith('CIRCLE 133.7951291667 -7.2451472222 ')
    assert q['TIME'][0].startswith('60796.0 ')
    assert kind.startswith('text/csv')


@pytest.mark.parametrize('params',[{'ra':'nan','dec':'0','fov':'300'},
 {'ra':'360','dec':'0','fov':'300'},{'ra':'1','dec':'91','fov':'300'},
 {'ra':'1','dec':'1','fov':'9000'},
 {'ra':'1','dec':'1','fov':'300','collection':'unknown'},
 {'ra':'1','dec':'1','fov':'300','start':'2026-06-01','end':'2025-05-01'}])
def test_invalid_archive_input_rejected_before_network(params):
    with pytest.raises(ValueError): upstream_request('archive',params)


@pytest.mark.parametrize('url',['http://irsa.ipac.caltech.edu/ibe/data/spherex/a.fits',
 'https://example.com/a.fits','https://irsa.ipac.caltech.edu@evil.test/ibe/data/spherex/a.fits',
 'https://irsa.ipac.caltech.edu/other/a.fits'])
def test_cutout_proxy_cannot_be_used_as_an_arbitrary_url_proxy(url):
    with pytest.raises(ValueError): upstream_request('cutout',{'url':url,'center':'1,2','size':'.1'})


def test_primary_lab_serves_coordinates_and_all_five_observed_targets(tmp_path):
    import json
    import threading
    import urllib.error
    import urllib.request
    from spherex_tracking.infrared import LabState, LocalServer, make_handler
    state=LabState(tmp_path)
    server=LocalServer(('127.0.0.1',0),make_handler(state))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    try:
        with urllib.request.urlopen(base+'/lab') as res:
            page=res.read()
            assert b'id="ra"' in page and b'id="dec"' in page
            assert b'/sky-assets/app.js' in page
            assert b'/sky-assets/zephyr-logo.svg' in page
            assert 'frame-ancestors *' in res.headers['Content-Security-Policy']
        with urllib.request.urlopen(base+'/sky-assets/zephyr-logo.svg') as res:
            assert res.headers['Content-Type'].startswith('image/svg+xml')
            assert b'<svg' in res.read()
        with urllib.request.urlopen(base+'/sky-assets/tour.js') as res:
            assert res.headers['Content-Type'].startswith('text/javascript')
            assert b'zephyr-lab-tour-v1' in res.read()
        for name,count in [('barnard',10),('epsilon',15),('wise0855',12),('rwaur',6),('rdra',9)]:
            with urllib.request.urlopen(base+f'/sky-assets/samples/{name}.json') as res:
                d=json.load(res)
            assert len(d['exposures'])==count
            assert len({e['mjd'] for e in d['exposures']})>1
        with urllib.request.urlopen(base+'/mpc') as res: assert b'id="ra"' in res.read()
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(base+'/sky-assets/%2e%2e/infrared.py')
        assert error.value.code==404
    finally:
        server.shutdown();server.server_close();state.executor.shutdown()
