import copy
import json
import threading
import urllib.request

import numpy as np
from PIL import Image

from spherex_tracking.infrared import LabState, LocalServer, make_handler, synthetic_manifest
from spherex_tracking.infrared_animation import render_animation
from spherex_tracking.infrared_mask import run_manifest


def test_export_preserves_photometry_and_uses_inverted_gray_in_time_order(tmp_path):
    report = run_manifest(synthetic_manifest(tmp_path / 'input'), tmp_path / 'out')
    baseline = copy.deepcopy(report)
    # Export must order by time even if supplied in reverse order.
    report['frames'].reverse()
    path = render_animation(report, tmp_path / 'out')
    with Image.open(path) as image:
        assert image.n_frames == 4
        assert image.info['duration'] == 1000
        rgb = np.asarray(image.convert('RGB'))[48:648, 20:620]
        assert np.array_equal(rgb[..., 0], rgb[..., 1])
        assert np.array_equal(rgb[..., 1], rgb[..., 2])
        assert rgb.min() < 10 and rgb.max() > 245
        image.seek(3)
    assert list(reversed(report['frames'])) == baseline['frames']


def test_gif_route_and_cached_query_do_not_run_archive_again(tmp_path, monkeypatch):
    output = tmp_path / 'out'
    report = run_manifest(synthetic_manifest(tmp_path / 'input'), output)
    state = LabState(output)
    monkeypatch.setattr('spherex_tracking.infrared.available_calibrations', lambda _: [4])
    calls = []
    monkeypatch.setattr(state.executor, 'submit', lambda *args: calls.append(args))
    params = {'detector': 4, 'low_um': 3.3, 'high_um': 3.5}
    key = state.submit(params)
    cached = output / 'runs' / key
    cached.mkdir(parents=True)
    (cached / 'report.json').write_text(json.dumps(report))
    state.running = False
    assert state.submit(params) == key
    assert len(calls) == 1
    assert state.jobs[key]['status'] == 'complete'
    server = LocalServer(('127.0.0.1', 0), make_handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/files/animation.gif') as res:
            assert res.headers['Content-Type'] == 'image/gif'
            assert res.read(6) == b'GIF89a'
        assert (cached / 'animation_gray_r.gif').is_file()
        with urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/api/stack?detector=4&start=0&count=3') as res:
            assert res.headers['Content-Type'] == 'image/png'
            assert res.read(8) == b'\x89PNG\r\n\x1a\n'
        from urllib.error import HTTPError
        import pytest
        with pytest.raises(HTTPError) as error:
            urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/api/stack?detector=4&start=0&count=999')
        assert error.value.code == 400
        base = f'http://127.0.0.1:{server.server_port}'
        with urllib.request.urlopen(base + '/api/analyses') as res:
            choices = json.load(res)
        assert choices[0]['id'] == key and choices[0]['frames'] == 4
        request = urllib.request.Request(base + '/api/select-analysis',
            json.dumps({'id': key}).encode(), {'Content-Type': 'application/json'})
        with urllib.request.urlopen(request) as res:
            assert json.load(res)['selected'] == key
        reopened = LabState(output)
        assert reopened.current_output == cached
        reopened.executor.shutdown()
        request = urllib.request.Request(base + '/api/select-analysis',
            json.dumps({'id': '../outside'}).encode(), {'Content-Type': 'application/json'})
        with pytest.raises(HTTPError) as error:
            urllib.request.urlopen(request)
        assert error.value.code == 400
        with urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/sky-assets/help.js') as res:
            assert b'export function installHelp' in res.read()
    finally:
        server.shutdown()
        server.server_close()
        state.executor.shutdown()
