"""Classify Dimensions records by VA funding evidence (separate from the dashboard's ORD tagging)."""
import re

import pandas as pd

from processors.ord_portfolio import BROAD_PORTFOLIO_NAMES, extract_broad_portfolios

ORD_PORTFOLIO = "VA-funded: ORD, portfolio identified"
ORD_GENERAL = "VA-funded: ORD, portfolio not identified"
VA_OTHER = "VA-funded: other VA / unspecified"
AFFILIATED_ONLY = "VA-affiliated only (no VA funding evidence)"
CATEGORIES = [ORD_PORTFOLIO, ORD_GENERAL, VA_OTHER, AFFILIATED_ONLY]

_ORD = re.compile(r"office of research (?:and|&) development|\bVA ORD\b", re.IGNORECASE)
_MIRECC = re.compile(r"mental illness research,? education", re.IGNORECASE)
_VA_GENERAL = re.compile(
    r"(?:united states )?department of veterans affairs|veterans['\u2019]? (?:hospital|affairs)|"
    r"veterans health administration|\bVHA\b",
    re.IGNORECASE,
)
_VA_ABBR = re.compile(r"\bVA\b(?! Tech)")
# Veterans charities / non-VA bodies that would otherwise look like VA funding.
_NOT_VA = re.compile(r"paralyzed veterans|disability, independent living|veterans (?:of|foundation)", re.IGNORECASE)

SOURCE_COLUMNS = ("Funder", "Funding")

# ORD award numbers, e.g. I01CX002193, 1IK6BX006184, CX002193.
_AWARD_CODE = re.compile(r"\b(?:\d?[A-Z]{1,3}\d?[\s-]?)?(?:CX|BX|RX|HX)[\s-]?(\d{5,7})(?:-\d{2}(?:[A-Z]\d)?)?\b")
AWARD_COLUMNS = ("Supporting Grants", "Funding", "Acknowledgements")


def extract_va_award_codes(row: pd.Series) -> str:
    """VA/ORD award numbers found in grant, funding and acknowledgement text; one entry per award, longest form kept."""
    best: dict[str, str] = {}
    for column in AWARD_COLUMNS:
        value = row.get(column)
        if not isinstance(value, str):
            continue
        for match in _AWARD_CODE.finditer(value):
            code = re.sub(r"[\s-]", "", match.group(0)).upper()
            key = code[code.find(match.group(1)) - 2:]
            if len(code) > len(best.get(key, "")):
                best[key] = code
    return "; ".join(sorted(best.values()))


def _funder_text(row: pd.Series) -> str:
    parts = []
    for column in SOURCE_COLUMNS:
        value = row.get(column)
        if isinstance(value, str) and value.strip():
            parts.append(value)
    return " ; ".join(parts)


def _va_funder_names(funder_text: str) -> str:
    """Funder entries only, with non-VA look-alikes removed."""
    return "; ".join(part for part in funder_text.split(";") if not _NOT_VA.search(part))


def classify_va_funding(row: pd.Series) -> dict:
    """Return the VA funding category and the VA parts (ORD portfolios, MIRECC, ...) evidenced for a record."""
    text = _va_funder_names(_funder_text(row))
    codes = set(str(row.get("ORD Broad Portfolio Codes") or "").split("; ")) - {""}
    codes |= extract_broad_portfolios(text)
    parts = {BROAD_PORTFOLIO_NAMES[code] for code in codes}

    ord_named = bool(_ORD.search(text))
    if ord_named:
        parts.add("Office of Research and Development")
    if _MIRECC.search(text):
        parts.add("MIRECC")
    va_general = bool(_VA_GENERAL.search(text) or _VA_ABBR.search(text))
    if va_general and not parts:
        parts.add("VA (unspecified)")

    if codes:
        category = ORD_PORTFOLIO
    elif ord_named:
        category = ORD_GENERAL
    elif parts or va_general:
        category = VA_OTHER
    else:
        category = AFFILIATED_ONLY
    return {
        "VA Funding Category": category,
        "VA Funding Parts": "; ".join(sorted(parts)),
        "VA Award Codes": extract_va_award_codes(row),
    }


def classify_va_funding_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Return the two classification columns indexed like `frame`."""
    return frame.apply(classify_va_funding, axis=1, result_type="expand")
