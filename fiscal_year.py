"""Single source for the fiscal year the tool reports on.

Defaults to the current federal fiscal year (Oct 1 - Sep 30). Override with the VARR_FY environment
variable (e.g. VARR_FY=26 or 2026) to rebuild a past year.
"""
from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"


def current_fiscal_year(today: date | None = None) -> int:
    today = today or date.today()
    return today.year + 1 if today.month >= 10 else today.year


def _resolve() -> int:
    raw = os.environ.get("VARR_FY", "").strip()
    if not raw:
        return current_fiscal_year()
    year = int(raw)
    return year + 2000 if year < 100 else year


FISCAL_YEAR = _resolve()
FY_SHORT = FISCAL_YEAR % 100
FY_START = f"{FISCAL_YEAR - 1}-10-01"
FY_END = f"{FISCAL_YEAR}-09-30"
BASELINE_CSV = DATA_DIR / f"varr_baseline_FY{FY_SHORT}.csv"
DOCS_DIR = Path(__file__).resolve().parent / "docs"
OUTPUT_DIR = DOCS_DIR / "data" / f"FY{FY_SHORT}"


def write_fiscal_years_index() -> None:
    """List every docs/data/FY* folder for the page's fiscal-year selector (docs/fiscal_years.js)."""
    entries = []
    for meta_path in sorted((DOCS_DIR / "data").glob("FY*/meta.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        entries.append({"fy": int(meta_path.parent.name[2:]), "updated": meta.get("generatedOn", "")})
    entries.sort(key=lambda e: -e["fy"])
    (DOCS_DIR / "fiscal_years.js").write_text(f"window.VARR_FYS = {json.dumps(entries)};\n", encoding="utf-8")
