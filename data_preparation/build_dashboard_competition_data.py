#!/usr/bin/env python3
"""Build skill-level applicant competition profiles for the dashboard.

The dashboard uses the original applicant count when it exists and the
traceable synthetic value otherwise. Skill matching follows the dashboard's
canonical aliases after punctuation and spacing are normalized.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path("/Users/wangmingfang/Desktop/crawler")
HTML = ROOT / "site/public/job-radar-p0-final.html"
SOURCE = ROOT / "data_augmented/postings_with_synthetic_applies.csv"
OUTPUT = ROOT / "site/public/competition-synthetic-data.js"


def canonical_data() -> dict:
    for line in HTML.read_text(encoding="utf-8").splitlines():
        if line.startswith("window.CANONICAL_SKILL_DATA="):
            return json.loads(line.split("=", 1)[1].removesuffix(";"))
    raise RuntimeError("CANONICAL_SKILL_DATA was not found")


def normalized_phrase(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def distribution(values: np.ndarray) -> list[list[object]]:
    return [
        ["1–10 人", int(np.sum((values >= 1) & (values <= 10)))],
        ["11–25 人", int(np.sum((values >= 11) & (values <= 25)))],
        ["26–50 人", int(np.sum((values >= 26) & (values <= 50)))],
        ["51–100 人", int(np.sum((values >= 51) & (values <= 100)))],
        ["101 人以上", int(np.sum(values >= 101))],
    ]


def metrics(values: np.ndarray) -> dict:
    return {
        "validRows": int(len(values)),
        "median": float(np.median(values)),
        "p75": float(np.quantile(values, 0.75)),
        "highCompetitionPct": round(float(np.mean(values >= 25) * 100), 1),
        "distribution": distribution(values),
    }


def profile(frame: pd.DataFrame, mask: pd.Series) -> dict:
    selected = frame.loc[mask]
    values = selected["applies_for_analysis"].to_numpy(dtype=np.int64)
    observed_values = selected.loc[
        selected["applies_value_source"] == "observed", "applies_for_analysis"
    ].to_numpy(dtype=np.int64)
    synthetic_values = selected.loc[
        selected["applies_value_source"] == "synthetic", "applies_for_analysis"
    ].to_numpy(dtype=np.int64)
    observed_rows = int((selected["applies_value_source"] == "observed").sum())
    synthetic_rows = int((selected["applies_value_source"] == "synthetic").sum())
    matched_rows = int(len(selected))
    result = {
        "matchedRows": matched_rows,
        "validRows": matched_rows,
        "coveragePct": 100.0,
        "observedRows": observed_rows,
        "syntheticRows": synthetic_rows,
        "observedCoveragePct": round(observed_rows / matched_rows * 100, 1),
        "syntheticCoveragePct": round(synthetic_rows / matched_rows * 100, 1),
        "observed": metrics(observed_values),
        "synthetic": metrics(synthetic_values),
        "combined": metrics(values),
    }
    # Keep the public values at the top level so existing consumers default to
    # the trustworthy metric instead of silently combining estimated rows.
    result.update(metrics(observed_values))
    return result


def main() -> None:
    canonical = canonical_data()
    frame = pd.read_csv(
        SOURCE,
        usecols=["description", "applies_for_analysis", "applies_value_source"],
        low_memory=False,
    )
    descriptions = (
        frame["description"]
        .fillna("")
        .str.lower()
        .str.replace(r"[^a-z0-9]+", " ", regex=True)
        .str.strip()
        .radd(" ")
        .add(" ")
    )

    aliases: dict[str, set[str]] = {key: set() for key in canonical["labels"]}
    for alias, key in canonical["aliases"].items():
        aliases[key].add(normalized_phrase(alias))

    profiles = {}
    for key in canonical["labels"]:
        mask = pd.Series(False, index=frame.index)
        for alias in sorted(aliases[key], key=len, reverse=True):
            mask |= descriptions.str.contains(f" {alias} ", regex=False)
        profiles[key] = profile(frame, mask)

    overall_mask = pd.Series(True, index=frame.index)
    overall = profile(frame, overall_mask)
    payload = {
        "sourceRows": int(len(frame)),
        "validRows": int(len(frame)),
        "methodVersion": "conditional_hotdeck_views_v1",
        "usesSynthetic": True,
        "overall": overall,
        "profiles": profiles,
    }
    OUTPUT.write_text(
        "window.SYNTHETIC_COMPETITION_DATA="
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        + ";\n",
        encoding="utf-8",
    )

    for key, item in profiles.items():
        print(
            f"{canonical['labels'][key]:24} rows={item['matchedRows']:6,} "
            f"observed={item['observedCoveragePct']:5.1f}% median={item['median']:g}"
        )


if __name__ == "__main__":
    main()
