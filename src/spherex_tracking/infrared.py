"""Zephyr local infrared laboratory: python -m spherex_tracking.infrared --help."""

from __future__ import annotations

import argparse
import json
import socket
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .infrared_archive import (
    available_calibrations,
    fetch_calibration,
    fetch_calibrations,
    prepare_archive,
    validate_request,
)
from .infrared_bands import DETECTOR_BANDS, MAX_EXPOSURES, detectors_for
from .infrared_display import render_comparison
from .infrared_mask import run_manifest, write_json

ROOT = Path(__file__).resolve().parents[2]


class LocalServer(ThreadingHTTPServer):
    """Windows must not allow two development servers to share one port."""

    allow_reuse_address = False
    daemon_threads = True

    def server_bind(self):
        if sys.platform == "win32":
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def synthetic_manifest(directory):
    """Deterministic, explicitly labelled fixture; never an archive fallback."""
    import numpy as np
    from astropy.io import fits
    from astropy.wcs import WCS

    base = Path(directory).resolve()
    base.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(32)
    yy, xx = np.indices((64, 64))
    wcs = WCS(naxis=2)
    wcs.wcs.crpix = [32, 32]
    wcs.wcs.cdelt = [-6.2 / 3600, 6.2 / 3600]
    wcs.wcs.crval = [359.999, 12.0]
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    entries = []
    for i in range(4):
        h = wcs.to_header()
        h.update(
            {
                "DETECTOR": 4,
                "DETCOORD": "sky",
                "BUNIT": "MJy/sr",
                "MJD-AVG": 61000.0 + i * 0.0015,
                "TIMESYS": "UTC",
                "SYNTHET": True,
            }
        )
        x, y = 29 + i * 1.8, 31 + i * 0.3
        image = 0.7 + rng.normal(0, 0.015, xx.shape)
        image += 0.3 * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / 2)
        image += 0.9 * np.exp(-((xx - 42) ** 2 + (yy - 25) ** 2) / 2)
        flags = np.full(xx.shape, 1 << 21, np.uint32)
        flags[5:9, 10] |= 1 << 10
        flags[30:34, 28:36] |= 1 << 19
        hdus = [
            fits.PrimaryHDU(),
            fits.ImageHDU(image.astype("f4"), h, name="IMAGE"),
            fits.ImageHDU(flags, name="FLAGS"),
            fits.ImageHDU(np.full(xx.shape, 0.015**2, "f4"), name="VARIANCE"),
            fits.ImageHDU(np.full(xx.shape, 0.5, "f4"), name="ZODI"),
        ]
        for name, arr in (("CWAVE", 3.4 + (xx - 31.5) * 0.002), ("CBAND", np.full(xx.shape, 0.08))):
            ch = fits.Header({"BUNIT": "um", "DETCOORD": "cutout", "DETECTOR": 4})
            hdus.append(fits.ImageHDU(arr.astype("f4"), ch, name=name))
        path = base / f"synthetic_{i}.fits"
        fits.HDUList(hdus).writeto(path, overwrite=True)
        ra, dec = wcs.all_pix2world(x, y, 0)
        entries.append(
            {
                "fits": path.name,
                "target": {
                    "ra": float(ra),
                    "dec": float(dec),
                    "mjd": h["MJD-AVG"],
                    "frame": "ICRS",
                    "provider": "synthetic fixture",
                    "position_status": "synthetic",
                },
            }
        )
    ra, dec = wcs.all_pix2world(42, 25, 0)
    manifest = {
        "object": "Demonstração sintética — não são dados NASA",
        "synthetic": True,
        "gaia_status": {"status": "synthetic"},
        "gaia": [
            {
                "source_id": "synthetic-star",
                "ra": float(ra),
                "dec": float(dec),
                "pmra": 0.0,
                "pmdec": 0.0,
                "phot_g_mean_mag": 12.0,
            }
        ],
        "exposures": entries,
        "provenance": {"description": "Seed 32; fixture for validation, no discovery claim."},
    }
    path = base / "manifest.json"
    write_json(path, manifest)
    return path


class LabState:
    def __init__(self, output, calibration=None, coordinates=None):
        self.output = Path(output).resolve()
        self.calibration = calibration or str(ROOT / "data/infrared/calibrations")
        self.coordinates = coordinates
        self.jobs = {}
        self.current_output = self.output if (self.output / "report.json").exists() else None
        self.lock = threading.Lock()
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.running = False

    def submit(self, params):
        _, _, _, cfg = validate_request(params)
        missing = set(detectors_for(cfg.low_um, cfg.high_um, cfg.detector)) - set(
            available_calibrations(self.calibration)
        )
        if missing:
            raise ValueError(
                f"Calibrações ausentes: {', '.join(f'D{d}' for d in sorted(missing))}. "
                "Execute calibration --detector all e reinicie com a pasta de calibrações."
            )
        with self.lock:
            if self.running:
                raise ValueError("Já existe uma consulta em processamento.")
            self.running = True
            key = uuid.uuid4().hex
            self.jobs[key] = {"status": "running", "message": "Iniciando consulta"}
        self.executor.submit(self._run, key, params)
        return key

    def _run(self, key, params):
        def progress(message):
            with self.lock:
                self.jobs[key]["message"] = message

        try:
            cache = ROOT / "data" / "infrared" / key
            output = self.output / "runs" / key
            manifest = prepare_archive(params, cache, self.calibration, self.coordinates, progress)
            report = run_manifest(manifest, output, progress=progress)
            progress("Gerando plotagem com cobertura válida")
            render_comparison(report, output)
            write_json(output / "report.json", report)
            with self.lock:
                self.current_output = output
                self.jobs[key] = {"status": "complete", "message": "Análise concluída"}
        except Exception as exc:
            with self.lock:
                self.jobs[key] = {"status": "error", "message": str(exc)}
        finally:
            with self.lock:
                self.running = False


