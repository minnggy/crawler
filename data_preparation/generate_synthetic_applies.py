#!/usr/bin/env python3
"""Create a traceable augmented postings dataset with synthetic applicant counts.

The original `applies` column is never changed. Missing values are filled only in
`applies_for_analysis`, and every generated value is labelled in
`applies_value_source`.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd


SOURCE = Path("/Users/wangmingfang/Downloads/postings.csv")
OUTPUT_DIR = Path("/Users/wangmingfang/Desktop/crawler/data_augmented")
OUTPUT_CSV = OUTPUT_DIR / "postings_with_synthetic_applies.csv"
QA_JSON = OUTPUT_DIR / "synthetic_applies_qa.json"
METHOD_VERSION = "conditional_hotdeck_views_v1"
SEED = 20260820

MODEL_COLUMNS = [
    "job_id",
    "views",
    "applies",
    "formatted_experience_level",
    "remote_allowed",
    "application_type",
    "work_type",
]

VIEW_BINS = [-np.inf, 2, 4, 9, 24, 49, 99, 249, np.inf]
VIEW_LABELS = ["0-2", "3-4", "5-9", "10-24", "25-49", "50-99", "100-249", "250+"]


def clean_category(series: pd.Series, missing: str = "Unknown") -> pd.Series:
    return series.fillna(missing).astype(str).str.strip().replace("", missing)


def prepare_model_frame(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["views_num"] = pd.to_numeric(out["views"], errors="coerce")
    out["applies_num"] = pd.to_numeric(out["applies"], errors="coerce")
    out["experience"] = clean_category(out["formatted_experience_level"])
    out["application"] = clean_category(out["application_type"])
    out["work"] = clean_category(out["work_type"])
    out["remote"] = clean_category(out["remote_allowed"].map({1.0: "Remote", 0.0: "Not remote"}))
    out["view_bin"] = pd.cut(
        out["views_num"].fillna(-1),
        bins=VIEW_BINS,
        labels=VIEW_LABELS,
        include_lowest=True,
    ).astype(str)
    return out


def build_view_pools(frame: pd.DataFrame) -> dict[tuple, np.ndarray]:
    pools: dict[tuple, list[int]] = defaultdict(list)
    valid = frame.loc[frame["views_num"].notna() & (frame["views_num"] > 0)]
    for row in valid.itertuples(index=False):
        view = int(max(1, round(row.views_num)))
        pools[(row.application, row.experience, row.work)].append(view)
        pools[(row.application, row.experience)].append(view)
        pools[(row.application,)].append(view)
        pools[("ALL",)].append(view)
    return {key: np.asarray(values, dtype=np.int32) for key, values in pools.items()}


def build_donor_pools(frame: pd.DataFrame) -> dict[tuple, np.ndarray]:
    pools: dict[tuple, list[float]] = defaultdict(list)
    valid = frame.loc[
        frame["applies_num"].notna()
        & frame["views_num"].notna()
        & (frame["views_num"] > 0)
        & (frame["applies_num"] >= 0)
        & (frame["applies_num"] <= frame["views_num"])
    ]
    for row in valid.itertuples(index=False):
        rate = float(row.applies_num / row.views_num)
        keys = [
            (row.view_bin, row.application, row.experience, row.remote, row.work),
            (row.view_bin, row.application, row.experience, row.remote),
            (row.view_bin, row.application, row.experience),
            (row.view_bin, row.application),
            (row.view_bin,),
            ("ALL",),
        ]
        for key in keys:
            pools[key].append(rate)
    return {key: np.asarray(values, dtype=np.float64) for key, values in pools.items()}


def choose_pool(pools: dict[tuple, np.ndarray], keys: list[tuple], minimum: int = 20) -> np.ndarray:
    for key in keys:
        values = pools.get(key)
        if values is not None and len(values) >= minimum:
            return values
    return pools[("ALL",)]


def simulate_rows(
    frame: pd.DataFrame,
    donor_pools: dict[tuple, np.ndarray],
    view_pools: dict[tuple, np.ndarray],
    rng: np.random.Generator,
    target_mask: pd.Series,
) -> tuple[np.ndarray, np.ndarray]:
    result = frame["applies_num"].to_numpy(dtype=float, copy=True)
    views_used = frame["views_num"].to_numpy(dtype=float, copy=True)

    for pos in np.flatnonzero(target_mask.to_numpy()):
        row = frame.iloc[pos]
        view = views_used[pos]
        if not np.isfinite(view) or view <= 0:
            view_keys = [
                (row.application, row.experience, row.work),
                (row.application, row.experience),
                (row.application,),
                ("ALL",),
            ]
            view_pool = choose_pool(view_pools, view_keys, minimum=30)
            view = float(rng.choice(view_pool))
            views_used[pos] = view

        view_bin = pd.cut(
            pd.Series([view]),
            bins=VIEW_BINS,
            labels=VIEW_LABELS,
            include_lowest=True,
        ).astype(str).iloc[0]
        donor_keys = [
            (view_bin, row.application, row.experience, row.remote, row.work),
            (view_bin, row.application, row.experience, row.remote),
            (view_bin, row.application, row.experience),
            (view_bin, row.application),
            (view_bin,),
            ("ALL",),
        ]
        rate_pool = choose_pool(donor_pools, donor_keys, minimum=20)
        rate = float(rng.choice(rate_pool))

        # Hot-deck scaling preserves the observed application/view relationship.
        # A count of at least 1 matches the source's disclosed applicant domain.
        value = int(np.clip(np.rint(view * rate), 1, max(1, np.rint(view))))
        result[pos] = value

    return np.rint(result), views_used


def distribution(values: np.ndarray) -> dict[str, float]:
    q = np.quantile(values, [0.25, 0.5, 0.75, 0.9, 0.95, 0.99])
    return {
        "count": int(len(values)),
        "p25": float(q[0]),
        "median": float(q[1]),
        "p75": float(q[2]),
        "p90": float(q[3]),
        "p95": float(q[4]),
        "p99": float(q[5]),
        "share_25_plus_pct": float(np.mean(values >= 25) * 100),
        "max": int(np.max(values)),
    }


def holdout_validation(frame: pd.DataFrame) -> dict:
    rng = np.random.default_rng(SEED + 1)
    observed_positions = np.flatnonzero(frame["applies_num"].notna().to_numpy())
    holdout_positions = rng.choice(
        observed_positions,
        size=max(1, int(len(observed_positions) * 0.2)),
        replace=False,
    )
    train = frame.copy()
    train.loc[train.index[holdout_positions], "applies_num"] = np.nan
    donor_pools = build_donor_pools(train)
    view_pools = build_view_pools(train)
    target = pd.Series(False, index=frame.index)
    target.iloc[holdout_positions] = True
    predicted, _ = simulate_rows(frame, donor_pools, view_pools, rng, target)
    actual = frame["applies_num"].to_numpy()[holdout_positions].astype(np.int32)
    pred = predicted[holdout_positions]
    return {
        "rows": int(len(actual)),
        "actual": distribution(actual),
        "predicted": distribution(pred),
        "median_absolute_error": float(np.median(np.abs(actual - pred))),
        "median_absolute_log_error": float(
            np.median(np.abs(np.log1p(actual) - np.log1p(pred)))
        ),
        "within_same_dashboard_bucket_pct": float(
            np.mean(
                np.digitize(actual, [11, 26, 51, 101])
                == np.digitize(pred, [11, 26, 51, 101])
            )
            * 100
        ),
    }


def write_augmented_csv(frame: pd.DataFrame, simulated: np.ndarray) -> None:
    values = dict(zip(frame["job_id"].astype(str), simulated, strict=True))
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with SOURCE.open("r", encoding="utf-8", newline="") as source, OUTPUT_CSV.open(
        "w", encoding="utf-8", newline=""
    ) as output:
        reader = csv.DictReader(source)
        fieldnames = list(reader.fieldnames or []) + [
            "applies_for_analysis",
            "applies_value_source",
            "applies_simulation_version",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for row in reader:
            raw = row.get("applies", "").strip()
            is_observed = raw != ""
            row["applies_for_analysis"] = str(int(float(raw))) if is_observed else str(values[row["job_id"]])
            row["applies_value_source"] = "observed" if is_observed else "synthetic"
            row["applies_simulation_version"] = "none" if is_observed else METHOD_VERSION
            writer.writerow(row)


def main() -> None:
    raw = pd.read_csv(SOURCE, usecols=MODEL_COLUMNS, low_memory=False)
    frame = prepare_model_frame(raw)
    observed_mask = frame["applies_num"].notna()
    missing_mask = ~observed_mask

    validation = holdout_validation(frame)
    rng = np.random.default_rng(SEED)
    donor_pools = build_donor_pools(frame)
    view_pools = build_view_pools(frame)
    filled, views_used = simulate_rows(frame, donor_pools, view_pools, rng, missing_mask)

    observed = frame.loc[observed_mask, "applies_num"].to_numpy(dtype=np.int32)
    synthetic = filled[missing_mask.to_numpy()]
    combined = filled

    known_view_mask = np.isfinite(views_used)
    qa = {
        "source_file": str(SOURCE),
        "output_file": str(OUTPUT_CSV),
        "method_version": METHOD_VERSION,
        "random_seed": SEED,
        "row_count": int(len(frame)),
        "unique_job_id_count": int(frame["job_id"].nunique()),
        "observed_rows": int(observed_mask.sum()),
        "synthetic_rows": int(missing_mask.sum()),
        "original_coverage_pct": float(observed_mask.mean() * 100),
        "analysis_coverage_pct": 100.0,
        "observed_distribution": distribution(observed),
        "synthetic_distribution": distribution(synthetic),
        "combined_distribution": distribution(combined),
        "integrity": {
            "observed_values_unchanged": bool(
                np.array_equal(combined[observed_mask.to_numpy()], observed)
            ),
            "all_analysis_values_integer": bool(np.all(combined == np.rint(combined))),
            "all_analysis_values_at_least_one": bool(np.all(combined >= 1)),
            "values_do_not_exceed_known_views": bool(
                np.all(combined[known_view_mask] <= np.rint(views_used[known_view_mask]))
            ),
            "rows_without_observed_or_imputed_views": int((~known_view_mask).sum()),
            "missing_analysis_values": int(np.isnan(combined.astype(float)).sum()),
        },
        "holdout_validation": validation,
        "caveat": (
            "Synthetic values are conditional estimates for missing applicant counts, "
            "not observed LinkedIn outcomes. Missingness is not random, so the augmented "
            "dataset must keep the source label in all downstream analysis."
        ),
    }

    write_augmented_csv(frame, filled)
    QA_JSON.write_text(json.dumps(qa, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(qa, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
