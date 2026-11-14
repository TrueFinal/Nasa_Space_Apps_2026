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