def make_handler(state):
    static = ROOT / "web" / "infrared-mask"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def _send(self, code, payload, content_type="application/json; charset=utf-8", home=False):
            scripts = "'self' 'unsafe-inline'" if home else "'self'"
            data = (
                json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()
                if isinstance(payload, (dict, list))
                else payload
            )
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                f"script-src {scripts}; "
                "font-src 'self' data: https://fonts.gstatic.com; "
                "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'",
            )
            self.end_headers()
            self.wfile.write(data)

        def _local_request(self):
            # Local binding plus DNS-rebinding and cross-origin POST protection.
            host = self.headers.get("Host", "").split(":")[0]
            if host not in ("127.0.0.1", "localhost"):
                return False
            origin = self.headers.get("Origin")
            return not origin or origin == f"http://{self.headers.get('Host')}"

        def do_GET(self):
            if not self._local_request():
                return self._send(403, {"error": "Origem não autorizada"})
            route = unquote(urlsplit(self.path).path)
            if route == "/api/state":
                return self._send(
                    200,
                    {
                        "has_report": state.current_output is not None,
                        "archive_ready": bool(available_calibrations(state.calibration)),
                        "available_detectors": available_calibrations(state.calibration),
                        "bands": [
                            {"detector": d, "low_um": lo, "high_um": hi}
                            for d, (lo, hi) in DETECTOR_BANDS.items()
                        ],
                    },
                )
            if route.startswith("/api/jobs/"):
                with state.lock:
                    job = state.jobs.get(route.rsplit("/", 1)[-1])
                    snapshot = dict(job) if job else None
                return self._send(
                    200 if snapshot else 404, snapshot or {"error": "Consulta inexistente"}
                )
            if route == "/api/report":
                if not state.current_output:
                    return self._send(404, {"error": "Nenhuma análise carregada"})
                return self._send(200, (state.current_output / "report.json").read_bytes())
            if route.startswith("/files/") and state.current_output:
                name = route.removeprefix("/files/")
                allowed = {"report.json", "measurements.csv", "manifest.json", "comparison.png",
                           "color_mosaic.png", "color_mosaic_rgba.png", "color_mosaic.json"} | {
                    f"exposure_{i:02d}.fits" for i in range(MAX_EXPOSURES)
                }
                if name not in allowed or not (state.current_output / name).is_file():
                    return self._send(404, {"error": "Arquivo não encontrado"})
                kind = (
                    "image/png"
                    if name.endswith(".png")
                    else "application/fits"
                    if name.endswith(".fits")
                    else "text/csv; charset=utf-8"
                    if name.endswith(".csv")
                    else "application/json; charset=utf-8"
                )
                return self._send(200, (state.current_output / name).read_bytes(), kind)
            assets = {
                "/lab": ("index.html", "text/html; charset=utf-8"),
                "/lab/": ("index.html", "text/html; charset=utf-8"),
                "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                "/plate.mjs": ("plate.mjs", "text/javascript; charset=utf-8"),
                "/style.css": ("style.css", "text/css; charset=utf-8"),
            }
            if route in assets:
                name, kind = assets[route]
                return self._send(200, (static / name).read_bytes(), kind)
            if route in ("/", "/index.html", "/zephyr_spherex_planet_x_interactive.html"):
                return self._send(
                    200,
                    (ROOT / "web/site/index.html").read_bytes(),
                    "text/html; charset=utf-8",
                    home=True,
                )
            site_assets = {
                "home.css": "text/css",
                "theme.css": "text/css",
                "three.min.js": "text/javascript",
                "OrbitControls.js": "text/javascript",
                "zephyr-logo.svg": "image/svg+xml",
                "three-LICENSE.txt": "text/plain",
                "manifest.json": "application/json",
            }
            if route.startswith("/site-assets/"):
                name = route.removeprefix("/site-assets/")
                if name in site_assets:
                    return self._send(
                        200,
                        (ROOT / "web/site/assets" / name).read_bytes(),
                        site_assets[name] + "; charset=utf-8",
                    )
            return self._send(404, {"error": "Rota não encontrada"})

        def do_POST(self):
            if not self._local_request():
                return self._send(403, {"error": "Origem não autorizada"})
            if self.path != "/api/run":
                return self._send(404, {"error": "Rota não encontrada"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 4096:
                    raise ValueError("Corpo deve conter até 4096 bytes.")
                params = json.loads(self.rfile.read(length))
                if not isinstance(params, dict):
                    raise ValueError("A consulta deve ser um objeto JSON.")
                key = state.submit(params)
                return self._send(202, {"job": key})
            except (ValueError, TypeError, KeyError) as exc:
                return self._send(400, {"error": str(exc)})

    return Handler


def main():
    parser = argparse.ArgumentParser(description="Zephyr · máscara infravermelha SPHEREx / MPC")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Processar FITS/efemérides definidos em um manifesto JSON")
    run.add_argument("manifest")
    run.add_argument("--output", default="outputs/infrared")
    demo = sub.add_parser("demo", help="Gerar e processar dados explicitamente sintéticos")
    demo.add_argument("--output", default="outputs/infrared_demo")
    color = sub.add_parser("colorize-cube", help="Colorir cubo FITS IRSA; somente display IR")
    color.add_argument("cube", help="FITS com IMAGE, WCS-WAVE, NHITS e FLAGS")
    color.add_argument("--output", default="outputs/infrared_color")
    cal = sub.add_parser("calibration", help="Baixar CWAVE/CBAND oficial (33 MB por detector)")
    cal.add_argument("--release", choices=["dr1", "qr3"], default="qr3")
    cal.add_argument("--detector", choices=["all", "1", "2", "3", "4", "5", "6"], default="all")
    cal.add_argument(
        "--output",
        default="data/infrared/calibrations",
        help="Pasta de calibrações; detector único também aceita um caminho .fits",
    )
    archive = sub.add_parser("archive", help="Baixar exposições D1–D6 pelo MOST")
    archive.add_argument("--object", default="1766")
    archive.add_argument("--start", default="2026-07-20")
    archive.add_argument("--end", default="2026-07-25")
    archive.add_argument("--low-um", type=float, default=0.75)
    archive.add_argument("--high-um", type=float, default=5.0)
    archive.add_argument("--max-exposures", type=int, default=12)
    archive.add_argument("--detector", type=int, default=0)
    archive.add_argument("--calibration", default="data/infrared/calibrations")
    archive.add_argument("--coordinates", choices=["sky", "detector"], default="sky")
    archive.add_argument(
        "--mpc-orbit-file", help="Linha de elementos MPC de um asteroide; modo mpc_input do MOST"
    )
    archive.add_argument("--cache", default="data/infrared/archive")
    archive.add_argument("--output", default="outputs/infrared")
    serve = sub.add_parser("serve", help="Abrir o laboratório Zephyr local")
    serve.add_argument("--output", default="outputs/infrared")
    serve.add_argument("--calibration", default="data/infrared/calibrations")
    serve.add_argument("--coordinates", choices=["sky", "detector"], default="sky")
    serve.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    try:
        if args.command == "colorize-cube":
            from .infrared_color import colorize_irsa_cube

            result = colorize_irsa_cube(args.cube, args.output)
            print(json.dumps({"output": str(Path(args.output).resolve()),
                              "channels": result["channels"]}, ensure_ascii=False))
        elif args.command == "calibration":
            if args.detector == "all":
                print(fetch_calibrations(args.output, args.release, print))
            else:
                target = Path(args.output)
                if target.suffix.lower() != ".fits":
                    target = target / f"calibration_D{args.detector}.fits"
                print(fetch_calibration(target, args.release, int(args.detector)))
        elif args.command == "serve":
            if args.calibration and not args.coordinates:
                parser.error("--coordinates é obrigatório quando --calibration é fornecido")
            state = LabState(args.output, args.calibration, args.coordinates)
            server = LocalServer(("127.0.0.1", args.port), make_handler(state))
            print(f"Zephyr: http://127.0.0.1:{server.server_port}/", flush=True)
            try:
                server.serve_forever()
            finally:
                server.server_close()
                state.executor.shutdown(wait=False)
        else:
            if args.command == "demo":
                manifest = synthetic_manifest(ROOT / "data" / "infrared_synthetic")
            elif args.command == "archive":
                params = {
                    k: getattr(args, k)
                    for k in (
                        "object",
                        "start",
                        "end",
                        "low_um",
                        "high_um",
                        "max_exposures",
                        "detector",
                    )
                }
                orbit = (
                    Path(args.mpc_orbit_file).read_text().strip() if args.mpc_orbit_file else None
                )
                manifest = prepare_archive(
                    params,
                    args.cache,
                    args.calibration,
                    args.coordinates,
                    print,
                    mpc_orbit_line=orbit,
                )
            else:
                manifest = args.manifest
            report = run_manifest(manifest, args.output, progress=print)
            render_comparison(report, Path(args.output).resolve())
            write_json(Path(args.output) / "report.json", report)
            print(
                json.dumps(
                    {
                        "output": str(Path(args.output).resolve()),
                        "frames": len(report["frames"]),
                        "synthetic": report["synthetic"],
                    }
                )
            )
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, f"Erro: {exc}\n")


if __name__ == "__main__":
    main()
