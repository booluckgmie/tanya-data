# Extracted data (pilot)

Machine-readable tables extracted from official publications. This is a separate store from `registry/`, which stays metadata-only.

Rules:
- Only sources whose reuse terms allow it. DOSM publications on open.dosm.gov.my state CC BY 4.0; credit "Department of Statistics Malaysia".
- Prefer the agency's own Excel file (exact cell read). PDF extraction is a later step and needs page-level provenance and checks.
- Each extraction has a `manifest.json`: source URL, edition, file hash, method, and per-table checks. Every row in `values.csv` carries its sheet and source row.
- Failed checks are reported, not hidden. `sum_failures` lists tables where parts do not add to the total; Table B1/B2 (ethnic groups) are hierarchical, so their parts include sub-groups and the flat-sum check does not apply.
- MOHE statistics are restricted to individual and registered educational use. Their extractor may be run locally; the tables are not republished here.

Pilot: `dosm/salaries_wages/2025` from `salaries_wages_2025.xlsx` (extractor `extract/dosm_xlsx.py`, needs openpyxl).

## Derived files (computed by this project, not official statistics)

- `dosm/salaries_wages/2025/derived_gender_gap.csv`: `gap_pct = (male - female) / male * 100` on DOSM's monthly median and mean, by age, strata, state, occupation, industry, sector, skill and ethnic group, 2010 to 2025. Unadjusted: no control for occupation, hours or experience. Each row names the source rows. Built by `extract/derive_gender_gap.py`.
- `dosm/salaries_wages/2025/illustrative_trend.csv`: log-linear trend of median pay to 2030 with an approximate 80% band, from `extract/project_trend.py`. An extrapolation of 2010 to 2025, not a forecast. The band covers trend uncertainty only, not the spread of individual salaries.

Scope notes:
- The 2025 workbook already holds 2010 to 2025 in every table, so older editions are not needed for the series. They would add restatements only.
- DOSM publishes no data-scientist salary. Its occupation tables stop at the nine MASCO major groups, and its industry tables at MSIC sections. The nearest rows are Professionals and Information and communication.
- The quarterly formal-sector wage workbook uses a different layout (month columns, two-line headers). It is not parsed yet.
