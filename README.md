# Tanya Data

A discovery layer for Malaysian official data. A user asks a question in plain words (English, Bahasa Malaysia or both) and the platform points to the right official dataset, report, dashboard or live feed, then sends them to the original source.

The platform holds **metadata only**. It never copies, generates or displays data values. Every result links to the agency's own page.

## Pipeline

```
harvest/harvest.py       datagovmy-meta + live API probes  ->  registry/registry.json
harvest/verify_links.py  checks every page and file URL    ->  registry/registry.json, registry/link_report.md
harvest/build_app.py     registry + app template           ->  dist/index.html
```

Python 3 standard library plus `curl` (BNM and ElectionData reject Python's TLS handshake). Run in this order:

```
python3 harvest/harvest.py          # clones datagovmy-meta and the MOH repos into .cache/ on first run
python3 harvest/verify_links.py     # about 1,400 URLs; results cached 12 hours in .cache/
python3 harvest/build_app.py
```

## What is indexed

| Kind | Source | Records |
|---|---|---|
| Dataset | data.gov.my / OpenDOSM / KKMNOW catalogue (`data-catalogue/`) | 297 |
| Dataset | Bank Negara Malaysia Open API: one record per statistical table, from BNM's own specification (`harvest/bnm.py`) | 341 |
| Dataset | Ministry of Health open-data repositories `covid19-public` and `data-darah-public` on GitHub (`harvest/moh.py`) | 36 |
| Dataset | ElectionData.MY catalogue, an independent project compiling Election Commission results; always Tier 3 (`harvest/electiondata.py`) | 202 |
| Dataset | Archive copies in `booluckgmie/sharecode` (APIMS air pollutant index, GSO electricity generation, Sabah job portal, NAPIC 2022 property tables, MPOB palm oil prices, Bursa PN17/GN3); allowlisted folders only, always Tier 3 (`harvest/sharecode.py`) | 7 |
| Report series | DOSM publications (`pub-dosm/`), editions grouped into series, with technical notes attached | 94 |
| Dashboard | portal dashboards and explorers (`dashboards/`, `explorers/`) | 56 |
| Live feed | data.gov.my live APIs: weather, warnings, flood stations, GTFS static and realtime | 8 |

Of these, 66 are withheld from the page: 6 dashboards whose portal page is gone, and 60 BNM tables that the agency lists but whose endpoint returns no records.

See `registry/SCHEMA.md` for the record format and `registry/tiers.json` for the provisional reliability tiers.

## Rules the platform keeps

- Metadata and pointers only. No copied data.
- Every record carries its agency, a reliability tier with the reason, a licence where the portal states one, and a link-check date.
- A record whose official portal page returns 404/410 is withheld from the app and listed in `registry/link_report.md`. A network error never hides a record.
- Tiers and fitness scores are estimates made by this tool, not official ratings.

## Known gaps

- The `sharecode` adapter is an allowlist. That repository also holds personal, employer and research files, which are never read. Weather (Open-Meteo, not official), `data_oku` (origin undocumented) and `SARA2025` (third-party platform, business addresses) are left out on purpose.
- Not yet harvested: state portals, and MOH data outside the two GitHub repositories above (other MoH-Malaysia repositories were not checked).
- BNM tables with only parameterised endpoints (for example `/year/{year}`) cannot be link-checked beyond their portal page.
- BNM and MOH frequencies are inferred from column names and endpoint paths, and flagged `frequency_inferred`.
- The MOH repositories are published snapshots; the page shows each file's date span so staleness is visible.
- No LLM enrichment yet (example questions, synonyms, caveats). Search is lexical plus a hand-built bilingual glossary.
- The DOSM investor-portal OpenAPI specs in `data-catalogue/openapi/` carry no titles and mostly duplicate catalogue datasets, so they are not indexed.
