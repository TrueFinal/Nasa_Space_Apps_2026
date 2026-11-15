"""Import the public SkyShift snapshot, run available scripts and enrich a report."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from spherex_tracking.skyshift import (  # noqa: E402
    DEFAULT_CACHE,
    enrich_report,
    import_public_data,
    load,
    run_analyses,
    save,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="Clone Nsa-2026/skyshift")
    parser.add_argument("--output", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--report", type=Path, help="report.json local a enriquecer")
    parser.add_argument("--run-scripts", action="store_true")
    parser.add_argument(
        "--receipt", type=Path, help="Salvar recibo compacto e versionável da execução"
    )
    args = parser.parse_args()
    manifest = import_public_data(args.source, args.output)
    analysis = run_analyses(args.source, args.output, args.report) if args.run_scripts else None
    if args.report:
        report = enrich_report(load(args.report), args.output)
        save(args.report, report)
        save(args.report.parent / "skyshift_context.json", report["skyshift_context"])
        if "skyshift_photometry" in report:
            save(args.report.parent / "skyshift_photometry.json", report["skyshift_photometry"])
    if args.receipt:
        inventory = json.dumps(manifest["files"], sort_keys=True, separators=(",", ":")).encode()
        receipt = {
            "repository": manifest["repository"],
            "commit": manifest["commit"],
            "imported_utc": manifest["imported_utc"],
            "summary": manifest["summary"],
            "inventory_sha256": hashlib.sha256(inventory).hexdigest(),
            "objects_with_spectra": len(manifest["objects"]),
            "objects_with_images": sum(bool(o["sets"]) for o in manifest["objects"]),
            "analysis": analysis,
        }
        if args.report:
            receipt["local_context"] = report["skyshift_context"]
        save(args.receipt, receipt)
    print(
        json.dumps(
            {
                "commit": manifest["commit"],
                "summary": manifest["summary"],
                "scripts": analysis["runs"] if analysis else [],
            },
            ensure_ascii=False,
        )
    )
    if analysis and any(r["status"] != "completed" for r in analysis["runs"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
