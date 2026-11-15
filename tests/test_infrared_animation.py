import copy
import json
import threading
import urllib.request

import numpy as np
from PIL import Image

from spherex_tracking.infrared import LabState, LocalServer, make_handler, synthetic_manifest
from spherex_tracking.infrared_animation import render_animation
from spherex_tracking.infrared_mask import run_manifest


def test_export_preserves_photometry_and_uses_inferno_in_time_order(tmp_path):
    report = run_manifest(synthetic_manifest(tmp_path / 'input'), tmp_path / 'out')
    baseline = copy.deepcopy(report)
    # Export must order by time even if supplied in reverse order.
    report['frames'].reverse()
    path = render_animation(report, tmp_path / 'out')
    with Image.open(path) as image:
        assert image.n_frames == 4
        assert image.info['duration'] == 1000
        rgb = np.asarray(image.convert('RGB'))[48:648, 20:620]
        assert np.any((rgb[..., 0] != rgb[..., 1]) & (rgb[..., 1] != rgb[..., 2]))
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
        assert (cached / 'animation.gif').is_file()
        with urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/inferno.mjs') as res:
            assert b'export function inferno' in res.read()
    finally:
        server.shutdown()
        server.server_close()
        state.executor.shutdown()
