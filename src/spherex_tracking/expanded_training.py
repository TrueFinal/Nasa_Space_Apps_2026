"""More real SPHEREx images and Gaia labels, with independent sky-field evaluation."""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

import numpy as np
from astropy.io import fits
from astropy.table import Table, vstack

from .classification import fit_bounded, write_csv
from .observed_training import extract_observed_frames

FIELDS = [
    (134.6917, 16.0303),
    (150.0, 2.0),
    (210.0, 20.0),
    (45.0, 20.0),
    (315.0, -10.0),
    (270.0, 30.0),
    (75.0, -20.0),
    (10.0, -10.0),
]


def acquire_expansion(folder="data/expanded", per_field=8):
    from astroquery.gaia import Gaia
    from astroquery.ipac.irsa import Irsa

    root = Path(folder)
    root.mkdir(parents=True, exist_ok=True)
    records, fields, catalogs, errors = [], [], {}, []
    Irsa.TIMEOUT = Gaia.TIMEOUT = 60
    for field, (ra, dec) in enumerate(FIELDS):
        directory = root / f"field{field}"
        directory.mkdir(exist_ok=True)
        archive_path, gaia_path = directory / "spherex.ecsv", directory / "gaia.ecsv"
        try:
            if not archive_path.exists():
                archive = Irsa.query_sia(pos=(ra, dec, 0.005), collection="spherex_dr1")
                (archive if isinstance(archive, Table) else archive.to_table()).write(archive_path)
            archive = Table.read(archive_path)
            query = (
                "SELECT source_id,ra,dec,ref_epoch,pmra,pmdec,phot_g_mean_mag,ruwe "
                "FROM gaiadr3.gaia_source WHERE 1=CONTAINS(POINT('ICRS',ra,dec),"
                f"CIRCLE('ICRS',{ra},{dec},0.5)) AND phot_g_mean_mag<20"
            )
            if not gaia_path.exists() or len(Table.read(gaia_path)) == 2000:
                Gaia.launch_job_async(query).get_results().write(gaia_path, overwrite=True)
            (directory / "gaia_query.adql").write_text(query)
            catalogs[field] = Table.read(gaia_path)
            selected = archive[np.array(archive["energy_bandpassname"]) == "SPHEREx-D1"]
            distance = ((np.asarray(selected["s_ra"], float) - ra) * np.cos(np.deg2rad(dec))) ** 2
            distance += (np.asarray(selected["s_dec"], float) - dec) ** 2
            selected = selected[np.argsort(distance)]
            # Prefer full spatial coverage, but retain observations across different times.
            selected = selected[: max(per_field * 3, per_field)]
            selected.sort("t_min")
            positions = np.unique(
                np.linspace(0, len(selected) - 1, min(per_field, len(selected))).astype(int)
            )
            chosen = selected[positions]
            for row in chosen:
                url = (
                    str(row["access_url"])
                    + "?"
                    + urlencode({"center": f"{ra},{dec}", "size": "0.6"})
                )
                records.append(
                    dict(
                        field_id=field,
                        ra_deg=ra,
                        dec_deg=dec,
                        obs_id=str(row["obs_id"]),
                        url=url,
                        path=str(directory / (str(row["obs_id"]) + "D1.fits")),
                    )
                )
            fields.append(
                dict(
                    field_id=field,
                    ra_deg=ra,
                    dec_deg=dec,
                    gaia_rows=len(catalogs[field]),
                    archive_rows=len(archive),
                )
            )
            print(
                "Field queried",
                field,
                "Gaia",
                len(catalogs[field]),
                "selected images",
                len(chosen),
                flush=True,
            )
        except Exception as exc:
            errors.append(dict(field_id=field, stage="query", error=str(exc)))
            print("Field query failed", field, str(exc), flush=True)

    def fetch(record):
        path = Path(record["path"])
        if path.exists():
            with fits.open(path) as handle:
                if "IMAGE" in handle and "VARIANCE" in handle:
                    return record
        for attempt in range(3):
            try:
                with urlopen(record["url"], timeout=60) as response:
                    data = response.read()
                partial = path.with_suffix(".partial")
                partial.write_bytes(data)
                with fits.open(partial) as handle:
                    if "EPSF" not in handle or "FLAGS" not in handle:
                        raise ValueError("Incomplete SPHEREx response")
                partial.replace(path)
                print("Downloaded", record["field_id"], path.name, len(data), "bytes", flush=True)
                return record
            except Exception:
                if attempt == 2:
                    raise

    downloaded = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(fetch, r): r for r in records}
        for future in as_completed(futures):
            try:
                downloaded.append(future.result())
            except Exception as exc:
                errors.append(dict(**futures[future], stage="download", error=str(exc)))
    downloaded.sort(key=lambda r: (r["field_id"], r["obs_id"]))
    manifest = dict(
        fields=fields,
        files=downloaded,
        errors=errors,
        cutout_size_deg=0.6,
        collection="spherex_dr1",
        detector=1,
        per_field_target=per_field,
    )
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest, catalogs


