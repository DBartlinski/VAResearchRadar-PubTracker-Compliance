# PubTracker Compliance-VARR

A copy of the [PubTracker compliance tool](https://github.com/DBartlinski/PubTracker) that takes its baseline from **VA Research Radar (VARR)**, the daily PubMed/OpenAlex/Crossref pipeline, instead of the VA Dimensions export. The original PubTracker repo and its published site are unchanged and serve as the control.

## How the baseline is produced

1. In the VA Research Radar project, make sure its database covers papers that went online from about Jan 1, 2025 (nine months before FY26) through Sep 30, 2026. The earlier months are needed because many papers go online months before their print issue.
2. Export the database as a Dimensions-schema CSV:

   ```
   python export_varr_baseline.py --db "<path>\vadaily.db"
   ```

   This writes `data/varr_baseline_FY26.csv`. Only journal-type records whose fiscal date falls between Oct 1, 2025 and Sep 30, 2026 are exported; datasets, software, registrations and peer reviews are dropped. Print dates are looked up from Crossref by DOI and cached in `data/crossref_print_dates.json`, so later runs only fetch new DOIs. Use `--no-print-dates` to skip the lookup.
3. Build the static data and publish `docs/`:

   ```
   python build_static_dashboard_data.py
   ```

## Differences from the Dimensions baseline

- Publication IDs are VARR keys (`doi:...`) unless the record carries a Dimensions ID. Dimensions links appear only for `pub.*` IDs.
- Fiscal dating follows Dimensions: Crossref print/issue date first, then VARR's own date (the earliest, usually online). Records without a DOI or Crossref print date use VARR's date. A month-only print date counts as the 1st of that month.
- Facility matching uses the standardized organizations from OpenAlex. When a record has none, the VA-looking segments of the raw affiliation text are used. OpenAlex spellings that differ from the Dimensions names in `vamc_reference.csv` (for example "VA Salt Lake City Healthcare System" or "South Texas Veterans Health Care System") are mapped by `ORG_ALIASES` in `export_varr_baseline.py`, so the shared reference file stays identical to the control.
- Facility tagging uses only the first two distinct VA facilities listed in a paper's author affiliations (in listed order); any further VA facilities are ignored. Different spellings of one facility count once, and VA Central Office / umbrella names (for example "Veterans Health Administration") do not use up a slot. Applied in `limit_va_facilities` in `export_varr_baseline.py`.
- Each record gets a `VA Evidence` level: **strong** (a standardized VA organization or VA funding), **medium** (VA named in the raw affiliations, excluding bare "VA" that can mean Virginia) or **weak** (neither). Weak records are left out of the dashboard data and listed in `data/varr_baseline_FY26_below_evidence.csv` for audit. Use `--min-evidence weak` to keep everything.
- Internal field names keep the Dimensions column names so the processors stay unchanged.

The remaining documentation (`docs/documentation.html`, `PubTracker compliance report SOP.*`) still describes the original Dimensions workflow.
