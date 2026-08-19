"""Reusable preprocessing for job-posting datasets (salary, geography, taxonomy, text).

Functions accept pandas.DataFrame objects and preserve raw values.  They are intentionally
source-agnostic so both ``postings.csv`` and the archive tables can be processed.
"""
from __future__ import annotations

import html
import re
import unicodedata
from typing import Iterable

import pandas as pd


_WS = re.compile(r"\s+")
_HTML = re.compile(r"<[^>]+>")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
_PHONE = re.compile(r"(?<!\d)(?:\+?\d[\d .()\-]{7,}\d)(?!\d)")


def clean_text(value, redact_pii: bool = False):
    """Normalize HTML/Unicode whitespace while retaining nulls and optionally masking PII."""
    if pd.isna(value):
        return pd.NA
    text = html.unescape(unicodedata.normalize("NFKC", str(value)))
    text = _HTML.sub(" ", text).replace("\u200b", " ")
    if redact_pii:
        text = _EMAIL.sub("[EMAIL]", text)
        text = _PHONE.sub("[PHONE]", text)
    return _WS.sub(" ", text).strip() or pd.NA


def _numeric(series):
    # Handles "$120,000", "120k", and ordinary numeric values.
    s = series.astype("string").str.replace(",", "", regex=False).str.replace(r"[$€£¥]", "", regex=True).str.strip()
    multiplier = s.str.lower().str.endswith("k")
    out = pd.to_numeric(s.str.rstrip("kK"), errors="coerce")
    return out.where(~multiplier, out * 1000)


def normalize_salary(df: pd.DataFrame) -> pd.DataFrame:
    """Add validated and annualized salary fields without dropping original columns."""
    out = df.copy()
    # Keep source values even when a canonical alias is used.
    aliases = {"min_salary": "salary_min", "max_salary": "salary_max", "med_salary": "salary_median"}
    for src, canonical in aliases.items():
        if src in out.columns:
            out[f"{canonical}_raw"] = out[src]
            out[canonical] = _numeric(out[src])
        elif canonical not in out.columns:
            out[canonical] = pd.NA
            out[f"{canonical}_raw"] = pd.NA
        else:
            out[f"{canonical}_raw"] = out[canonical]
            out[canonical] = _numeric(out[canonical])
    if "normalized_salary" in out.columns:
        out["normalized_salary_raw"] = out["normalized_salary"]
        out["normalized_salary"] = _numeric(out["normalized_salary"])
    else:
        out["normalized_salary"] = pd.NA
        out["normalized_salary_raw"] = pd.NA
    if "currency" in out.columns:
        out["salary_currency"] = out["currency"].astype("string").str.upper().str.strip()
    else:
        out["salary_currency"] = pd.NA
    if "pay_period" in out.columns:
        out["salary_period"] = out["pay_period"].astype("string").str.upper().str.strip()
    else:
        out["salary_period"] = pd.NA

    out["salary_missing"] = out[["salary_min", "salary_max", "salary_median", "normalized_salary"]].isna().all(axis=1)
    out["salary_nonnegative"] = out[["salary_min", "salary_max", "salary_median"]].ge(0).all(axis=1, skipna=True)
    out["salary_order_valid"] = (
        out["salary_min"].isna() | out["salary_max"].isna() | (out["salary_min"] <= out["salary_max"])
    )
    # Prefer normalized salary, then midpoint; annualization requires a known period.
    base = out["normalized_salary"].where(out["normalized_salary"].notna())
    midpoint = (out["salary_min"] + out["salary_max"]) / 2
    base = base.where(base.notna(), midpoint)
    factors = {"HOURLY": 2080, "MONTHLY": 12, "WEEKLY": 52, "BIWEEKLY": 26, "YEARLY": 1, "ANNUAL": 1}
    period = out["salary_period"]
    out["salary_annualized"] = base * period.map(factors)
    out["salary_conversion_assumption"] = period.map({k: (f"{v}x {k.lower()} salary" if v != 1 else "already annual") for k, v in factors.items()})
    out.loc[out["salary_annualized"].isna(), "salary_conversion_assumption"] = pd.NA
    out["salary_outlier_flag"] = (out["salary_annualized"] <= 0) | (out["salary_annualized"] > 1_000_000)
    out["salary_valid_for_analysis"] = out["salary_annualized"].gt(0) & out["salary_annualized"].le(1_000_000) & out["salary_order_valid"]
    return out


