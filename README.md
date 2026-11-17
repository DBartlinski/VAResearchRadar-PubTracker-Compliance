# PubTracker Compliance-VARR

A copy of the [PubTracker compliance tool](https://github.com/DBartlinski/PubTracker) that takes its baseline from **VA Research Radar (VARR)**, the daily PubMed/OpenAlex/Crossref pipeline, instead of the VA Dimensions export. The original PubTracker repo and its published site are unchanged and serve as the control.

## How the baseline is produced

1. In the VA Research Radar project, make sure its database covers fiscal year 2026 (`start_date: 2025-10-01` with a lookback long enough to backfill).
2. Export the database as a Dimensions-schema CSV:

   ```
   python export_varr_baseline.py --db "<path>\vadaily.db"
   ```

   This writes `data/varr_baseline_FY26.csv`. Only journal-type records dated Oct 1, 2025 to Sep 30, 2026 are exported; datasets, software, registrations and peer reviews are dropped.
3. Build the static data and publish `docs/`:

   ```
   python build_static_dashboard_data.py
   ```

## Differences from the Dimensions baseline

- Publication IDs are VARR keys (`doi:...`) unless the record carries a Dimensions ID. Dimensions links appear only for `pub.*` IDs.
- There is a single publication date per record instead of Dimensions' print/online/general dates.
- Facility matching uses the standardized organizations from OpenAlex. When a record has none, the VA-looking segments of the raw affiliation text are used.
- Internal field names keep the Dimensions column names so the processors stay unchanged.

The remaining documentation (`docs/documentation.html`, `PubTracker compliance report SOP.*`) still describes the original Dimensions workflow.
