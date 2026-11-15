"""Prototype real/bogus ranking, trained on labeled injections on real backgrounds.

Real candidates remain unlabeled. A source-like score is not an asteroid probability.
"""

import csv
import hashlib
import json
import multiprocessing as mp
import time
import uuid
from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter, shift

from .zogy import zogy_subtract

FEATURES = [
    "abs_scorr",
    "d_peak",
    "d_min",
    "local_rms",
    "positive_fraction",
    "negative_positive_ratio",
    "psf_correlation",
    "psf_residual",
    "width",
    "ellipticity",
    "asymmetry",
    "concentration",
    "mask_fraction",
    "mask_distance",
]


def extract_features(result, x, y, sign=1, radius=6):
    x, y = int(x), int(y)
    if (
        min(x, y) < radius
        or x + radius >= result["difference"].shape[1]
        or y + radius >= result["difference"].shape[0]
    ):
        return None
    sl = (slice(y - radius, y + radius + 1), slice(x - radius, x + radius + 1))
    d = sign * result["difference"][sl]
    valid = result["valid"][sl]
    if not valid[radius, radius] or valid.sum() < 20:
        return None
    yy, xx = np.mgrid[-radius : radius + 1, -radius : radius + 1]
    annulus = (xx**2 + yy**2 >= 16) & valid
    values = d[annulus] if annulus.any() else d[valid]
    sky = np.median(values)
    rms = max(float(1.4826 * np.median(np.abs(values - sky))), 0.1)
    data = np.where(valid, d - sky, 0)
    pd = result["psf_difference"]
    cy, cx = np.array(pd.shape) // 2
    p = pd[cy - radius : cy + radius + 1, cx - radius : cx + radius + 1]
    if p.shape != data.shape:
        return None
    p = np.where(valid, p, 0)
    amplitude = np.sum(data * p) / max(np.sum(p * p), 1e-12)
    correlation = np.sum(data * p) / max(np.sqrt(np.sum(data**2) * np.sum(p**2)), 1e-12)
    positive = np.maximum(data, 0)
    weight = positive / max(positive.sum(), 1e-12)
    mx, my = np.sum(weight * xx), np.sum(weight * yy)
    covariance = np.array(
        [
            [np.sum(weight * (xx - mx) ** 2), np.sum(weight * (xx - mx) * (yy - my))],
            [np.sum(weight * (xx - mx) * (yy - my)), np.sum(weight * (yy - my) ** 2)],
        ]
    )
    eigenvalues = np.maximum(np.linalg.eigvalsh(covariance), 1e-8)
    bad_y, bad_x = np.nonzero(~valid)
    distance = (
        float(np.min(np.hypot(bad_x - radius, bad_y - radius))) if len(bad_x) else float(radius + 1)
    )
    return dict(
        abs_scorr=float(sign * result["scorr"][y, x]),
        d_peak=float(data.max() / rms),
        d_min=float(data.min() / rms),
        local_rms=rms,
        positive_fraction=float(np.mean(data[valid] > 0)),
        negative_positive_ratio=float(np.maximum(-data, 0).sum() / max(positive.sum(), 1e-12)),
        psf_correlation=float(correlation),
        psf_residual=float(np.mean((data - amplitude * p)[valid] ** 2) / rms**2),
        width=float(np.sqrt(eigenvalues.sum())),
        ellipticity=float(1 - np.sqrt(eigenvalues[0] / eigenvalues[1])),
        asymmetry=float(np.sum(np.abs(data - data[::-1, ::-1])) / max(np.abs(data).sum(), 1e-12)),
        concentration=float(positive[xx**2 + yy**2 <= 4].sum() / max(positive.sum(), 1e-12)),
        mask_fraction=float(np.mean(~valid)),
        mask_distance=distance,
    )


def prepare_pairs(report, products):
    results = []
    for meta in report["pairs"]:
        n, r = meta["science"], meta["reference"]
        results.append(
            zogy_subtract(
                products["images"][n],
                products["images"][r],
                products["psfs"][n],
                products["psfs"][r],
                products["variances"][n],
                products["variances"][r],
                flux_scale=meta["photometry"]["ratio"],
                mask_new=products["masks"][n],
                mask_reference=products["masks"][r],
                astrometric_sigma_xy=meta["astrometric_sigma_xy"],
            )
        )
    return results