def _split_location(value):
    if pd.isna(value):
        return pd.Series({"country": pd.NA, "region": pd.NA, "city": pd.NA})
    text = clean_text(value)
    parts = [p.strip() for p in str(text).split(",") if p.strip()]
    if not parts:
        return pd.Series({"country": pd.NA, "region": pd.NA, "city": pd.NA})
    countries = {"US": "United States", "USA": "United States", "UNITED STATES": "United States", "UK": "United Kingdom", "CANADA": "Canada", "AUSTRALIA": "Australia"}
    country = countries.get(parts[-1].upper(), parts[-1] if len(parts) > 2 else pd.NA)
    city = parts[0]
    region = parts[1] if len(parts) > 2 else (parts[1] if len(parts) == 2 and parts[1] != country else pd.NA)
    if len(parts) == 2 and country is pd.NA:
        country, region = pd.NA, parts[1]
    return pd.Series({"country": country, "region": region, "city": city})


def normalize_geography(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    location_col = next((c for c in ("location", "job_location") if c in out.columns), None)
    if location_col:
        out["location_raw"] = out[location_col]
        loc = out[location_col].apply(_split_location)
    else:
        loc = pd.DataFrame(index=out.index, data={"country": pd.NA, "region": pd.NA, "city": pd.NA})
    for c in ("search_country", "search_city"):
        if c in out.columns:
            if c == "search_country":
                loc["country"] = loc["country"].fillna(out[c].astype("string").str.strip())
            else:
                loc["city"] = loc["city"].fillna(out[c].astype("string").str.strip())
    out["country"], out["region"], out["city"] = loc["country"], loc["region"], loc["city"]
    out["location_missing"] = out[["country", "city"]].isna().all(axis=1)
    return out


def _first_match(text, rules):
    for label, pattern in rules:
        if re.search(pattern, text, flags=re.I):
            return label
    return "Other"


def normalize_taxonomy(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    work = out.get("formatted_work_type", out.get("work_type", pd.Series(pd.NA, index=out.index))).astype("string").str.strip()
    out["work_type_raw"] = work
    out["work_type_standard"] = work.str.lower().map({"full-time": "Full-time", "part-time": "Part-time", "contract": "Contract", "temporary": "Temporary", "internship": "Internship", "volunteer": "Volunteer"}).fillna("Other")
    arrangement = out.get("job_type", pd.Series(pd.NA, index=out.index)).astype("string").str.title()
    if "remote_allowed" in out.columns:
        arrangement = arrangement.where(arrangement.notna(), out["remote_allowed"].map({1: "Remote", True: "Remote", 0: "Unknown", False: "Unknown"}))
    out["work_arrangement"] = arrangement.where(arrangement.isin(["Onsite", "Hybrid", "Remote"]), "Unknown")
    exp = out.get("formatted_experience_level", out.get("job_level", pd.Series(pd.NA, index=out.index))).astype("string").str.strip()
    out["experience_level_raw"] = exp
    out["experience_level_standard"] = exp.str.lower().map({"entry level": "Entry-level", "associate": "Associate", "mid-senior level": "Mid-level", "mid senior": "Mid-level", "senior": "Senior", "manager": "Manager", "director": "Director"}).fillna("Unknown")
    title = out.get("title", out.get("job_title", pd.Series("", index=out.index))).fillna("").astype(str)
    rules = [("Data/Analytics", r"data|analyst|analytics|business intelligence"), ("Software/Engineering", r"engineer|developer|software|devops|architect"), ("Sales", r"sales|account executive|business development"), ("Marketing", r"marketing|seo|content|brand"), ("Finance", r"finance|accountant|financial|audit"), ("Human Resources", r"human resources|recruit|talent"), ("Healthcare", r"nurse|medical|healthcare|clinical")]
    out["job_family"] = title.str.lower().map(lambda x: _first_match(x, rules))
    return out


def normalize_text_and_skills(df: pd.DataFrame, redact_pii: bool = False) -> pd.DataFrame:
    out = df.copy()
    for c in ("description", "job_summary", "skills_desc", "job_skills"):
        if c in out.columns:
            out[f"{c}_clean"] = out[c].map(lambda x: clean_text(x, redact_pii=redact_pii))
    skill_col = next((c for c in ("job_skills", "skills_desc") if c in out.columns), None)
    if skill_col:
        out["skills_raw"] = out[skill_col]
        out["skills_clean"] = out[f"{skill_col}_clean"].astype("string").str.lower().str.replace(r"\s+", " ", regex=True)
        out["has_skills"] = out["skills_clean"].notna()
    else:
        out["skills_raw"], out["skills_clean"] = pd.NA, pd.NA
        out["has_skills"] = False
    out["has_summary"] = out.get("job_summary_clean", pd.Series(pd.NA, index=out.index)).notna()
    return out


def preprocess_dataframe(df: pd.DataFrame, redact_pii: bool = False) -> pd.DataFrame:
    """Run all normalization steps in a stable, composable order."""
    return normalize_text_and_skills(normalize_taxonomy(normalize_geography(normalize_salary(df)),), redact_pii=redact_pii)
