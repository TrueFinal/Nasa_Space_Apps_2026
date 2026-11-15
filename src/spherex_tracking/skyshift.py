"""Versioned SkyShift public products and positional context, separate from native science.

No external pixel or flux is added to an aperture measurement. Scripts are run only
by the explicit CLI, in subprocesses, and never by an HTTP request.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import numpy as np

REPOSITORY = "https://github.com/Nsa-2026/skyshift"
DEFAULT_CACHE = Path(__file__).resolve().parents[2] / "data/skyshift"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path, data):
    from .infrared_mask import write_json

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    write_json(Path(path), data)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_git(source, *args):
    # Trust only this explicitly supplied local clone; do not alter global Git config.
    return subprocess.check_output(
        ["git", "-c", f"safe.directory={Path(source).as_posix()}", "-C", str(source), *args],
        text=True,
    ).strip()


def inside(root, name):
    """Accept local relative paths only, including on Windows."""
    if not isinstance(name, str) or "\\" in name or ":" in name:
        raise ValueError("Caminho SkyShift inválido")
    path = (Path(root) / name).resolve()
    if not path.is_relative_to(Path(root).resolve()):
        raise ValueError("Caminho fora dos dados SkyShift")
    return path


def import_public_data(source, output=DEFAULT_CACHE):
    """Snapshot all real public JSON/bin files with hashes; reject broken references."""
    source, output = Path(source).resolve(), Path(output).resolve()
    public = source / "web/public/data"
    if not public.is_dir() or output.is_relative_to(public):
        raise ValueError("Informe o clone SkyShift e um destino separado de web/public/data")
    commit = source_git(source, "rev-parse", "HEAD")
    remote = source_git(source, "remote", "get-url", "origin")
    if remote.removesuffix(".git").lower() != REPOSITORY.lower():
        raise ValueError("O clone deve ter origem em Nsa-2026/skyshift")
    dirty = source_git(source, "status", "--porcelain", "--", "web/public/data", "scripts", "core")
    if dirty:
        raise ValueError("O código e os dados de origem precisam estar sem alterações locais")
    inventory, objects, sets, pixels, missing = {}, [], [], 0, 0
    files = sorted(p for p in public.rglob("*") if p.suffix in (".json", ".bin"))
    referenced = set()
    for path in files:
        if path.is_symlink():
            raise ValueError(f"Link simbólico não aceito: {path}")
        name = path.relative_to(public).as_posix()
        inside(public, name)
        inventory[name] = {"sha256": digest(path), "bytes": path.stat().st_size}
        if path.suffix != ".json":
            continue
        data = load(path)
        if isinstance(data, dict) and "epochs" in data and "size" in data:
            nx, ny = data["size"]
            for epoch in data["epochs"]:
                binary = inside(
                    public, (path.parent.relative_to(public) / epoch["data_url"]).as_posix()
                )
                if binary.suffix != ".bin" or binary.stat().st_size != 2 * nx * ny:
                    raise ValueError(f"Binário com tamanho inválido: {binary}")
                if not all(np.isfinite(epoch[k]) for k in ("scale", "zero")):
                    raise ValueError(f"Calibração numérica inválida: {path}")
                if binary not in referenced:
                    raw = np.fromfile(binary, dtype="<u2")
                    missing += int(np.count_nonzero(raw == 0))
                    pixels += raw.size
                    referenced.add(binary)
            sets.append({"file": name, "clock": data["clock"], "epochs": len(data["epochs"])})
    candidates = load(public / "candidates.json")["candidates"]
    candidate_by_id = {c["id"]: c for c in candidates}
    for path in sorted(public.rglob("object.json")):
        slug = path.parent.relative_to(public).as_posix()
        obj = load(path)
        index_path = path.with_name("index.json")
        if index_path.exists():
            idx = load(index_path)
            choices = [
                {"file": f["file"], "clock": f["clock"], "fov": f["fov"]} for f in idx["frames"]
            ]
            center = idx["center"]
        elif path.with_name("frames.json").exists():
            frame = load(path.with_name("frames.json"))
            choices = [{"file": "frames.json", "clock": frame["clock"], "fov": None}]
            center = frame["center"]
        else:
            # Some published candidate objects have spectra but no precomputed images.
            choices = []
            row = candidate_by_id.get(path.parent.name)
            center = {"ra": row["ra"], "dec": row["dec"]} if row else None
        for choice in choices:
            if f"{slug}/{choice['file']}" not in inventory:
                raise ValueError(f"Conjunto ausente: {slug}/{choice['file']}")
        points = obj.get("spectrum", [])
        infrared = [p for p in points if 0.75 <= p["um"] <= 5]
        objects.append(
            {
                "slug": slug,
                "name": obj.get("name") or slug,
                "center": center,
                "sets": choices,
                "infrared_points": len(infrared),
                "saturated_points": sum(bool(p["saturated"]) for p in infrared),
                "negative_points": sum(p["flux_ujy"] < 0 for p in infrared),
            }
        )
    from collections import Counter

    manifest = {
        "schema_version": 1,
        "repository": REPOSITORY,
        "commit": commit,
        "imported_utc": datetime.now(timezone.utc).isoformat(),
        "files": inventory,
        "objects": objects,
        "summary": {
            "json_files": sum(n.endswith(".json") for n in inventory),
            "binary_files": len(referenced),
            "frame_sets": len(sets),
            "bytes": sum(i["bytes"] for i in inventory.values()),
            "pixels": pixels,
            "no_data_pixels": missing,
            "candidates": len(candidates),
            "kinds": dict(Counter(c["kind"] for c in candidates)),
        },
        "limitations": [
            "Produtos derivados e quantizados; não substituem os FITS originais e sua variância.",
            "Candidatos e notas A/B/C não confirmam descobertas.",
            "Fluxos de épocas e filtros diferentes não formam um espectro simultâneo.",
            "Somente 0,75–5,00 µm é apresentado no explorador espectral.",
        ],
    }
    # Publish the manifest last. An interrupted import cannot advertise a complete new snapshot.
    for path in files:
        target = output / "public" / path.relative_to(public)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    save(output / "manifest.json", manifest)
    return manifest


class PublicData:
    def __init__(self, root=DEFAULT_CACHE):
        self.root = Path(root)
        self.manifest = load(self.root / "manifest.json")
        self.candidates = self.read("candidates.json")["candidates"]

    def file(self, name):
        if name not in self.manifest["files"]:
            raise ValueError("Arquivo fora do manifesto SkyShift")
        path = inside(self.root / "public", name)
        if digest(path) != self.manifest["files"][name]["sha256"]:
            raise ValueError("Arquivo SkyShift alterado; importe novamente a origem")
        return path

    def read(self, name):
        return load(self.file(name))

    def summary(self):
        analysis = (
            load(self.root / "analysis.json") if (self.root / "analysis.json").exists() else None
        )
        if analysis and analysis.get("commit") != self.manifest["commit"]:
            analysis = None
        return {k: v for k, v in self.manifest.items() if k != "files"} | {
            "analysis": analysis,
            "distant": self.read("distant.json"),
        }

    def object(self, slug, frames=None):
        entry = next((o for o in self.manifest["objects"] if o["slug"] == slug), None)
        if not entry:
            raise ValueError("Objeto SkyShift não importado")
        obj = self.read(f"{slug}/object.json")
        obj["spectrum"] = [p for p in obj.get("spectrum", []) if 0.75 <= p["um"] <= 5]
        if not entry["sets"] and not frames:
            return {
                "entry": entry,
                "object": obj,
                "frames": None,
                "repository": REPOSITORY,
                "commit": self.manifest["commit"],
            }
        frames = frames or entry["sets"][0]["file"]
        if frames not in [s["file"] for s in entry["sets"]]:
            raise ValueError("Conjunto de imagens não importado")
        data = self.read(f"{slug}/{frames}")
        for epoch in data["epochs"]:
            name = f"{slug}/{epoch['data_url']}"
            if name not in self.manifest["files"]:
                raise ValueError("Imagem fora do manifesto")
            epoch["data_url"] = f"/skyshift-data/{name}"
        return {
            "entry": entry,
            "object": obj,
            "frames": data,
            "repository": self.manifest["repository"],
            "commit": self.manifest["commit"],
        }

    def context(self, report, radius_arcsec=3):
        """Left association at the published epoch, not a moving-object identity match."""
        rows = self.candidates
        ras = np.radians([c["ra"] for c in rows])
        decs = np.radians([c["dec"] for c in rows])
        matches = []
        samples = report.get("dataset_join", {}).get("samples", [])
        if report.get("synthetic"):
            samples = []  # never claim that a synthetic source matches real observations
        for sample in samples:
            ra, dec = np.radians([sample["ra"], sample["dec"]])
            a = (
                np.sin((decs - dec) / 2) ** 2
                + np.cos(dec) * np.cos(decs) * np.sin((ras - ra) / 2) ** 2
            )
            separations = np.degrees(2 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))) * 3600
            ids = np.flatnonzero(separations <= radius_arcsec)
            for i in sorted(ids, key=lambda i: separations[i])[:20]:
                c = rows[i]
                dt = abs(c["mjd"] - sample["mjd"]) if c.get("mjd") is not None else None
                matches.append(
                    {
                        "sample_id": sample["id"],
                        "candidate_id": c["id"],
                        "kind": c["kind"],
                        "grade": c.get("grade"),
                        "separation_arcsec": float(separations[i]),
                        "delta_days": dt,
                        "epoch_compatible": dt is not None and dt <= 1,
                        "same_detector": c.get("det") == sample["detector"],
                        "association": "positional_context_not_identity",
                        "frames_slug": f"cand/{c['id']}" if c.get("frames_url") else None,
                    }
                )
        return {
            "repository": REPOSITORY,
            "commit": self.manifest["commit"],
            "radius_arcsec": radius_arcsec,
            "epoch_tolerance_days": 1,
            "samples_checked": len(samples),
            "matches": matches,
            "max_candidates_per_sample": 20,
            "positions_propagated": False,
            "measurement_policy": "native_aperture_unchanged",
            "status": "synthetic_not_matched" if report.get("synthetic") else "complete",
        }


@lru_cache(maxsize=2)
def _cached(root, stamp):
    return PublicData(root)


def public_data(root=DEFAULT_CACHE):
    manifest = Path(root) / "manifest.json"
    return _cached(str(Path(root).resolve()), manifest.stat().st_mtime_ns)


def enrich_report(report, root=DEFAULT_CACHE):
    if (Path(root) / "manifest.json").exists():
        report["skyshift_context"] = public_data(root).context(report)
        report.pop("skyshift_photometry", None)
        analysis_path = Path(root) / "analysis.json"
        if analysis_path.exists():
            analysis = load(analysis_path)
            photo = analysis.get("native_photometry", {})
            frames = {f["id"]: f for f in report.get("frames", [])}
            rows = photo.get("rows", [])
            same_inputs = (
                bool(rows)
                and len(rows) == len(frames)
                and all(
                    r["frame_id"] in frames
                    and r.get("fits_sha256") == frames[r["frame_id"]].get("output_sha256")
                    and r.get("primary_measurement") == frames[r["frame_id"]].get("measurement")
                    for r in rows
                )
            )
            if (
                photo.get("report_manifest_sha256") == report.get("manifest_sha256")
                and photo.get("report_manifest_sha256")
                and analysis.get("commit") == report["skyshift_context"]["commit"]
                and same_inputs
            ):
                report["skyshift_photometry"] = photo
    return report


def run_analyses(source, output=DEFAULT_CACHE, report_path=None):
    """Run the upstream aggregation and native-photometry scripts, with explicit scope."""
    import os

    source, output = Path(source).resolve(), Path(output).resolve()
    data = public_data(output)
    commit = source_git(source, "rev-parse", "HEAD")
    if commit != data.manifest["commit"]:
        raise ValueError("Os scripts devem ter a mesma revisão dos dados importados")
    if source_git(source, "status", "--porcelain", "--", "scripts", "core", "web/public/data"):
        raise ValueError("Os scripts/dados de origem foram alterados desde a importação")
    folder = output / "analyses"
    folder.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(source / "core/src") + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    tasks = [
        (
            "build_validation",
            source / "scripts/validate/build_validation.py",
            [
                "--site-data",
                str(output / "public"),
                "--results",
                str(folder / "zone_reports"),
                "--out",
                str(folder / "validation.json"),
                "--suspects-out",
                str(folder / "suspects.json"),
                "--distant-out",
                str(folder / "distant.json"),
            ],
        ),
        (
            "distant",
            source / "scripts/validate/distant.py",
            ["--results", str(folder / "zone_reports"), "--out", str(folder / "distant.json")],
        ),
    ]
    if report_path:
        tasks.append(
            (
                "native_photometry",
                Path(__file__).parents[2] / "scripts/skyshift_photometry.py",
                [
                    "--source",
                    str(source),
                    "--report",
                    str(Path(report_path).resolve()),
                    "--output",
                    str(folder / "native_photometry.json"),
                ],
            )
        )
    runs = []
    for name, script, args in tasks:
        try:
            result = subprocess.run(
                [sys.executable, str(script), *args],
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=300,
            )
            (folder / f"{name}.log").write_text(result.stdout + result.stderr, encoding="utf-8")
            runs.append(
                {
                    "script": script.relative_to(source).as_posix()
                    if script.is_relative_to(source)
                    else script.name,
                    "name": name,
                    "status": "completed" if result.returncode == 0 else "failed",
                    "returncode": result.returncode,
                    "log": f"{name}.log",
                }
            )
        except subprocess.TimeoutExpired:
            runs.append({"name": name, "status": "timeout"})
    succeeded = {r["name"] for r in runs if r["status"] == "completed"}
    validation = load(folder / "validation.json") if "build_validation" in succeeded else {}
    analysis = {
        "repository": REPOSITORY,
        "commit": commit,
        "runs": runs,
        "scope": "aggregation_of_published_measurements_and_separate_native_photometry",
        "checks": [
            {"id": c["id"], "status": c["status"], "headline": c["headline"]}
            for c in validation.get("checks", [])
        ],
        "not_rerun": [
            {
                "scripts": "v1_targets.py, v4_asteroids.py, v6_v7_motion.py",
                "reason": "A agregação usa medidas publicadas; "
                "recuperação/astrometria bruta requer novos recortes.",
            },
            {
                "scripts": "v8_spectra.py, distant_injection.py",
                "reason": "Tabelas Parquet das zonas e órfãos não constam em web/public/data.",
            },
            {
                "scripts": "science/asteroids.py, science/comet.py",
                "reason": "Ajustes físicos completos requerem recortes e geometria Horizons; "
                "não foram inferidos do RGB.",
            },
            {
                "scripts": "precompute/*, candidates/frames.py, demo_check.py",
                "reason": "Produtos públicos foram importados; "
                "não houve novo levantamento nem teste de latência remoto.",
            },
        ],
    }
    photo = folder / "native_photometry.json"
    if "native_photometry" in succeeded and photo.exists():
        analysis["native_photometry"] = load(photo)
    save(output / "analysis.json", analysis)
    return analysis
