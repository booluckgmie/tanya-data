# Registry schema (v0.1)

`registry/registry.json` is `{schema, harvested_at, sources[], counts, records[]}`. One record per thing a user can be sent to.

| Field | Meaning |
|---|---|
| `kind` | `dataset`, `publication` (a series of DOSM editions), `dashboard`, `live_api` |
| `id` | Stable id. Datasets keep the portal id. Others are prefixed `pub:`, `dash:`, `api:` |
| `title`, `description` | `{en, ms}` as published by the agency |
| `category` | `{en, ms, sub}` portal category |
| `portals` | portals that list it: `datagovmy`, `opendosm`, `kkmnow`, `databnm` |
| `agencies` | `[{code, name, tier}]` source agencies. Empty when the metadata names none |
| `tier`, `tier_basis` | reliability tier 1-3 and why. See `tiers.json`. Weakest listed agency wins |
| `access` | `[{type, url, label?}]` where the data is: `csv`, `parquet`, `api`, `pdf`, `excel` |
| `pages` | `[{portal, url}]` canonical pages on the official portals |
| `licence` | `{name, url, basis}` where the portal states one, else `null` |
| `frequency` | `DAILY`, `MONTHLY`, ..., `REALTIME`, or `UNKNOWN` when the metadata does not say |
| `geography`, `geography_inferred` | levels in the metadata, and levels inferred from column names |
| `coverage` | `{begin, end}` years. For a publication series, reference years parsed from edition titles |
| `data_as_of`, `last_updated`, `next_update` | dates from the metadata, or `null` |
| `columns`, `join_keys` | column names, and the recognised join keys among them |
| `methodology`, `caveats` | text from the metadata |
| `related`, `see_also_ids` | graph edges to other records: declared related datasets, and publications or dashboards the dataset page links to |
| `methodology_docs` | publications only: DOSM technical notes |
| `releases` | publications only: `[[edition id, release date]]`, newest first |
| `publisher` | present when the publisher is not the source agency: `{name, official, note}` (for example ElectionData.MY, which compiles Election Commission results) |
| `frequency_inferred` | `true` when the frequency was inferred from column names or endpoint paths (BNM, MOH) |
| `verified` | `{checked_at, state, checks[]}` from `verify_links.py`. `state` is `ok`, `page_missing`, `file_missing` or `unreachable` |

Join keys are recognised from column names: `date`, `year`, `state`, `district`, `parliament`, `DUN`, `sex`, `age`, `age group`, `ethnicity`, `urban/rural`, `country`, `sector`, `MCOICOP division`.
