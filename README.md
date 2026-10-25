# Tanya Data

A discovery layer for Malaysian official data. A user asks a question in plain words (English, Bahasa Malaysia or both) and the platform points to the right official dataset, report, dashboard or live feed, then sends them to the original source.

The platform holds **metadata only**. It never copies, generates or displays data values. Every result links to the agency's own page.

## Pipeline

```
harvest/harvest.py       datagovmy-meta, BNM, MOH, NAPIC, docs, ...  ->  registry/registry.json
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
| Dataset | Toll sources (`harvest/tolls.py`): LLM's directories of 33 operating and 3 under-construction highways, read directly from llm.gov.my | 2 |
| Dashboard / Dataset | Toll rate lookup (kadartol.llm.gov.my) and two old data.gov.my toll datasets: **identified through web search only, not read**, flagged unreachable | 3 |
| Report series | NAPIC (JPPH) property publications: 14 series across market, stock, status and price/rental indices, read from napic.jpph.gov.my (`harvest/napic.py`) | 14 |
| Dashboard | NAPIC open transaction data, an embedded Tableau Public dashboard | 1 |
| Dataset / Report series | MPOB public pages (`harvest/mpob.py`): daily CPO price (rolling 3 years, Excel per year), the latest monthly industry performance report and year summary, and the annual Overview of the Malaysian Oil Palm Industry (10 PDFs, 2016 to 2025) | 4 |
| Report series | DOSM publications (`pub-dosm/`), editions grouped into series, with technical notes attached | 94 |
| Report series | DOSM release archive (`harvest/dosm_archive.py`): edition history back to 2014 added to 8 labour and wage series (Salaries & Wages 15 editions, Labour Force 194), plus a new series, Job Vacancies Advertised Online | 1 new |
| Dashboard | portal dashboards and explorers (`dashboards/`, `explorers/`) | 56 |
| Live feed | DOE APIMS public API: hourly Air Pollutant Index by station, last 24 hours (`harvest/doe.py`) | 1 |
| Live feed | data.gov.my realtime APIs read from the developer docs: weather forecast, weather and earthquake warnings, flood warning, GTFS static and realtime for KTMB, Prasarana and BAS.MY (`harvest/devdocs.py`) | 10 |
| API | data.gov.my static query APIs from the same docs: the Data Catalogue API and the OpenDOSM API | 2 |

Of these, 66 are withheld from the page: 6 dashboards whose portal page is gone, and 60 BNM tables that the agency lists but whose endpoint returns no records.

See `registry/SCHEMA.md` for the record format and `registry/tiers.json` for the provisional reliability tiers.

## Rules the platform keeps

- Metadata and pointers only. No copied data.
- Respect each source's limits. `api.data.gov.my` allows 4 requests per minute per API, so the pipeline spaces and caches its calls to it, and checks one endpoint per API record.
- A record whose page could not be read says so on its card ("could not be reached when last checked"). GitHub web pages return 403 through this environment's proxy, so a record counts as live when its page or a file link answers.
- Every record carries its agency, a reliability tier with the reason, a licence where the portal states one, and a link-check date.
- A record whose official portal page returns 404/410 is withheld from the app and listed in `registry/link_report.md`. A network error never hides a record.
- Tiers and fitness scores are estimates made by this tool, not official ratings.

## Considered and not indexed

- **PAYGAP Asia (paygap.asia):** a crowdsourced salary-sharing platform (users submit payslips to unlock the data). It has no public API, only the internal endpoints its own web app calls, and its Terms of Use forbid copying, reproducing or publicly displaying its content. It is also not official data. Not indexed, and its endpoints are not called. The official labour and wage series are in the registry instead.
- **JobStreet's internal search API** (`/api/chalice-search/...`): not called. JobStreet's terms say "You may not use data mining, robots, screen scraping, or similar automated data gathering, extraction or publication tools on our websites and apps", and its robots.txt disallows its job search API paths. The endpoint is undocumented and the pasted URL carried personal user and session ids, which are deliberately not stored here. DOSM's Job Vacancies Advertised Online (built from job ads on major private recruitment platforms) is the official source.
- **Hiredly Salary Checker (my.hiredly.com/salary):** not pulled. The page gives salary by role, level and location from Hiredly job ads, but the report sits behind a free sign-up (the public page shows "0 job ads analysed"), so there is no open data to read. Hiredly's Terms and Conditions allow a single copy for personal, non-commercial use, forbid using its content publicly or commercially, and forbid reselling information from the site (clauses 3.1, 3.3 and 18.1). Collecting reports through an account and republishing them here would break those terms. To use it, ask Hiredly for a data licence (hello@hiredly.com or employer@hiredly.com), or look figures up one at a time on the site yourself.
- **Free salary-by-title websites (explored 2026-10-24):** CariGaji, Fastjobs, JobStreet Explore Salaries, NodeFlair, Paylab, PayScale, Michael Page's comparison tool and Calculator Malaysia all publish salary ranges by job title for free, but none is official and none states a reuse licence that was found. CariGaji's own methodology page says its ranges are compiled from the annual recruiter guides of Michael Page, Hays and Randstad plus JobStreet advertised pay, for the Klang Valley, so copying it would republish those firms' figures second-hand. Their terms were not reviewed except as noted for Hiredly above, so none is indexed or copied. They are fine for a person to look up; for a project dataset, use the official sources below or a licensed feed.
- **Private-sector salary by title, other searches (2026-10-25):** the only recurring industry source found is PIKOM's ICT job market outlook (ICT professionals averaged about RM8,100 to RM8,500 a month in 2015 and 2016, co-produced with JobStreet); the editions found were dated and their current availability was not confirmed. Robert Walters' and Hays' annual guides give data scientist ranges (for example RM180,000 to RM300,000 a year in technology for 2026) but are recruiter marketing material and were not retrieved or copied. MDEC, TalentCorp, MEF and PERKESO publish no occupation salary table that was found. DOSM's formal-sector wages carry no occupation split.
- **TalentCorp and LinkedIn (searched 2026-10-25):** TalentCorp (a Ministry of Human Resources agency) publishes the MyMahir Malaysia Critical Occupations List (MyCOL 2024/2025, 212 pages, `talentcorp.com.my`, 66 occupations) and earlier editions back to 2015/2016. It carries no salary figures; it scores shortage using vacancy and wage-premium indicators. It does list a data scientist and analyst occupation as in shortage, with respondents reporting vacancies mostly at junior level (1 to 3 years). It is useful as demand evidence, not as a pay source. No LinkedIn-published Malaysia salary report was found; LinkedIn's talent insights are not public.
- **Official sources that give pay by grade or group:** Belanjawan 2026 Lampiran A (`belanjawan.mof.gov.my/pdf/belanjawan2026/sp/LAMPIRAN-A.pdf`, 3 pages) lists minimum and maximum monthly pay for every public-sector grade under SSPA. It covers public-service posts only and is by grade, not job title. The 2017 data.gov.my dataset "Minimum and Maximum Median Monthly Basic Salary by MSIC and MASCO" is on `archive.data.gov.my`, which this environment cannot reach. Lampiran A is extracted to `data/mof/sspa_pay_scales/2026`; the 2017 dataset is not.
- **Commercial salary and job-market reports** (for example Hays, Robert Walters, Michael Page, Randstad, JobStreet, LinkedIn): not indexed pending a decision on whether third-party commercial sources belong at Tier 3. No LinkedIn Malaysia annual series was found. DOSM's own Job Vacancies Advertised Online series is the official counterpart.

## MPOB URL patterns (bepi.mpob.gov.my)

| What | Pattern |
|---|---|
| Daily CPO price, table | `/admin2/price_local_daily_view_cpo_msia.php?more=Y&jenis={1W,1M,3M,6M,1Y}[&tahun=YYYY]` |
| Daily CPO price, chart | `/admin2/chart_cpomsia.php?jenis={1W,1M,3M,6M,1Y}&tahun=YYYY` |
| Daily CPO price, Excel | `/admin2/price_local_daily_view_cpo_msia_excel.php?val=YYYY&excel=Y` |
| Monthly performance report | `/stat/web_report1.php?val=<id>&val1=<MM>`: latest month only; `<id>` cannot be derived for other months |
| Annual overview | `/images/overview/Overview_of_Industry_YYYY.pdf` (2016 to 2020), `Overview{YYYY}.pdf` (2021 on) |

Daily is the finest granularity published. Only the last three years answer (2024 to 2026 when checked); earlier years return an empty file. `price.mpob.gov.my` and the export duties page need a login and are not touched.

## Preserved copies (`archive/`)

The registry holds metadata only. `archive/` is a separate, deliberate exception: preserved copies of source files that an official site stops serving, so the history survives. The registry still sends users to the official page first.

- `archive/mpob/cpo_daily_YYYY.csv`: MPOB's daily crude palm oil price, one tidy file per year, columns `date, price_rm_per_tonne, status` where status is `price`, `public_holiday`, `no_trade` or `pending`. MPOB serves only the last three years, so each year is saved while it is still available and never deleted afterwards. 2023 was imported from an earlier scrape of the MPOB price pages; 2024 to 2026 come straight from MPOB's Excel export. The parser was checked against that independent scrape (0 differences over 628 days). Future public holidays and weekends in the current year are listed by MPOB in advance and appear with their status and no price.
- `harvest/archive_mpob.py` does the download and parsing. It rewrites a file only when the parsed content changes (the Excel files embed a new timestamp on every download).
- `.github/workflows/archive-mpob.yml` runs it every Monday and can be started by hand. It has not yet run on GitHub: the first run needs the Actions tab, and GitHub runs scheduled workflows from the default branch only.

## Known gaps

- The platform stores edition titles, dates and links for historical series, not the figures inside them. Extracting values into a separate store would be a different design and needs an explicit decision.
- The `sharecode` adapter is an allowlist. That repository also holds personal, employer and research files, which are never read. Weather (Open-Meteo, not official), `data_oku` (origin undocumented) and `SARA2025` (third-party platform, business addresses) are left out on purpose.
- Not harvested because the host refuses this environment: the Ministry of Education EMIS Risalah map (`emisonline.moe.gov.my/risalahmap/`) resets the TLS handshake and `www.moe.gov.my` returns 403. Run the pipeline from another network, or add the host to the environment's allowed domains and retry.
- Toll rates: the official rate lookup (`kadartol.llm.gov.my`) and the old data.gov.my toll datasets could not be read from the harvesting environment (503, connection reset, and a firewall 403). They are indexed as pointers from search results, marked unverified, and no rate values are stored. Rerun from another network to read them.
- Not yet harvested: state portals, and MOH data outside the two GitHub repositories above (other MoH-Malaysia repositories were not checked).
- BNM tables with only parameterised endpoints (for example `/year/{year}`) cannot be link-checked beyond their portal page.
- BNM and MOH frequencies are inferred from column names and endpoint paths, and flagged `frequency_inferred`.
- The MOH repositories are published snapshots; the page shows each file's date span so staleness is visible.
- The developer-docs adapter compares its endpoint list with the docs on every run and logs `devdocs DRIFT` when they differ. Titles and descriptions are written in the adapter, not taken from the docs.
- No LLM enrichment yet (example questions, synonyms, caveats). Search is lexical plus a hand-built bilingual glossary.
- The DOSM investor-portal OpenAPI specs in `data-catalogue/openapi/` carry no titles and mostly duplicate catalogue datasets, so they are not indexed.

## Site usage (Vercel Web Analytics)

The page loads Vercel's cookie-free analytics script (`/_vercel/insights/script.js`, served only on Vercel once Web Analytics is enabled for the project). It sends no search text and no custom events. The "Site usage" section shows aggregate visitors, pageviews, daily trend, top pages, countries, devices and referrers from `app/analytics.json`, a snapshot taken at build time. Refresh it with `VERCEL_TOKEN=... python3 tools/fetch_analytics.py`, rebuild, and commit. Hobby plans keep 31 days of data.
