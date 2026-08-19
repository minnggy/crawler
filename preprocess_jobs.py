#!/usr/bin/env python3
"""Streaming quality checks and dashboard aggregates for the two job datasets.

The script never loads the multi-GB job_summary.csv into memory.  It writes
cleaned parquet files, quality metrics and small CSV aggregates suitable for a
dashboard.  Original files are read-only.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
except ImportError:  # pragma: no cover - dependency is optional at import time
    pa = pq = None


def _writer(path: Path):
    if pq is None:
        raise RuntimeError("pyarrow is required: pip install pyarrow")
    return None


def _append_parquet(df: pd.DataFrame, path: Path, state: dict):
    # Fallback for environments without pyarrow: stream to CSV instead.
    if pq is None:
        df.to_csv(path, mode="a", header=not state.get("written", False), index=False)
        state["written"] = True
        return
    table = pa.Table.from_pandas(df, preserve_index=False)
    if state.get("writer") is None:
        state["schema"] = table.schema
        state["writer"] = pq.ParquetWriter(path, state["schema"], compression="zstd")
    elif not table.schema.equals(state["schema"], check_metadata=False):
        # CSV chunks can infer a nullable text column as float in a later
        # chunk; cast to the first chunk's schema for stable append semantics.
        table = table.cast(state["schema"], safe=False)
    state["writer"].write_table(table)


def _finish(state):
    if state.get("writer") is not None:
        state["writer"].close()


def _clean_text(s: pd.Series) -> pd.Series:
    return s.astype("string").str.replace(r"\s+", " ", regex=True).str.strip()


def _quality_template():
    return {"rows": 0, "duplicate_key": 0, "nulls": Counter(), "invalid_dates": 0,
            "invalid_salary": 0, "orphan_rows": 0}


def process_postings(path: Path, out: Path, chunksize: int, max_chunks: int | None = None) -> dict:
    q = _quality_template(); state = {}; agg = defaultdict(Counter); salaries = []
    parquet = out / ("postings_clean.parquet" if pq is not None else "postings_clean.csv")
    for i, chunk in enumerate(pd.read_csv(path, chunksize=chunksize, low_memory=False)):
        if max_chunks is not None and i >= max_chunks: break
        q["rows"] += len(chunk)
        key = chunk.get("job_posting_url", pd.Series(index=chunk.index, dtype="string")).astype("string").str.strip()
        q["duplicate_key"] += int(key.duplicated().sum())
        for c in chunk.columns:
            q["nulls"][c] += int(chunk[c].isna().sum())
        for c in ["listed_time", "original_listed_time", "expiry", "closed_time"]:
            if c in chunk:
                dt = pd.to_datetime(chunk[c], unit="ms", errors="coerce", utc=True)
                q["invalid_dates"] += int(((chunk[c].notna()) & dt.isna()).sum())
                chunk[c] = dt
        for c in ["title", "company_name", "location", "description"]:
            if c in chunk: chunk[c] = _clean_text(chunk[c])
        if "normalized_salary" in chunk:
            sal = pd.to_numeric(chunk["normalized_salary"], errors="coerce")
            q["invalid_salary"] += int((sal < 0).sum())
            salaries.extend(sal[(sal > 0) & (sal <= 1_000_000)].dropna().tolist())
        for c in ["formatted_work_type", "work_type", "formatted_experience_level"]:
            if c in chunk:
                agg[c].update(chunk[c].dropna().astype(str).str.strip())
        _append_parquet(chunk, parquet, state)
    _finish(state)
    summary = pd.DataFrame([{"category": k, "value": v, "count": n} for k, vals in agg.items() for v, n in vals.items()])
    if not summary.empty: summary.to_csv(out / "postings_category_summary.csv", index=False)
    q["salary_valid_rows"] = len(salaries)
    q["salary_median"] = float(pd.Series(salaries).median()) if salaries else None
    return q


def process_archive(archive: Path, out: Path, chunksize: int, max_chunks: int | None = None) -> dict:
    master_path = archive / "linkedin_job_postings.csv"
    q = _quality_template(); state = {}; agg = defaultdict(Counter)
    db = sqlite3.connect(out / "_job_keys.sqlite")
    db.execute("CREATE TABLE IF NOT EXISTS keys (job_link TEXT PRIMARY KEY)")
    parquet = out / ("archive_jobs_clean.parquet" if pq is not None else "archive_jobs_clean.csv")
    for i, chunk in enumerate(pd.read_csv(master_path, chunksize=chunksize, low_memory=False)):
        if max_chunks is not None and i >= max_chunks: break
        q["rows"] += len(chunk)
        if "job_link" in chunk:
            links = chunk["job_link"].astype("string").str.strip()
            q["duplicate_key"] += int(links.duplicated().sum())
            db.executemany("INSERT OR IGNORE INTO keys(job_link) VALUES (?)", ((x,) for x in links.dropna()))
        for c in chunk.columns: q["nulls"][c] += int(chunk[c].isna().sum())
        for c in ["first_seen", "last_processed_time"]:
            if c in chunk:
                dt = pd.to_datetime(chunk[c], errors="coerce", utc=True)
                q["invalid_dates"] += int(((chunk[c].notna()) & dt.isna()).sum()); chunk[c] = dt
        for c in ["job_title", "company", "job_location", "search_city", "search_country"]:
            if c in chunk: chunk[c] = _clean_text(chunk[c])
        for c in ["job_type", "job_level", "search_country"]:
            if c in chunk: agg[c].update(chunk[c].dropna().astype(str).str.strip())
        _append_parquet(chunk, parquet, state)
    _finish(state); db.commit()
    for fn, col in [("job_skills.csv", "job_skills"), ("job_summary.csv", "job_summary")]:
        p = archive / fn; count = covered = 0; miss = 0
        if p.exists():
            for i, chunk in enumerate(pd.read_csv(p, chunksize=chunksize, usecols=["job_link", col], on_bad_lines="skip")):
                if max_chunks is not None and i >= max_chunks: break
                count += len(chunk); chunk["job_link"] = chunk["job_link"].astype("string").str.strip()
                covered += sum(1 for x in chunk["job_link"].dropna() if db.execute("SELECT 1 FROM keys WHERE job_link=?", (str(x),)).fetchone())
                miss += int(chunk[col].isna().sum())
        q[fn.replace(".csv", "_rows")] = count; q[fn.replace(".csv", "_covered")] = covered; q[fn.replace(".csv", "_missing_content")] = miss
    rows = [{"category": k, "value": v, "count": n} for k, vals in agg.items() for v, n in vals.items()]
    if rows: pd.DataFrame(rows).to_csv(out / "archive_category_summary.csv", index=False)
    db.close(); (out / "_job_keys.sqlite").unlink(missing_ok=True)
    return q


def write_quality(report: dict, out: Path):
    serial = {}
    for name, q in report.items():
        serial[name] = {k: (dict(v) if isinstance(v, Counter) else v) for k, v in q.items()}
    (out / "data_quality_report.json").write_text(json.dumps(serial, ensure_ascii=False, indent=2, default=str))
    rows = []
    for ds, q in serial.items():
        rows += [{"dataset": ds, "metric": k, "value": v} for k, v in q.items() if k != "nulls"]
        rows += [{"dataset": ds, "metric": f"nulls.{k}", "value": v} for k, v in q.get("nulls", {}).items()]
    pd.DataFrame(rows).to_csv(out / "data_quality_report.csv", index=False)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--postings", type=Path, required=True); ap.add_argument("--archive", type=Path, required=True); ap.add_argument("--output", type=Path, default=Path("processed_jobs")); ap.add_argument("--chunksize", type=int, default=50_000); ap.add_argument("--dry-run", action="store_true", help="process only one chunk per input")
    a = ap.parse_args(); a.output.mkdir(parents=True, exist_ok=True); limit = 1 if a.dry_run else None
    report = {"postings": process_postings(a.postings, a.output, a.chunksize, limit), "archive": process_archive(a.archive, a.output, a.chunksize, limit)}
    write_quality(report, a.output); print(json.dumps({k: {"rows": v["rows"], "duplicate_key": v["duplicate_key"]} for k, v in report.items()}, ensure_ascii=False))


if __name__ == "__main__": main()
