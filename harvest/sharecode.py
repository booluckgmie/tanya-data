"""Adapter for the owner's personal archive repository github.com/booluckgmie/sharecode.

That repository holds scraped copies of other organisations' data plus unrelated personal,
employer and research files. This adapter is a strict ALLOWLIST of folders whose official
origin is documented in the repository itself. It never walks the tree. Everything else is
deliberately left out (see EXCLUDED), in particular anything personal or employer-related.

Each record points first to the original official page and describes the repository only
as an archive copy (Tier 3, publisher = the archive). Only column names and date spans are
read; no values are stored. Standard library only.
"""
import csv, os, re, subprocess

ORG = 'https://github.com/booluckgmie/sharecode'
RAW = 'https://raw.githubusercontent.com/booluckgmie/sharecode'
PUBLISHER = {'name': 'booluckgmie/sharecode (personal archive on GitHub)', 'official': False,
             'note': 'Scraped copy made by the repository owner. Not published by the agency.'}
CAVEAT = ('Archive copy made by the repository owner by scraping the official source, not published by the agency. '
          'The repository states no licence. For authoritative figures use the original official page. %s')
DATED = re.compile(r'^(?:sabah_jobs_)?(\d{4}-\d{2}-\d{2})\.csv$')
# Left out on purpose, with the reason. Printed at harvest time so the exclusions are visible.
EXCLUDED = {
    'data_weatherUO': 'comes from Open-Meteo, a private foreign service, not an official Malaysian source',
    'data_oku': 'origin is not documented in the repository',
    'SARA2025': 'comes from a third-party platform and lists business addresses',
    'aurumvibe': 'gold prices from Yahoo Finance, not an official source',
    'marketIntel, data, nb, ncnc, nprc, docs-my, portfolio-cms, webdev, imagesDOSMT2023, notebooks':
        'personal, employer, research or non-data material',
}


def agency(code, name, tier):
    return {'code': code, 'name': name, 'tier': tier}


def ensure_repo(base):
    dest = os.path.join(base, 'sharecode')
    if os.path.isdir(os.path.join(dest, '.git')):
        subprocess.run(['git', '-C', dest, 'pull', '-q', '--ff-only'], check=False)
    else:
        os.makedirs(base, exist_ok=True)
        subprocess.run(['git', 'clone', '-q', '--depth', '1', ORG + '.git', dest], check=True, env=dict(os.environ, GIT_LFS_SKIP_SMUDGE='1'))
    return dest


def branch_of(dest):
    return subprocess.run(['git', '-C', dest, 'rev-parse', '--abbrev-ref', 'HEAD'], capture_output=True, text=True).stdout.strip() or 'master'


def header(path):
    with open(path, newline='', encoding='utf-8-sig') as f:
        return [c.strip() for c in next(csv.reader(f))]


def dated_files(folder):
    fs = sorted((m.group(1), f) for f in os.listdir(folder) for m in [DATED.match(f)] if m)
    return fs


def numeric_span(path, date_col, val_col):
    """First and last date that has a numeric value (MPOB marks holidays PH and no-trade NT)."""
    lo = hi = None
    with open(path, newline='', encoding='utf-8-sig') as f:
        rd = csv.DictReader(f)
        for r in rd:
            try:
                float(r[val_col])
            except (ValueError, TypeError, KeyError):
                continue
            d = r[date_col]
            lo = d if lo is None or d < lo else lo
            hi = d if hi is None or d > hi else hi
    return lo, hi


def rec(rid, title, desc, cat, agencies, origin, folder_url, access, cols, keys, freq, begin, end, asof, geo_inf, caveat_extra, related=()):
    return {
        'kind': 'dataset', 'id': 'sharecode:' + rid,
        'title': {'en': title, 'ms': title}, 'description': {'en': desc, 'ms': ''},
        'category': {'en': cat, 'ms': cat, 'sub': 'Archive copy (GitHub)'},
        'portals': ['sharecode'], 'agencies': agencies, 'tier': 3,
        'tier_basis': 'archive copy kept by an individual; the originating agency is named but did not publish this copy',
        'publisher': PUBLISHER, 'access': access,
        'pages': [dict(origin), {'portal': 'sharecode', 'url': folder_url}],
        'licence': None, 'frequency': freq, 'frequency_inferred': True,
        'geography': [], 'geography_inferred': geo_inf, 'demography': [],
        'coverage': {'begin': begin, 'end': end}, 'data_as_of': asof, 'last_updated': None, 'next_update': None,
        'columns': [{'name': c, 'title': '', 'description': ''} for c in cols], 'join_keys': keys,
        'methodology': '', 'caveats': CAVEAT % caveat_extra, 'related': list(related), 'see_also': [],
        'source_agencies_raw': [a['code'].upper() for a in agencies] + ['archive copy'],
    }