def artificial_shape(psf, kind, rng):
    shape = np.zeros((17, 17))
    radius = psf.shape[0] // 2
    shape[8 - radius : 9 + radius, 8 - radius : 9 + radius] = psf
    if kind in ["source", "pointlike_artifact"]:
        return shape
    if kind == "hot_pixel":
        shape[:] = 0
        shape[8, 8] = 1
    elif kind == "dipole":
        shape -= shift(shape, [rng.uniform(-2, 2), rng.uniform(1, 3)], order=1, mode="constant")
    elif kind == "streak":
        original = shape.copy()
        direction = rng.uniform(0, np.pi)
        shape[:] = 0
        for delta in np.linspace(-4, 4, 9):
            shape += shift(
                original,
                [delta * np.sin(direction), delta * np.cos(direction)],
                order=1,
                mode="constant",
            )
    elif kind == "extended":
        shape = gaussian_filter(shape, [rng.uniform(1, 2), rng.uniform(2, 3)])
    elif kind == "ringing":
        shape -= 0.8 * gaussian_filter(shape, 1.5)
    return shape


def build_training_data(report, products, bases, output, samples=900, seed=2026):
    rng = np.random.default_rng(seed)
    rows = []
    kinds = ["hot_pixel", "dipole", "streak", "extended", "ringing", "pointlike_artifact"]
    attempts = 0
    while len(rows) < samples and attempts < samples * 5:
        attempts += 1
        group = int(rng.integers(0, 16))
        x = [22, 44, 66, 88][group % 4] + int(rng.integers(-3, 4))
        y = [22, 44, 66, 88][group // 4] + int(rng.integers(-3, 4))
        pair = int(rng.integers(0, len(bases)))
        if not bases[pair]["valid"][y, x] or abs(bases[pair]["scorr"][y, x]) > 4:
            continue
        label = int(len(rows) % 2 == 0)
        kind = "source" if label else str(rng.choice(kinds))
        meta = report["pairs"][pair]
        n, r = meta["science"], meta["reference"]
        shape = artificial_shape(products["psfs"][n], kind, rng)
        nominal_snr = rng.uniform(6, 20)
        amplitude = nominal_snr * np.sqrt(np.median(products["variances"][n]) / np.sum(shape**2))
        image = products["images"][n].copy()
        image[y - 8 : y + 9, x - 8 : x + 9] += amplitude * shape
        result = zogy_subtract(
            image,
            products["images"][r],
            products["psfs"][n],
            products["psfs"][r],
            products["variances"][n],
            products["variances"][r],
            flux_scale=meta["photometry"]["ratio"],
            mask_new=products["masks"][n],
            mask_reference=products["masks"][r],
            astrometric_sigma_xy=meta["astrometric_sigma_xy"],
        )
        neighborhood = np.where(
            result["valid"][y - 2 : y + 3, x - 2 : x + 3],
            result["scorr"][y - 2 : y + 3, x - 2 : x + 3],
            -np.inf,
        )
        dy, dx = np.unravel_index(np.argmax(neighborhood), neighborhood.shape)
        px, py = x + dx - 2, y + dy - 2
        if result["scorr"][py, px] < 5:
            continue
        features = extract_features(result, px, py)
        if features is None:
            continue
        rows.append(
            dict(
                sample_id=len(rows),
                spatial_group=group,
                x=x,
                y=y,
                pair=pair,
                label=label,
                label_origin="artificial injection on real SPHEREx background",
                injected_kind=kind,
                **features,
            )
        )
    write_csv(Path(output) / "training_samples.csv", rows)
    if len(rows) < 100:
        raise RuntimeError("Not enough usable injection samples.")
    return rows


def write_csv(path, rows):
    path = Path(path)
    if not rows:
        path.write_text("")
        return
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _fit_worker(dataset, destination):
    import xgboost as xgb
    from sklearn.metrics import (
        average_precision_score,
        confusion_matrix,
        precision_recall_fscore_support,
        roc_auc_score,
    )

    start = time.perf_counter()
    data = np.load(dataset)
    train, validation, test = (data[key] for key in ["train", "validation", "test"])
    x, y = data["x"], data["y"]
    dtrain = xgb.DMatrix(x[train], label=y[train], feature_names=FEATURES, nthread=2)
    dval = xgb.DMatrix(x[validation], label=y[validation], feature_names=FEATURES, nthread=2)
    model = xgb.train(
        dict(
            objective="binary:logistic",
            tree_method="hist",
            device="cpu",
            max_depth=3,
            eta=0.08,
            subsample=0.9,
            colsample_bytree=0.9,
            nthread=2,
            seed=2026,
            eval_metric="logloss",
        ),
        dtrain,
        num_boost_round=200,
        evals=[(dval, "validation")],
        early_stopping_rounds=20,
        verbose_eval=False,
    )
    model = model[: model.best_iteration + 1]
    predicted = model.predict(xgb.DMatrix(x[test], feature_names=FEATURES, nthread=2))
    precision, recall, f1, _ = precision_recall_fscore_support(
        y[test], predicted >= 0.5, average="binary", zero_division=0
    )
    metrics = dict(
        status="complete",
        fit_seconds=time.perf_counter() - start,
        n_train=int(train.sum()),
        n_validation=int(validation.sum()),
        n_test=int(test.sum()),
        roc_auc=float(roc_auc_score(y[test], predicted)),
        average_precision=float(average_precision_score(y[test], predicted)),
        precision=float(precision),
        recall=float(recall),
        f1=float(f1),
        confusion_matrix=confusion_matrix(y[test], predicted >= 0.5).tolist(),
        boosting_rounds=int(model.num_boosted_rounds()),
        feature_importance=model.get_score(importance_type="gain"),
        evaluation_domain=str(data["evaluation_domain"])
        if "evaluation_domain" in data
        else "Artificial labels on held-out sky tiles; not confirmed objects",
    )
    destination = Path(destination)
    model.save_model(destination / "model.ubj")
    (destination / "metrics.json").write_text(json.dumps(metrics, indent=2))
    np.savez(
        destination / "test_predictions.npz",
        truth=y[test],
        scores=predicted,
        sample_ids=np.flatnonzero(test),
    )


def fit_bounded(
    rows,
    output,
    timeout=120.0,
    evaluation_domain="Artificial labels on held-out sky tiles",
    split_description="Disjoint sky tiles; no coordinates or artifact tags in model inputs",
    group_partitions=None,
):
    """Hard wall-clock limit covers child imports, DMatrix construction and training."""
    if not 0 < timeout <= 120:
        raise ValueError("Training timeout must be between zero and 120 seconds.")
    output = Path(output)
    groups = np.array([r["spatial_group"] for r in rows])
    all_groups = np.unique(groups)
    shuffled = np.random.default_rng(2026).permutation(all_groups)
    if group_partitions is None:
        train_groups, val_groups, test_groups = shuffled[:10], shuffled[10:13], shuffled[13:]
    else:
        train_groups, val_groups, test_groups = [
            np.asarray(group_partitions[k]) for k in ["train", "validation", "test"]
        ]
        combined = np.concatenate([train_groups, val_groups, test_groups])
        if len(combined) != len(np.unique(combined)) or set(combined) != set(all_groups):
            raise ValueError("Group partitions must be disjoint and cover every group.")
    train, validation, test = [
        np.isin(groups, subset) for subset in [train_groups, val_groups, test_groups]
    ]
    y = np.array([r["label"] for r in rows])
    if any(len(np.unique(y[mask])) < 2 for mask in [train, validation, test]):
        raise ValueError("Both classes are required in each spatial split.")
    dataset = output / "training_matrix.npz"
    np.savez_compressed(
        dataset,
        x=np.array([[r[k] for k in FEATURES] for r in rows]),
        y=y,
        train=train,
        validation=validation,
        test=test,
        evaluation_domain=evaluation_domain,
    )
    destination = output / ("fit_" + uuid.uuid4().hex[:10])
    destination.mkdir()
    start = time.perf_counter()
    process = mp.get_context("spawn").Process(
        target=_fit_worker, args=(str(dataset), str(destination))
    )
    process.start()
    # Keep each wait short; the hard deadline is enforced by the parent process.
    while process.is_alive() and time.perf_counter() - start < timeout:
        process.join(min(0.2, max(0.001, timeout - (time.perf_counter() - start))))
    if process.is_alive():
        process.terminate()
        process.join(1)
        if process.is_alive():
            process.kill()
            process.join(1)
        metrics = dict(
            status="timeout",
            budget_seconds=timeout,
            wall_seconds=time.perf_counter() - start,
            model_used=False,
        )
    elif process.exitcode != 0 or not (destination / "metrics.json").exists():
        metrics = dict(status="failed", child_exitcode=process.exitcode, model_used=False)
    else:
        metrics = json.loads((destination / "metrics.json").read_text())
        metrics.update(
            model_path=str(destination / "model.ubj"),
            wall_seconds=time.perf_counter() - start,
            budget_seconds=timeout,
            model_used=True,
        )
    metrics["split"] = dict(
        train_groups=train_groups.tolist(),
        validation_groups=val_groups.tolist(),
        test_groups=test_groups.tolist(),
        strategy=split_description,
    )
    (output / "training_metrics.json").write_text(json.dumps(metrics, indent=2))
    return metrics


def rank_real(report, bases, metrics, output):
    review_path = Path(output) / "review_labels.csv"
    previous = {}
    if review_path.exists() and review_path.stat().st_size:
        with review_path.open(newline="") as handle:
            for row in csv.DictReader(handle):
                key = (int(row["candidate_id"]), int(row["pair"]), float(row["x"]), float(row["y"]))
                previous[key] = row
    rows = []
    for i, candidate in enumerate(report["candidates"]):
        features = extract_features(
            bases[candidate["pair"]], candidate["x"], candidate["y"], candidate["sign"]
        )
        if features is not None:
            rows.append({"candidate_id": i, **candidate, **features})
    if metrics["status"] == "complete":
        import xgboost as xgb

        model = xgb.Booster({"nthread": 2})
        model.load_model(metrics["model_path"])
        scores = (
            model.predict(
                xgb.DMatrix(
                    np.array([[r[k] for k in FEATURES] for r in rows]),
                    feature_names=FEATURES,
                    nthread=2,
                )
            )
            if rows
            else []
        )
        method = "XGBoost injection-trained source-like score"
    else:
        scores = [np.clip(r["psf_correlation"], 0, 1) * (1 - r["mask_fraction"]) for r in rows]
        method = "Heuristic fallback; XGBoost training did not complete"
    for row, score in zip(rows, scores):
        reviewed = previous.get((row["candidate_id"], row["pair"], row["x"], row["y"]), {})
        human_label = reviewed.get("human_label", "")
        row.update(
            source_like_score=float(score),
            predicted_class="fonte_candidata" if score >= 0.5 else "provavel_artefato",
            human_label=human_label,
            review_notes=reviewed.get("notes", ""),
            label_status="human-reviewed" if human_label else "unlabeled real candidate",
            ranking_method=method,
        )
    rows.sort(key=lambda r: (r["source_like_score"], r["abs_scorr"]), reverse=True)
    for i, row in enumerate(rows, 1):
        row["rank"] = i
    write_csv(Path(output) / "candidate_ranking.csv", rows)
    write_csv(
        Path(output) / "review_labels.csv",
        [
            dict(
                candidate_id=r["candidate_id"],
                pair=r["pair"],
                x=r["x"],
                y=r["y"],
                source_like_score=r["source_like_score"],
                human_label=r["human_label"],
                notes=r["review_notes"],
            )
            for r in rows
        ],
    )
    return rows


def finish_classification(output="outputs/sprints"):
    output = Path(output)
    report = json.loads(Path("outputs/zogy/report.json").read_text())
    products = dict(np.load("outputs/zogy/products.npz"))
    bases = prepare_pairs(report, products)
    metrics = json.loads((output / "training_metrics.json").read_text())
    ranking = rank_real(report, bases, metrics, output)
    n_rows = int(len(np.load(output / "training_matrix.npz")["y"]))
    summary = dict(
        training=metrics,
        n_training_examples=n_rows,
        n_ranked_real_candidates=len(ranking),
        feature_names=FEATURES,
        upstream_products_sha256=hashlib.sha256(
            Path("outputs/zogy/products.npz").read_bytes()
        ).hexdigest(),
        upstream_report_sha256=hashlib.sha256(
            Path("outputs/zogy/report.json").read_bytes()
        ).hexdigest(),
        confirmed_real_training_labels=0,
        label_policy="Known injected sources/artifacts only; actual candidates unlabeled",
        real_candidate_classes_are_predictions=True,
    )
    (output / "sprint2_report.json").write_text(json.dumps(summary, indent=2))
    (output / "candidate_ranking.json").write_text(json.dumps(ranking, indent=2))
    print(
        "Training:", metrics["status"], "; wall seconds:", metrics.get("wall_seconds"), flush=True
    )
    print("Ranked real candidates:", len(ranking), flush=True)
    return summary


def run_classification(output="outputs/sprints", samples=900, timeout=120.0):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    report = json.loads(Path("outputs/zogy/report.json").read_text())
    products = dict(np.load("outputs/zogy/products.npz"))
    bases = prepare_pairs(report, products)
    print("Building labeled injection examples on real backgrounds", flush=True)
    rows = build_training_data(report, products, bases, output, samples)
    print("Examples:", len(rows), "; XGBoost hard limit:", timeout, "seconds", flush=True)
    fit_bounded(rows, output, timeout)
    return finish_classification(output)


if __name__ == "__main__":
    run_classification()
