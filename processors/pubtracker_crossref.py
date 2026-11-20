"""Optional PubTracker corroboration check for Dimensions-based ORD funding tags.

PubTracker is a manually user-submitted system and only covers a subset of VA
publications, so it is never used to replace or lower the bar for the text-based
ORD funding evidence in `ord_portfolio.py` - only to corroborate it for the subset
of records that were also submitted to PubTracker. This module is intentionally
additive: callers can ignore it entirely (e.g. via a dashboard toggle left off) to
get the exact same ORD numbers as before this cross-reference existed.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

PUBTRACKER_EXPORT_DIR = Path("PubTracker Export")
EXPORT_NAME = re.compile(r"^submissionlist(\d{14})(?:-[\w.]+)?\.(?:xlsx|xls|csv)$", re.IGNORECASE)


def _normalize_title(title) -> str:
    if not isinstance(title, str):
        return ""
    text = re.sub(r"[^a-z0-9 ]+", " ", title.lower())
    return re.sub(r"\s+", " ", text).strip()


def find_export_set(directory: Path = PUBTRACKER_EXPORT_DIR) -> list[Path]:
    """All exports sharing the newest `submissionlist<YYYYMMDDHHMMSS>` timestamp (e.g. one file per year).

    Older exports in the folder are ignored so submissions are never double counted. When nothing is
    found, returns a single non-existent placeholder path so callers report a clear "not found" message.
    """
    stamped = {}
    for path in directory.glob("submissionlist*") if directory.exists() else []:
        match = EXPORT_NAME.match(path.name)
        if match:
            stamped.setdefault(match.group(1), []).append(path)
    if not stamped:
        return [directory / "submissionlist<YYYYMMDDHHMMSS>-<label>.xlsx (none found)"]
    return sorted(stamped[max(stamped)])


def read_export(path: Path) -> pd.DataFrame:
    """Read one PubTracker export (.xlsx/.xls or .csv)."""
    if Path(path).suffix.lower() == ".csv":
        return pd.read_csv(path, encoding="utf-8-sig")
    return pd.read_excel(path, sheet_name=0)


def find_latest_export(directory: Path = PUBTRACKER_EXPORT_DIR) -> Path | None:
    """Return the first file of the newest export set in `directory`, if any."""
    paths = find_export_set(directory)
    return paths[0] if paths[0].exists() else None


def load_pubtracker_submissions(path: Path | list[Path] | None = None) -> pd.DataFrame:
    """Load and normalize PubTracker submission export(s) for title-based cross-referencing.

    `path` may be one export or several (their rows are combined).
    Returns an empty frame (safe no-op for callers) if no export file is found.
    """
    path = path or find_export_set()
    columns = ["_norm_title", "PubTracker Reported Portfolio", "PubTracker VA Funded"]
    if path is None:
        return pd.DataFrame(columns=columns)

    paths = path if isinstance(path, (list, tuple)) else [path]
    if not all(Path(p).exists() for p in paths):
        return pd.DataFrame(columns=columns)
    raw = pd.concat([read_export(p) for p in paths], ignore_index=True)
    raw = raw[raw["Submittion Type"].astype(str).str.strip().str.lower() == "publication"].copy()
    raw["_norm_title"] = raw["Title"].map(_normalize_title)
    raw = raw[raw["_norm_title"] != ""]
    raw["PubTracker Reported Portfolio"] = raw["POC Primary Service"].fillna("").astype(str).str.strip()
    raw["PubTracker VA Funded"] = raw["VA Funded?"].astype(str).str.strip().str.lower().eq("yes")

    # One PubTracker row per normalized title is enough for a corroboration check.
    return raw[columns].drop_duplicates("_norm_title")


def crossref_ord_funding(publications: pd.DataFrame, pubtracker: pd.DataFrame) -> pd.DataFrame:
    """Return `publications` with PubTracker corroboration columns appended.

    Does not modify any existing column, including the Dimensions-based ORD tags.
    """
    result = publications.copy()
    result["_norm_title"] = result["Title"].map(_normalize_title)
    merged = result.merge(pubtracker, on="_norm_title", how="left")
    merged["PubTracker Match Found"] = merged["PubTracker Reported Portfolio"].notna()
    merged["PubTracker Reported Portfolio"] = merged["PubTracker Reported Portfolio"].fillna("")
    merged["PubTracker VA Funded"] = merged["PubTracker VA Funded"].fillna(False)
    return merged.drop(columns=["_norm_title"])
