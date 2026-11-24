"""Export the VA Research Radar (vadaily) publication database as a Dimensions-schema CSV.

PubTracker Compliance-VARR uses this CSV as its baseline in place of the VA Dimensions export, so the
downstream processors (facility matching, ORD tagging, compliance) run unchanged.

    python export_varr_baseline.py --db "<path>\\vadaily.db"

Publications are placed in the fiscal year by print/issue date first, then online date, matching
Dimensions. vadaily stores the earliest (online) date, so print dates are looked up from Crossref by DOI
and cached in data/crossref_print_dates.json; PubMed issue dates (data/pubmed_issue_dates.json) fill in
where Crossref has none. The vadaily database must therefore cover papers that went
online up to about nine months before the fiscal year starts.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import time
from functools import lru_cache
from pathlib import Path

from fiscal_year import BASELINE_CSV, FY_END, FY_START

DATA = Path(__file__).parent / "data"
DEFAULT_OUT = BASELINE_CSV
PRINT_CACHE = DATA / "crossref_print_dates.json"
ISSUE_CACHE = DATA / "pubmed_issue_dates.json"
EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
CROSSREF = "https://api.crossref.org/works"
CONTACT = "david.bartlinski@va.gov"
DOIS_PER_REQUEST = 20

COLUMNS = [
    "Publication ID", "DOI", "PMID", "PMCID", "Title", "Abstract", "Acknowledgements", "Funding",
    "Source title", "Publisher", "ISSN", "Publication date", "PubYear", "Open Access",
    "Publication Type", "Document Type", "Authors", "Authors (Raw Affiliation)", "Authors Affiliations",
    "Research Organizations - standardized", "MeSH terms", "Funder", "Grant IDs of Supporting Grants",
    "Supporting Grants", "Times cited", "RCR", "FCR", "Source Linkout",
    "Dimensions for Veterans Affairs URL", "Fields of Research (ANZSRC 2020)", "Broad Research Areas",
    "Health Research Areas", "RCDC Categories", "VARR Sources", "VA Evidence",
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

# OpenAlex/ROR spellings of VA facilities -> the Dimensions name used in vamc_reference.csv search terms.
# The canonical name is appended (the original is kept) so facility matching finds the station.
ORG_ALIASES = [
    (re.compile(r"salt lake city healthcare system", re.I), "VA Salt Lake City Health care System"),
    (re.compile(r"south texas veterans health ?care system", re.I), "VA South Texas Health Care System"),
    (re.compile(r"northeast ohio health ?care system", re.I), "Louis Stokes Cleveland VA Medical Center"),
    (re.compile(r"\bdallas va medical center", re.I), "VA North Texas Health Care System"),
    (re.compile(r"(?<!salt )\blake city va medical center", re.I), "North Florida/South Georgia Veterans Health System"),
    (re.compile(r"crescenz (va|veterans affairs) medical center", re.I), "Philadelphia VA Medical Center"),
    (re.compile(r"doris miller (department of veterans affairs|va) medical center", re.I), "Doris Miller VA Medical Center"),
    (re.compile(r"\bva center for clinical management research", re.I), "VA Ann Arbor Healthcare System"),
    (re.compile(r"\bva indianapolis\b", re.I), "Richard L. Roudebush VA Medical Center"),
]


# Raw-affiliation phrases that name the VA itself; a bare "VA" is excluded because it also matches Virginia.
VA_AFFILIATION = re.compile(
    r"veterans?[ ’']*(affairs|health|administration|hospital|medical|healthcare|integrated)"
    r"|\bVAMC\b|\bVHA\b|national center for ptsd"
    r"|\bVA\s+(medical|health|healthcare|hospital|[A-Z][\w.-]*\s+(healthcare|health care|medical|health system))",
    re.I)
EVIDENCE_RANK = {"weak": 0, "medium": 1, "strong": 2}


def va_evidence(record: dict) -> str:
    """strong: standardized VA organization or VA funding; medium: VA named in raw affiliations; else weak."""
    if VA_SEGMENT.search(record.get("research_orgs") or "") or record.get("va_funded") or record.get("ord_funded"):
        return "strong"
    if VA_AFFILIATION.search(record.get("affiliations") or ""):
        return "medium"
    return "weak"


ABSTRACT_DOI = re.compile(
    r"^10\.1093/geroni/igaf\d+\.\d+$"          # Innovation in Aging meeting abstracts
    r"|^10\.1681/asn\.\d{4}[0-9a-z]{8}$"       # JASN meeting abstracts
    r"|^10\.1002/alz\d{5}_\d+$"                # Alzheimer's & Dementia meeting abstracts
    r"|^10\.1093/ajrccm/aamag\d+\.\d+$|meetingabstracts"
    r"|_suppl\.|^10\.1152/physiol\.\d{4}\.\d+\.s\d\.\d+$", re.I)
ERRATUM_TITLE = re.compile(
    r"^\s*(author |publisher |editorial |addendum and )?(correction|corrigendum|erratum|errata)\b", re.I)


def document_type(pub_type: str, doi: str = "", title: str = "") -> str:
    if pub_type == "Conference-Abstract" or ABSTRACT_DOI.search(doi or ""):
        return "Conference Abstract"
    if pub_type == "Erratum" or ERRATUM_TITLE.search(title or "") or (title or "").lower().startswith("corrigendum to"):
        return "Correction Erratum"
    return "Article"


MAX_VA_FACILITIES = 2
VA_CENTRAL_OFFICE_STATION = "101"


@lru_cache(maxsize=1)
def _facility_terms() -> list[tuple[str, list[str]]]:
    from processors.compliance_calculator import get_search_terms, load_vamc_reference
    ref = load_vamc_reference()
    return [(str(station).strip(), [t.lower() for t in get_search_terms(display)])
            for display, station in zip(ref["vamc_display"], ref["station_no"])]


def facility_station(org: str) -> str | None:
    """Station number of the first reference facility whose search term appears in `org`."""
    low = org.lower()
    for station, terms in _facility_terms():
        if any(t in low for t in terms):
            return station
    return None


def canonical_org(org: str) -> str:
    for pattern, canonical in ORG_ALIASES:
        if pattern.search(org):
            return canonical
    return org


def limit_va_facilities(orgs: list[str]) -> list[str]:
    """Keep non-VA organizations plus only the first two distinct VA facilities in listed order.

    VA Central Office / umbrella names are not facilities, so they do not use up a slot.
    """
    kept, facilities = [], []
    for org in orgs:
        station = facility_station(canonical_org(org))
        if station == VA_CENTRAL_OFFICE_STATION or not (station or VA_SEGMENT.search(org)):
            kept.append(org)
            continue
        key = station or org.lower()
        if key not in facilities and len(facilities) < MAX_VA_FACILITIES:
            facilities.append(key)
        if key in facilities:
            kept.append(org)
    return kept


def organizations(record: dict) -> str:
    """Standardized orgs (or VA-looking raw affiliation segments when none), capped at the first two VA
    facilities, plus Dimensions-name aliases."""
    orgs = [s.strip() for s in (record.get("research_orgs") or "").split(";") if s.strip()]
    if not orgs:
        segments = [s.strip() for s in (record.get("affiliations") or "").split(";")]
        orgs = [s for s in segments if s and VA_SEGMENT.search(s)]
    orgs = limit_va_facilities(orgs)
    for pattern, canonical in ORG_ALIASES:
        if canonical not in orgs and any(pattern.search(o) for o in orgs):
            orgs.append(canonical)
    return "; ".join(orgs)


def funding(record: dict) -> str:
    """Funding statement, or funder names plus award numbers so ORD prefix/service detection still works."""
    if (record.get("funding_text") or "").strip():
        return record["funding_text"]
    return "; ".join(p for p in (record.get("funder"), record.get("grant_ids")) if p)


def load_records(db: Path) -> list[dict]:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return [json.loads(raw) for (raw,) in con.execute("SELECT record FROM publications")]
    finally:
        con.close()


def _date_parts(value: dict | None) -> str:
    parts = ((value or {}).get("date-parts") or [[None]])[0]
    if not parts or not parts[0]:
        return ""
    y, m, d = (list(parts) + [1, 1])[:3]
    return f"{int(y):04d}-{int(m or 1):02d}-{int(d or 1):02d}"


def lookup_print_dates(dois: set[str], cache_path: Path = PRINT_CACHE) -> dict[str, str]:
    """DOI -> Crossref print date (YYYY-MM-DD, "" when Crossref has none). Cached; only new DOIs are fetched."""
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    todo = sorted(d for d in dois if d not in cache)
    if todo:
        import requests
        try:
            import truststore  # VA network inspects TLS; trust the OS certificate store.
            truststore.inject_into_ssl()
        except ImportError:
            pass
        session = requests.Session()
        session.headers["User-Agent"] = f"PubTrackerCompliance-VARR/1.0 (mailto:{CONTACT})"
        print(f"Looking up Crossref print dates for {len(todo)} DOIs...")
        for i in range(0, len(todo), DOIS_PER_REQUEST):
            batch = todo[i:i + DOIS_PER_REQUEST]
            params = {"filter": ",".join(f"doi:{d}" for d in batch), "rows": DOIS_PER_REQUEST * 2,
                      "select": "DOI,published-print"}
            for attempt in range(6):
                try:
                    resp = session.get(CROSSREF, params=params, timeout=60)
                except requests.RequestException:
                    resp = None
                if resp is not None and resp.status_code == 200:
                    break
                time.sleep(2 ** attempt)
            else:
                print(f"  giving up on batch at {i} (left uncached; re-run to retry)")
                continue
            found = {it["DOI"].lower(): _date_parts(it.get("published-print"))
                     for it in resp.json()["message"]["items"]}
            for d in batch:
                cache[d] = found.get(d, "")
            if (i // DOIS_PER_REQUEST) % 50 == 0:
                print(f"  {i + len(batch)}/{len(todo)}")
                cache_path.write_text(json.dumps(cache, sort_keys=True), encoding="utf-8")
            time.sleep(0.3)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache, sort_keys=True), encoding="utf-8")
    return cache


def fiscal_date(record: dict, print_dates: dict[str, str]) -> str:
    """Print/issue date first, then the record's own (earliest/online) date, as Dimensions does.

    Print dates after the fiscal year end are ignored: Dimensions had not yet assigned those issues, so
    it dated the paper by its online date.
    """
    printed = (print_dates.get((record.get("doi") or "").lower())
               or print_dates.get(f"pmid:{record.get('pmid')}") or "")
    if printed and printed <= FY_END:
        return printed
    return record.get("pub_date") or ""


MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
SEASONS = {"winter": 1, "spring": 4, "summer": 7, "fall": 10, "autumn": 10}


def _issue_date(pub_date) -> str:
    """PubMed journal-issue PubDate element -> YYYY-MM-DD (month or season starts, day defaults to 1).

    Year-only dates (continuous-publication journals) are not issue dates, so they return "".
    """
    year = pub_date.findtext("Year")
    month = (pub_date.findtext("Month") or "").strip().lower()
    if not year:
        match = re.match(r"(\d{4})\s*([A-Za-z]{3,6})?", pub_date.findtext("MedlineDate") or "")
        if not match:
            return ""
        year, month = match.group(1), (match.group(2) or "").lower()
    number = int(month) if month.isdigit() else MONTHS.get(month[:3]) or SEASONS.get(month)
    if not number:
        return ""
    day = pub_date.findtext("Day")
    return f"{int(year):04d}-{number:02d}-{int(day) if day and day.isdigit() else 1:02d}"


def lookup_pubmed_issue_dates(pmids: set[str], cache_path: Path = ISSUE_CACHE) -> dict[str, str]:
    """PMID -> PubMed journal issue date (the fallback when Crossref has no print date). Cached."""
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    todo = sorted(p for p in pmids if p not in cache)
    if todo:
        import xml.etree.ElementTree as ET

        import requests
        try:
            import truststore
            truststore.inject_into_ssl()
        except ImportError:
            pass
        session = requests.Session()
        print(f"Looking up PubMed issue dates for {len(todo)} PMIDs...")
        for i in range(0, len(todo), 200):
            batch = todo[i:i + 200]
            for attempt in range(6):
                try:
                    resp = session.post(EFETCH, data={"db": "pubmed", "id": ",".join(batch), "retmode": "xml",
                                                      "tool": "varr-compliance", "email": CONTACT}, timeout=120)
                except requests.RequestException:
                    resp = None
                if resp is not None and resp.status_code == 200:
                    break
                time.sleep(2 ** attempt)
            else:
                print(f"  giving up on batch at {i} (left uncached; re-run to retry)")
                continue
            found = {}
            for article in ET.fromstring(resp.content).iter("PubmedArticle"):
                pmid = article.findtext("MedlineCitation/PMID")
                issue = article.find("MedlineCitation/Article/Journal/JournalIssue/PubDate")
                found[pmid] = _issue_date(issue) if issue is not None else ""
            for p in batch:
                cache[p] = found.get(p, "")
            time.sleep(0.4)
        cache_path.write_text(json.dumps(cache, sort_keys=True), encoding="utf-8")
    return cache


def rows(records: list[dict], print_dates: dict[str, str]):
    for r in records:
        pub_type = r.get("pub_type") or ""
        mapped = PUBLICATION_TYPE.get(pub_type, "article")
        date = fiscal_date(r, print_dates)
        if mapped is None or not FY_START <= date <= FY_END:
            continue
        if not ({"pubmed", "openalex", "crossref"} & set(r.get("sources") or [])):
            continue
        yield {
            "Publication ID": r.get("dimensions_id") or r.get("key"),
            "DOI": r.get("doi"), "PMID": r.get("pmid"), "PMCID": r.get("pmcid"),
            "Title": r.get("title"), "Abstract": r.get("abstract"),
            "Acknowledgements": r.get("acknowledgements"), "Funding": funding(r),
            "Source title": r.get("journal"), "Publisher": r.get("publisher"), "ISSN": r.get("issn"),
            "Publication date": date, "PubYear": date[:4], "Open Access": r.get("open_access"),
            "Publication Type": mapped, "Document Type": document_type(pub_type, r.get("doi") or "", r.get("title") or ""),
            "Authors": r.get("authors"), "Authors (Raw Affiliation)": r.get("affiliations"),
            "Authors Affiliations": r.get("affiliations"),
            "Research Organizations - standardized": organizations(r), "MeSH terms": r.get("mesh_terms"),
            "Funder": r.get("funder"), "Grant IDs of Supporting Grants": r.get("grant_ids"),
            "Supporting Grants": r.get("grant_ids"), "Times cited": r.get("times_cited"),
            "RCR": r.get("rcr"), "FCR": r.get("fcr"), "Source Linkout": r.get("source_linkout"),
            "Dimensions for Veterans Affairs URL": r.get("dimensions_url"),
            "Fields of Research (ANZSRC 2020)": r.get("fields_of_research"),
            "Broad Research Areas": r.get("fields_of_research"),
            "Health Research Areas": r.get("health_areas"), "RCDC Categories": r.get("rcdc"),
            "VARR Sources": ", ".join(r.get("sources") or []),
            "VA Evidence": va_evidence(r),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path, help="Path to vadaily.db")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--no-print-dates", action="store_true",
                        help="Use vadaily's earliest (online) date only; skip the Crossref print-date lookup")
    parser.add_argument("--min-evidence", choices=list(EVIDENCE_RANK), default="medium",
                        help="Lowest VA-evidence level kept (default medium); dropped rows go to the audit CSV")
    args = parser.parse_args()

    records = load_records(args.db)
    print_dates = {}
    if not args.no_print_dates:
        # Print dates trail online dates, so only papers online by FY end can be printed within the FY.
        print_dates = lookup_print_dates({r["doi"].lower() for r in records
                                          if r.get("doi") and (r.get("pub_date") or "") <= FY_END})
        # PubMed issue dates cover papers Crossref has no print date for.
        no_print = {r["pmid"] for r in records if r.get("pmid") and (r.get("pub_date") or "") <= FY_END
                    and not print_dates.get((r.get("doi") or "").lower())}
        issue_dates = lookup_pubmed_issue_dates(no_print)
        print_dates.update({f"pmid:{p}": d for p, d in issue_dates.items() if d})

    seen, written, dropped = set(), 0, 0
    floor = EVIDENCE_RANK[args.min_evidence]
    audit_path = args.out.with_name(f"{args.out.stem}_below_evidence.csv")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="") as f, \
            open(audit_path, "w", encoding="utf-8", newline="") as audit:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        audit_writer = csv.DictWriter(audit, fieldnames=["DOI", "Title", "Source title", "Publication date",
                                                         "Authors (Raw Affiliation)", "VARR Sources", "VA Evidence"],
                                      extrasaction="ignore")
        writer.writeheader()
        audit_writer.writeheader()
        for row in rows(records, print_dates):
            if row["Publication ID"] in seen:
                continue
            seen.add(row["Publication ID"])
            if EVIDENCE_RANK[row["VA Evidence"]] < floor:
                audit_writer.writerow(row)
                dropped += 1
                continue
            writer.writerow(row)
            written += 1
    print(f"Wrote {written} publications ({FY_START} to {FY_END}) to {args.out}; "
          f"{dropped} below '{args.min_evidence}' evidence listed in {audit_path.name}")


if __name__ == "__main__":
    main()
