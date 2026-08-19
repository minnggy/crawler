#!/usr/bin/env python3
"""Create a small archive preview that definitely includes skills/summary text."""
import argparse, csv, hashlib, re
from pathlib import Path

ID_RE = re.compile(r"(?:-|/)(\d{7,})(?:[/?#]|$)")

def clean(v):
    return re.sub(r"\s+", " ", (v or "").replace("\ufeff", "")).strip()

def canonical(v):
    return clean(v).split("#", 1)[0].split("?", 1)[0].rstrip("/")

def job_key(url):
    m = ID_RE.search(url)
    return "linkedin:" + m.group(1) if m else "url:" + hashlib.sha1(url.encode()).hexdigest()

def read_content(path, column, limit):
    out = {}
    with path.open(encoding="utf-8-sig", newline="", errors="replace") as f:
        for i, row in enumerate(csv.DictReader(f)):
            if i >= limit:
                break
            u = canonical(row.get("job_link"))
            if u:
                out[u] = clean(row.get(column))
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--rows", type=int, default=100)
    a = ap.parse_args(); a.output.parent.mkdir(parents=True, exist_ok=True)
    skills = read_content(a.archive / "job_skills.csv", "job_skills", a.rows)
    summaries = read_content(a.archive / "job_summary.csv", "job_summary", a.rows)
    wanted = set(skills) | set(summaries)
    fields = ["job_key", "source_dataset", "snapshot_date", "job_link", "job_title", "company", "job_location", "job_skills", "job_summary"]
    found = 0
    with (a.archive / "linkedin_job_postings.csv").open(encoding="utf-8-sig", newline="", errors="replace") as src, a.output.open("w", encoding="utf-8", newline="") as dst:
        w = csv.DictWriter(dst, fieldnames=fields); w.writeheader()
        for row in csv.DictReader(src):
            u = canonical(row.get("job_link"))
            if u not in wanted:
                continue
            w.writerow({"job_key": job_key(u), "source_dataset": "archive", "snapshot_date": clean(row.get("first_seen"))[:10], "job_link": u, "job_title": clean(row.get("job_title")), "company": clean(row.get("company")), "job_location": clean(row.get("job_location")), "job_skills": skills.get(u, ""), "job_summary": summaries.get(u, "")})
            found += 1
    print(f"content rows: {len(wanted)}, matched master rows: {found}")

if __name__ == "__main__": main()
