import json
import threading
import urllib.request

from spherex_tracking.infrared import LabState, LocalServer, make_handler


def test_both_interfaces_share_backend_without_asset_or_route_collisions(tmp_path, monkeypatch):
    state = LabState(tmp_path)
    calls = []
    monkeypatch.setattr(state, "submit", lambda params, **kw: calls.append(kw) or "job")
    server = LocalServer(("127.0.0.1", 0), make_handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:

        def get(path):
            with urllib.request.urlopen(base + path) as response:
                return response.read().decode("utf-8")

        explorer = get("/lab")
        assert 'id="ra"' in explorer
        assert explorer.count('href="/native-lab"') == 1
        assert "/sky-assets/app.js" in explorer
        assert "tour-start" in get("/sky-assets/tour.js")
        native = get("/native-lab")
        assert 'id="query"' in native and 'id="reference-panel"' in native
        assert "/native-assets/app.js" in native
        assert "Explore as seis bandas" not in native
        assert "api/native-run" in get("/native-assets/app.js")
        assert "export function stretch" in get("/native-assets/plate.mjs")
        assert "skyshift-math.mjs" in get("/native-assets/skyshift.mjs")
        assert "installHelp" in get("/sky-assets/help.js")
        for route in ("/api/run", "/api/native-run"):
            request = urllib.request.Request(
                base + route, json.dumps({}).encode(), {"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(request) as response:
                assert json.load(response)["job"] == "job"
        assert calls == [{"render_previews": False}, {"render_previews": True}]
    finally:
        server.shutdown()
        server.server_close()
        state.executor.shutdown()
