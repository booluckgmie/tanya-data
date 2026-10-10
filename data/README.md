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

## Formal-sector wages (`dosm/formal_wages/2026-Q1`)

Parsed by `extract/dosm_formal_wages.py` from DOSM's quarterly Employee Wages Statistics (Formal Sector) workbook: 6,432 rows from 28 tables, monthly, October 2024 to March 2026.
- Scope: Malaysian citizens in formal-sector employment only, so it excludes non-citizens and informal work. Do not mix it with the all-employee Salaries & Wages survey figures.
- Tables: headcount, share, month-on-month and year-on-year change, and median wage, by sex, ethnic group, age, economic activity and state; wage-scale distribution; wage percentiles (10th to 90th); age by broad sector (headcount, share and median wage).
- Window: each release carries about 18 months. Longer history needs the earlier quarterly workbooks, which are not collected yet.
- Checks: group headcounts add to the total in 90 of 90 comparisons (sex, ethnic and age; activity; state).
- `derived_gender_gap_monthly.csv`: median-wage gap between men and women each month. It runs about 1% to 4% in this series, against 7.5% in the 2025 all-employee survey. The two cover different populations, so neither contradicts the other.
- Industry detail is broad (agriculture, mining, manufacturing, construction, services), so it does not isolate ICT.
