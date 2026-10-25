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

## Public-sector pay scales (`mof/sspa_pay_scales/2026`)

Minimum and maximum monthly basic pay for 70 public-service grades, from Belanjawan 2026 Lampiran A (Ministry of Finance), extracted by `extract/mof_sspa.py` with pdfplumber from the PDF's text layer. Every row carries its page and line.
- Scope: civil-service posts under SSPA only, by grade, not by job title. Private-sector pay is not covered. Grade 1 starts at RM1,500; the federal management and professional series (Grades 9 to 15) run from RM2,250 to RM16,350 at the extremes.
- Columns: `min_rm`, `max_rm`, annual increment (RM, or a percentage for the top grades such as VU and VK) and the increment at the maximum.
- Checks: 70 rows read by the parser and 70 found by an independent line count; every minimum is below its maximum; maximum pay falls with grade in each numbered federal series. Grades 13P, 11 and similar series start at different points, so minimums are not expected to rise in order.
- Cross-check: all 16 federal grades (1 to 15 and 13P) match JPA's own table, Lampiran D1 of the SSPA circular (`docs.jpa.gov.my/docs/sspa/SSPA_LAMPIRAN_D.pdf`), on minimum, maximum, annual increment and increment at maximum. Run with `--cross-check` to repeat it.
- Not found: which SSPA grade each scheme grade maps to (for example the IT officer scheme, grades F41 to F54 under the old pay system). The JPA annexes that were readable do not give it, and the scheme and SPA hosts refuse this environment. No grade is assigned to any job title here.
- Licence: the document states none. The figures are facts from a public official document, credited to the Ministry of Finance. Check with the Ministry before relying on it for anything beyond reference.

## Local-only extractions (`data_local/`, not committed)

`extract/randstad_tech.py` reads the technology salary table on Randstad Malaysia's public 2026 page (6 roles, including data scientist, as basic monthly pay ranges in RM). The page states no reuse licence, so the output goes to `data_local/randstad/2026/` (ignored by git) with a manifest of source URL, dates, page hash and the page's own footnote. Re-run it on your own machine to rebuild. The Robert Walters, Hays and Michael Page Malaysia guides were not found as downloadable files; only second-hand quotations of them turned up, and those were not copied.

## Comparing sources (`extract/compare_salary_sources.py`)

Writes `data_local/salary_comparison.csv` (not committed): DOSM 2025 median and mean for Professionals, Information and communication and tertiary-educated; civil-service grades 9 and 12 to 15; and the local Randstad roles. Each row states its basis and population. The DOSM rows put the median in `mid_rm` and the mean in `high_rm`; the other rows are minimum to maximum, so do not read the `high_rm` column across sources as the same thing.

## MarkItDown MCP

`.mcp.json` registers Microsoft's `markitdown-mcp` (run with `uvx markitdown-mcp`) so a Claude Code session in this repo can convert PDFs, Office files and web pages to Markdown. It reads text layers only. Text embedded as unmapped glyphs, as on the cover page of Belanjawan Lampiran A, comes out as `(cid:NN)` codes. It is a reading aid; the extractors above remain the source of the committed data.

## Household income, 1970 to 2024 (`dosm/household_income`)

`extract/fetch_household_income.py` downloads OpenDOSM's national household income series (mean and median monthly household income, RM, 22 survey years from 1970 to 2024; CC BY 4.0). It is household income, not individual pay, and survey years are not annual, so it is a long-run proxy for the period before the Salaries & Wages Survey begins in 2010. DOSM's wage releases found online start at 2010 (the Salaries & Wages Survey tables run 2010 onward); no earlier individual wage survey report was found.