def build_sharecode(infer_keys, base, log):
    d = ensure_repo(base)
    br = branch_of(d)
    tree = lambda p: '%s/tree/%s/%s' % (ORG, br, p)
    raw = lambda p: '%s/%s/%s' % (RAW, br, p)
    out = []

    # --- APIMS hourly air pollutant index (Department of Environment)
    fs = dated_files(os.path.join(d, 'data_apims'))
    cols = header(os.path.join(d, 'data_apims', fs[-1][1]))
    keys, geo = infer_keys([{'name': c.lower()} for c in cols])
    arch = 'data_apims/archiveAPI201707-20241103.parquet'
    access = [{'type': 'csv', 'label': 'Latest daily file (CSV)', 'url': raw('data_apims/' + fs[-1][1])},
              {'type': 'web', 'label': 'All daily files (GitHub folder)', 'url': tree('data_apims')}]
    if os.path.exists(os.path.join(d, arch)):
        access.append({'type': 'parquet', 'label': 'Archive Jul 2017 to Nov 2024 (Parquet)', 'url': raw(arch)})
    out.append(rec('apims_hourly', 'Hourly Air Pollutant Index by station (archive of the DOE APIMS portal)',
        'Hourly Air Pollutant Index (API) readings for monitoring stations across Malaysia, scraped from the Department of Environment public portal, one file per day. The official portal shows current readings; this archive keeps the history.',
        'Environment', [agency('jas', 'Department of Environment (DOE/JAS)', 2)],
        {'portal': 'doeapims', 'url': 'https://eqms.doe.gov.my/'}, tree('data_apims'), access, cols, keys, 'HOURLY',
        2017, int(fs[-1][0][:4]), fs[-1][0], geo,
        'Daily files run from %s; a Parquet archive covers July 2017 to November 2024 (period taken from its file name). The old APIMS address (apims.doe.gov.my) no longer resolves; the public portal is now at eqms.doe.gov.my, and current readings are in the live API record api:apims_hourly.' % fs[0][0],
        related=['air_pollution', 'api:apims_hourly']))

    # --- GSO electricity generation
    fs = dated_files(os.path.join(d, 'data_gso'))
    cols = header(os.path.join(d, 'data_gso', fs[-1][1]))
    keys, geo = infer_keys([{'name': c.lower()} for c in cols])
    out.append(rec('gso_generation', 'Electricity generation by fuel type, Peninsular Malaysia (archive of GSO data)',
        'Electricity generation by fuel type (coal, gas, co-generation, oil, hydro, solar and others) through the day, scraped daily from the Grid System Operator system data page.',
        'Energy', [agency('gso', 'Grid System Operator (GSO)', 3)],
        {'portal': 'gso', 'url': 'https://www.gso.org.my/SystemData/CurrentGen.aspx'}, tree('data_gso'),
        [{'type': 'csv', 'label': 'Latest daily file (CSV)', 'url': raw('data_gso/' + fs[-1][1])},
         {'type': 'web', 'label': 'All daily files (GitHub folder)', 'url': tree('data_gso')}],
        cols, keys, 'DAILY', int(fs[0][0][:4]), int(fs[-1][0][:4]), fs[-1][0], geo,
        'Daily files run from %s. GSO is a company unit, not a government agency. Coverage of Sabah and Sarawak is not stated.' % fs[0][0]))

    # --- Sabah job portal
    jd = os.path.join(d, 'data_jobsabah', 'data_jobsabah', 'all_jobs')
    fs = dated_files(jd)
    cols = header(os.path.join(jd, fs[-1][1]))
    keys, geo = infer_keys([{'name': c.lower()} for c in cols])
    out.append(rec('sabah_jobs', 'Job vacancies advertised on the Sabah government job portal (daily archive)',
        'Daily snapshots of job vacancies listed on the Sabah government job portal, deduplicated, one file per day.',
        'Labour', [agency('sabah-jobs', 'Sabah government job portal (jobs.sabah.gov.my)', 2)],
        {'portal': 'sabahjobs', 'url': 'https://jobs.sabah.gov.my/'}, tree('data_jobsabah/data_jobsabah'),
        [{'type': 'csv', 'label': 'Latest daily file (CSV)', 'url': raw('data_jobsabah/data_jobsabah/all_jobs/' + fs[-1][1])},
         {'type': 'web', 'label': 'All daily files (GitHub folder)', 'url': tree('data_jobsabah/data_jobsabah/all_jobs')}],
        cols, keys, 'DAILY', int(fs[0][0][:4]), int(fs[-1][0][:4]), fs[-1][0], geo,
        'Sabah only. Daily files run from %s. These are job advertisements, not employment statistics.' % fs[0][0]))

    # --- NAPIC 2022 property tables
    for fname, rid, title, desc, extra in (
        ('napic_jual2022.csv', 'napic_sale_2022', 'Property transaction prices by area and type, 2022 (archive of NAPIC tables)',
         'Average transacted property prices by locality, property type and state for 2022, with 2021 comparison, extracted from the National Property Information Centre annual property market report tables.',
         'Extracted from NAPIC report tables for 2022 only.'),
        ('napic_sewa2022.csv', 'napic_rent_2022', 'Property rental ranges by area and type, 2022 (archive of NAPIC tables)',
         'Rental ranges by locality, property type and state for 2022, with 2021 comparison, extracted from the National Property Information Centre annual property market report tables.',
         'Extracted from NAPIC report tables for 2022 only.')):
        p = os.path.join(d, 'data_napic', fname)
        cols = header(p)
        out.append(rec(rid, title, desc, 'Housing', [agency('napic', 'National Property Information Centre (NAPIC), JPPH', 2)],
            {'portal': 'napic', 'url': 'https://napic.jpph.gov.my/'}, tree('data_napic'),
            [{'type': 'csv', 'label': 'CSV', 'url': raw('data_napic/' + fname)}], cols, [], 'YEARLY', 2021, 2022, None,
            ['STATE', 'DISTRICT'], extra + ' Values are as extracted; check them against the NAPIC report.',
            related=['napic:laporan_pasaran_harta_tahunan', 'napic:jadual_data_transaksi_harta_tanah', 'napic:indeks_harga_rumah_malaysia']))

    # --- MPOB crude palm oil daily price
    p = os.path.join(d, 'mpob', 'cpo_daily_prices.csv')
    lo, hi = numeric_span(p, 'date', 'price')
    out.append(rec('mpob_cpo_daily', 'Crude palm oil (CPO) local daily price (archive of MPOB data)',
        'Daily local crude palm oil price, scraped from the Malaysian Palm Oil Board price pages. Public holidays and non-trading days are marked rather than priced.',
        'Agriculture', [agency('mpob', 'Malaysian Palm Oil Board (MPOB)', 2)],
        {'portal': 'mpob', 'url': 'https://bepi.mpob.gov.my/admin2/price_local_daily_view_cpo_msia.php?more=Y&jenis=1W'}, tree('mpob'),
        [{'type': 'csv', 'label': 'CSV', 'url': raw('mpob/cpo_daily_prices.csv')}, {'type': 'web', 'label': 'Yearly files (GitHub folder)', 'url': tree('mpob/data')}],
        header(p), ['date'], 'DAILY', int(lo[:4]), int(hi[:4]), hi, [],
        'Priced days run from %s to %s. The price column holds PH (public holiday) or NT (no trade) on other days, and the file lists dates beyond the last priced day. MPOB now serves only the last three years, so the 2023 prices in this archive are no longer available from MPOB.' % (lo, hi),
        related=['mpob:cpo_daily_price']))

    # --- Bursa PN17 / GN3
    p = os.path.join(d, 'bursaMY', 'pn17_gn3_companies.csv')
    out.append(rec('bursa_pn17_gn3', 'Bursa Malaysia PN17 and GN3 listed companies (archive of the Bursa list)',
        'Listed companies classified under Practice Note 17 (PN17) or Guidance Note 3 (GN3), with the date Bursa Malaysia last updated the list. Tracked daily from the Bursa listing directory page; a historical file and the source PDFs are kept alongside.',
        'Finance', [agency('bursa', 'Bursa Malaysia', 3)],
        {'portal': 'bursa', 'url': 'https://www.bursamalaysia.com/bm/trade/trading_resources/listing_directory/pn17_and_gn3_companies'}, tree('bursaMY'),
        [{'type': 'csv', 'label': 'Current list (CSV)', 'url': raw('bursaMY/pn17_gn3_companies.csv')},
         {'type': 'csv', 'label': 'Historical list (CSV)', 'url': raw('bursaMY/pn17_gn3_historical.csv')},
         {'type': 'web', 'label': 'Source PDFs (GitHub folder)', 'url': tree('bursaMY')}],
        header(p), [], 'UNKNOWN', None, None, None, [],
        'Bursa Malaysia is an exchange company, not a government agency.'))
    log('sharecode: %d records from an allowlist of folders. Excluded: %s' % (len(out), '; '.join('%s (%s)' % (k, v) for k, v in EXCLUDED.items())))
    return out
