# Extracted data (pilot)

Machine-readable tables extracted from official publications. This is a separate store from `registry/`, which stays metadata-only.

Rules:
- Only sources whose reuse terms allow it. DOSM publications on open.dosm.gov.my state CC BY 4.0; credit "Department of Statistics Malaysia".
- Prefer the agency's own Excel file (exact cell read). PDF extraction is a later step and needs page-level provenance and checks.
- Each extraction has a `manifest.json`: source URL, edition, file hash, method, and per-table checks. Every row in `values.csv` carries its sheet and source row.
- Failed checks are reported, not hidden. `sum_failures` lists tables where parts do not add to the total; Table B1/B2 (ethnic groups) are hierarchical, so their parts include sub-groups and the flat-sum check does not apply.
- MOHE statistics are restricted to individual and registered educational use. Their extractor may be run locally; the tables are not republished here.

Pilot: `dosm/salaries_wages/2025` from `salaries_wages_2025.xlsx` (extractor `extract/dosm_xlsx.py`, needs openpyxl).
