import pytest
import requests

from earth_detectives.core import HTTP, IngestionError, public_url


class Response:
    ok = True
    status_code = 200

    def __init__(self, content=b"valid", length="5"):
        self.content = content
        self.headers = {"Content-Length": length}

    def iter_content(self, size):
        yield self.content

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def close(self):
        pass


def test_incomplete_download_is_never_promoted(tmp_path, monkeypatch):
    http = HTTP(attempts=1)
    monkeypatch.setattr(http.session, "get", lambda *a, **k: Response(b"bad", "100"))
    with pytest.raises(IngestionError):
        http.download("https://example.org/data", tmp_path / "data.txt", lambda _: {})
    assert list(tmp_path.iterdir()) == []


def test_connection_retry_then_validated_atomic_download(tmp_path, monkeypatch):
    http = HTTP(attempts=2)
    calls = []

    def request(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise requests.ConnectionError("secret must not enter logs")
        return Response()

    monkeypatch.setattr(http.session, "get", request)
    monkeypatch.setattr("earth_detectives.core.time.sleep", lambda _: None)
    path, _ = http.download(
        "https://example.org/data?secret=value", tmp_path / "data.txt", lambda _: {"valid": True}
    )
    assert path.read_bytes() == b"valid"
    assert len(calls) == 2
    assert not list(tmp_path.glob("*.part"))


def test_url_redaction():
    assert public_url("https://user:pass@example.org/data?token=secret#fragment") == (
        "https://example.org/data"
    )


def test_eula_error_exposes_only_public_approval_link(monkeypatch):
    http = HTTP(attempts=1)
    response = Response()
    response.ok, response.status_code = False, 403
    response.json = lambda: {
        "error_description": "EULA Acceptance Failure",
        "resolution_url": (
            "https://urs.earthdata.nasa.gov/approve_app?client_id=public-app&token=secret"
        ),
    }
    monkeypatch.setattr(http.session, "get", lambda *a, **k: response)
    with pytest.raises(IngestionError, match="aceite de EULA") as exc:
        http.get("https://data.gesdisc.earthdata.nasa.gov/data/file.nc4")
    assert "client_id=public-app" in str(exc.value)
    assert "secret" not in str(exc.value)
