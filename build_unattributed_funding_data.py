"""Write docs/data/unattributed_va_funding.json for docs/unattributed.html.

Standalone: nothing here is imported by the existing dashboard builds.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

from build_static_dashboard_data import (
    OUTPUT_DIR,
    PUBTRACKER_GAP_PATHS,
    SOURCE_CSV,
    _text,
)
from processors.dashboard_data import load_dashboard_dataset
from processors.pubtracker_compliance import (
    UNATTRIBUTED,
    build_station_lookup,
    facility_map,
    filter_fiscal_year,
    load_pubtracker_files,
    match_to_pubtracker,
    quarter_options,
    record_links,
)
from processors.va_funder_evidence import CATEGORIES, classify_va_funding_frame


def main() -> None:
    dataset = load_dashboard_dataset(str(SOURCE_CSV))
    scoped, _ = filter_fiscal_year(dataset.publications)
    pub_facilities = facility_map(dataset.facility_matches)
    unattributed = scoped[~scoped["Publication ID"].isin(pub_facilities)].copy()
    unattributed = unattributed.join(classify_va_funding_frame(unattributed))

    found: dict = {}
    if all(path.exists() for path in PUBTRACKER_GAP_PATHS):
        pubtracker = load_pubtracker_files(PUBTRACKER_GAP_PATHS, build_station_lookup())
        results = match_to_pubtracker(unattributed, pub_facilities, pubtracker, 90.0)
        found = dict(zip(results["Publication ID"], results["Match Type"].ne("Missing")))

    records = []
    for row in unattributed.sort_values("Canonical Date", ascending=False).to_dict("records"):
        links = record_links(row)
        records.append([
            row["Publication ID"],
            row["Canonical Date"].strftime("%Y-%m-%d"),
            _text(row.get("Title")),
            _text(row.get("Source title")),
            _text(row.get("DOI Link")).removeprefix("https://doi.org/"),
            _text(row.get("PubMed Link")).removeprefix("https://pubmed.ncbi.nlm.nih.gov/").strip("/"),
            CATEGORIES.index(row["VA Funding Category"]),
            row["VA Funding Parts"],
            _text(row.get("Funder")),
            _text(row.get("Supporting Grants")),
            int(bool(found.get(row["Publication ID"]))),
            row["VA Award Codes"],
            links["PMC Link"].removeprefix("https://pmc.ncbi.nlm.nih.gov/articles/").strip("/"),
            links["Source Link"],
        ])
    payload = {
        "unattributedLabel": UNATTRIBUTED,
        "categories": CATEGORIES,
        "periods": {
            label: {"start": start.strftime("%Y-%m-%d"), "end": end.strftime("%Y-%m-%d")}
            for label, (start, end) in quarter_options(scoped).items()
        },
        # [id, date, title, journal, doi, pmid, categoryIdx, vaParts, funders, grants, inPubTracker, vaAwardCodes, pmcid, sourceLink]
        "records": records,
    }
    out = OUTPUT_DIR / "unattributed_va_funding.json"
    out.write_text(json.dumps(payload, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    counts = unattributed["VA Funding Category"].value_counts()
    print(f"Wrote {out} ({out.stat().st_size / 1_048_576:.2f} MB), {len(records):,} unattributed records")
    print(counts.to_string())


if __name__ == "__main__":
    main()
