"""Transporte validado, escrita atômica e proveniência compartilhados pelos coletores."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import requests

LOG = logging.getLogger("ingestion")


class IngestionError(Exception):
    """Falha reportável sem incluir credenciais ou respostas externas nos logs."""


def timestamps():
    now = datetime.now(timezone.utc)
    return {
        "retrieved_at_utc": now.isoformat(),
        "retrieved_at_local": now.astimezone(ZoneInfo("America/Sao_Paulo")).isoformat(),
    }


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def public_url(url):
    """Nunca persistir query assinada nem userinfo de URLs de transferência."""
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.hostname or "", parsed.path, "", ""))


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n")
    os.replace(temporary, path)


class HTTP:
    def __init__(self, attempts=3, timeout=60):
        self.attempts = attempts
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "EarthDetectives-Ingestion/0.1"
        # Não aplicar implicitamente credenciais .netrc a fontes ou links de staging.
        self.session.trust_env = False

    def get(self, url, *, attempts=None, **kwargs):
        if urlsplit(url).scheme != "https":
            raise IngestionError("Somente endpoints HTTPS são aceitos")
        budget = self.attempts if attempts is None else attempts
        for attempt in range(1, budget + 1):
            LOG.info("HTTP tentativa=%s endpoint=%s", attempt, public_url(url))
            try:
                response = self.session.get(url, timeout=self.timeout, **kwargs)
            except requests.RequestException:
                response = None
            if response is not None and response.ok:
                return response
            status = response.status_code if response is not None else "connection_error"
            retry = response is None or status in (408, 429) or status >= 500
            if response is not None:
                response.close()
            if not retry or attempt == budget:
                raise IngestionError(f"Falha HTTP ({status}) em {public_url(url)}")
            LOG.warning("Nova tentativa após falha HTTP (%s)", status)
            time.sleep(min(2 ** (attempt - 1), 20))
        raise IngestionError("Orçamento de tentativas inválido")

    def json(self, url, **kwargs):
        with self.get(url, **kwargs) as response:
            try:
                return response.json()
            except ValueError as exc:
                raise IngestionError("O serviço não retornou JSON válido") from exc

    def download(self, url, destination, validator):
        """Reinicia temporários; só promove arquivos após validar todo o conteúdo."""
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".part")
        for attempt in range(1, self.attempts + 1):
            try:
                with self.get(url, stream=True, attempts=1) as response:
                    expected = response.headers.get("Content-Length")
                    encoded = response.headers.get("Content-Encoding")
                    with temporary.open("wb") as stream:
                        for chunk in response.iter_content(1024 * 1024):
                            stream.write(chunk)
                    if expected and not encoded and temporary.stat().st_size != int(expected):
                        raise IngestionError("Download incompleto: Content-Length incompatível")
                audit = validator(temporary)
                digest = sha256(temporary)
                final = destination.with_name(
                    f"{destination.stem}-{digest[:16]}{destination.suffix}"
                )
                os.replace(temporary, final)
                return final, audit
            except (requests.RequestException, IngestionError, OSError, ValueError) as exc:
                temporary.unlink(missing_ok=True)
                LOG.warning("Transferência/validação falhou; tentativa=%s", attempt)
                if attempt == self.attempts:
                    raise IngestionError(
                        "Transferência falhou ou conteúdo inválido; temporário descartado"
                    ) from exc
                time.sleep(min(2 ** (attempt - 1), 20))


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.path = self.root / "metadata/manifest.json"
        self.data = (
            json.loads(self.path.read_text())
            if self.path.exists()
            else {"schema_version": 1, "files": [], "runs": [], "jobs": {}}
        )

    def save(self):
        atomic_json(self.path, self.data)

    def cached(self, key):
        for entry in reversed(self.data["files"]):
            if entry["request_key"] == key and entry["status"] == "complete":
                path = self.root / entry["path"]
                if path.is_file() and path.stat().st_size == entry["size_bytes"]:
                    if sha256(path) == entry["sha256"]:
                        LOG.info("Arquivo íntegro reutilizado: %s", entry["path"])
                        return entry
                LOG.warning("Arquivo ausente ou corrompido: %s", entry["path"])
        return None

    def record(self, key, path, audit, metadata):
        entry = {
            **metadata,
            **timestamps(),
            "request_key": key,
            "path": str(Path(path).relative_to(self.root)),
            "size_bytes": Path(path).stat().st_size,
            "sha256": sha256(path),
            "status": "complete",
            "audit": audit,
        }
        self.data["files"] = [x for x in self.data["files"] if x["path"] != entry["path"]]
        self.data["files"].append(entry)
        self.save()
        return entry
