"""Export the VA Research Radar (vadaily) publication database as a Dimensions-schema CSV.

PubTracker Compliance-VARR uses this CSV as its baseline in place of the VA Dimensions export, so the
downstream processors (facility matching, ORD tagging, compliance) run unchanged.

    python export_varr_baseline.py --db "<path>\\vadaily.db"
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from pathlib import Path

DEFAULT_OUT = Path(__file__).parent / "data" / "varr_baseline_FY26.csv"
FY_START, FY_END = "2025-10-01", "2026-09-30"

COLUMNS = [
    "Publication ID", "DOI", "PMID", "PMCID", "Title", "Abstract", "Acknowledgements", "Funding",
    "Source title", "Publisher", "ISSN", "Publication date", "PubYear", "Open Access",
    "Publication Type", "Document Type", "Authors", "Authors (Raw Affiliation)",
    "Research Organizations - standardized", "Funder", "Grant IDs of Supporting Grants",
    "Supporting Grants", "Times cited", "RCR", "FCR", "Source Linkout",
    "Dimensions for Veterans Affairs URL", "Fields of Research (ANZSRC 2020)", "VARR Sources",
]

# vadaily pub_type -> Dimensions "Publication Type"; None drops records that are not publications.
PUBLICATION_TYPE = {
    "Article": "article", "Review": "article", "Editorial": "article", "Letter": "article",
    "Erratum": "article", "Preprint": "preprint", "Book-Chapter": "chapter",
    "Conference-Abstract": "proceeding", "Conference-Paper": "proceeding", "Book": "book",
    "Dataset": None, "Software": None, "Study-Registration": None, "Peer-Review": None,
    "Paratext": None, "Data-Paper": None,
}
VA_SEGMENT = re.compile(r"veterans|\bVA\b|\bVAMC\b|\bVHA\b", re.I)


def document_type(pub_type: str) -> str:
    if pub_type == "Conference-Abstract":
        return "Conference Abstract"
    if pub_type == "Erratum":
        return "Correction Erratum"
    return "Article"


def organizations(record: dict) -> str:
    """Standardized orgs, or the VA-looking raw affiliation segments when a record has none."""
    orgs = (record.get("research_orgs") or "").strip()
    if orgs:
        return orgs
    segments = [s.strip() for s in (record.get("affiliations") or "").split(";")]
    return "; ".join(s for s in segments if s and VA_SEGMENT.search(s))


def rows(db: Path):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        for (raw,) in con.execute("SELECT record FROM publications"):
            r = json.loads(raw)
            pub_type = r.get("pub_type") or ""
            mapped = PUBLICATION_TYPE.get(pub_type, "article")
            date = r.get("pub_date") or ""
            if mapped is None or not FY_START <= date <= FY_END:
                continue
            if not ({"pubmed", "openalex", "crossref"} & set(r.get("sources") or [])):
                continue
            yield {
                "Publication ID": r.get("dimensions_id") or r.get("key"),
                "DOI": r.get("doi"), "PMID": r.get("pmid"), "PMCID": r.get("pmcid"),
                "Title": r.get("title"), "Abstract": r.get("abstract"),
                "Acknowledgements": r.get("acknowledgements"), "Funding": r.get("funding_text"),
                "Source title": r.get("journal"), "Publisher": r.get("publisher"), "ISSN": r.get("issn"),
                "Publication date": date, "PubYear": date[:4], "Open Access": r.get("open_access"),
                "Publication Type": mapped, "Document Type": document_type(pub_type),
                "Authors": r.get("authors"), "Authors (Raw Affiliation)": r.get("affiliations"),
                "Research Organizations - standardized": organizations(r),
                "Funder": r.get("funder"), "Grant IDs of Supporting Grants": r.get("grant_ids"),
                "Supporting Grants": r.get("grant_ids"), "Times cited": r.get("times_cited"),
                "RCR": r.get("rcr"), "FCR": r.get("fcr"), "Source Linkout": r.get("source_linkout"),
                "Dimensions for Veterans Affairs URL": r.get("dimensions_url"),
                "Fields of Research (ANZSRC 2020)": r.get("fields_of_research"),
                "VARR Sources": ", ".join(r.get("sources") or []),
            }
    finally:
        con.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path, help="Path to vadaily.db")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    seen, written = set(), 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows(args.db):
            if row["Publication ID"] in seen:
                continue
            seen.add(row["Publication ID"])
            writer.writerow(row)
            written += 1
    print(f"Wrote {written} publications ({FY_START} to {FY_END}) to {args.out}")


if __name__ == "__main__":
    main()
