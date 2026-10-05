# Tanya Data

A discovery layer for Malaysian official data. A user asks a question in plain words (English, Bahasa Malaysia or both) and the platform points to the right official dataset, report, dashboard or live feed, then sends them to the original source.

The platform holds **metadata only**. It never copies, generates or displays data values. Every result links to the agency's own page.

## Pipeline

```
harvest/harvest.py       datagovmy-meta + live API probes  ->  registry/registry.json
harvest/verify_links.py  checks every page and file URL    ->  registry/registry.json, registry/link_report.md
harvest/build_app.py     registry + app template           ->  dist/index.html
```

Python 3 standard library only. Run in this order:

```
python3 harvest/harvest.py          # clones .cache/datagovmy-meta on first run
python3 harvest/verify_links.py     # about 1,400 URLs; results cached 12 hours in .cache/
python3 harvest/build_app.py
```

## What is indexed

| Kind | Source | Records |
|---|---|---|
| Dataset | data.gov.my / OpenDOSM / KKMNOW catalogue (`data-catalogue/`) | 297 |
| Report series | DOSM publications (`pub-dosm/`), editions grouped into series, with technical notes attached | 94 |
| Dashboard | portal dashboards and explorers (`dashboards/`, `explorers/`) | 56 |
| Live feed | data.gov.my live APIs: weather, warnings, flood stations, GTFS static and realtime | 8 |

See `registry/SCHEMA.md` for the record format and `registry/tiers.json` for the provisional reliability tiers.

## Rules the platform keeps

- Metadata and pointers only. No copied data.
- Every record carries its agency, a reliability tier with the reason, a licence where the portal states one, and a link-check date.
- A record whose official portal page returns 404/410 is withheld from the app and listed in `registry/link_report.md`. A network error never hides a record.
- Tiers and fitness scores are estimates made by this tool, not official ratings.

## Known gaps

- Metadata from `datagovmy-meta` only. Agencies that publish elsewhere (BNM's own API, state portals, MOH GitHub) are not yet harvested.
- No LLM enrichment yet (example questions, synonyms, caveats). Search is lexical plus a hand-built bilingual glossary.
- The DOSM investor-portal OpenAPI specs in `data-catalogue/openapi/` carry no titles and mostly duplicate catalogue datasets, so they are not indexed.