def field_split(rows, field_ids):
    if len(field_ids) < 4:
        raise ValueError(
            "At least four observed sky fields are required for independent evaluation."
        )
    train = field_ids[:-3]
    validation, test = field_ids[-3:-2], field_ids[-2:]
    partitions = dict(train=train, validation=validation, test=test)
    kept, seen, removed = [], set(), 0
    # Remove repeated hardware/source identities from later partitions.
    for name in ["train", "validation", "test"]:
        subset = [row for row in rows if row["field_id"] in partitions[name]]
        current_identities = set()
        for row in subset:
            if row["identity"] in seen:
                removed += 1
                continue
            item = dict(row, spatial_group=row["field_id"], partition=name, sample_id=len(kept))
            kept.append(item)
            current_identities.add(row["identity"])
        seen |= current_identities
    return kept, partitions, removed


def run_expanded(output="outputs/expanded", per_field=8, timeout=120.0):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    manifest, catalogs = acquire_expansion(per_field=per_field)
    all_rows, metadata = [], []
    for field in sorted({r["field_id"] for r in manifest["files"]}):
        records = [r for r in manifest["files"] if r["field_id"] == field]
        rows, _, _ = extract_observed_frames(records, catalogs, keep_native=False)
        for row in rows:
            row.update(
                field_id=field,
                obs_id=records[row["epoch"]]["obs_id"],
                fits_path=records[row["epoch"]]["path"],
                sample_id=len(all_rows),
            )
            all_rows.append(row)
        metadata.append(
            dict(
                field_id=field,
                images=len(records),
                samples=len(rows),
                sources=sum(r["label"] for r in rows),
                artifacts=sum(not r["label"] for r in rows),
            )
        )
        print("Field examples extracted", metadata[-1], flush=True)
    Table(vstack([catalogs[k] for k in sorted(catalogs)])).write(
        output / "gaia_catalogs.ecsv", overwrite=True
    )
    write_csv(output / "all_observed_samples.csv", all_rows)
    rows, partitions, removed = field_split(all_rows, sorted({r["field_id"] for r in all_rows}))
    write_csv(output / "training_samples.csv", rows)
    print(
        "Training expanded observed data",
        len(rows),
        "examples; limit",
        timeout,
        "seconds",
        flush=True,
    )
    metrics = fit_bounded(
        rows,
        output,
        timeout,
        evaluation_domain="Observed SPHEREx/Gaia sources vs contamination; independent sky fields",
        split_description="Sky fields held out; repeated Gaia/detector identities excluded",
        group_partitions=partitions,
    )
    report = dict(
        training=metrics,
        fields=metadata,
        n_images=len(manifest["files"]),
        n_fields=len(metadata),
        n_raw_samples=len(all_rows),
        n_training_samples=len(rows),
        n_sources=sum(r["label"] for r in rows),
        n_artifacts=sum(not r["label"] for r in rows),
        n_unique_gaia_sources=len({r["gaia_source_id"] for r in rows if r["label"]}),
        n_gaia_catalog_rows=sum(len(t) for t in catalogs.values()),
        n_repeated_identities_excluded_from_later_splits=removed,
        artificial_samples=0,
        cutout_size_deg=0.6,
        partitions=partitions,
        downloaded_bytes=sum(Path(r["path"]).stat().st_size for r in manifest["files"]),
        acquisition_errors=manifest["errors"],
        model_task="Native observed source vs instrumental contamination; not asteroid identity",
    )
    (output / "expanded_report.json").write_text(json.dumps(report, indent=2))
    if metrics["status"] == "complete":
        registry = dict(
            metrics_path=str((output / "training_metrics.json").resolve()),
            training_report=str((output / "expanded_report.json").resolve()),
            n_training_samples=len(rows),
            n_spherex_images=len(manifest["files"]),
        )
        Path("outputs/active_observed_model.json").write_text(json.dumps(registry, indent=2))
        from .observed_training import run_observed

        run_observed(
            "outputs/expanded_demo", timeout, training_metrics_path=registry["metrics_path"]
        )
    print(
        "EXPANDED COMPLETE",
        len(rows),
        "samples",
        len(manifest["files"]),
        "SPHEREx images",
        flush=True,
    )
    return report


if __name__ == "__main__":
    run_expanded()
