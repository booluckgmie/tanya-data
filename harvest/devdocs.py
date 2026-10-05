"""data.gov.my developer documentation adapter: https://developer.data.gov.my/

The docs describe Malaysia's official Open API (https://api.data.gov.my). This adapter builds one
registry record per API (kind 'api' for the static query APIs, 'live_api' for the realtime ones).
Facts come from the fetched docs pages: endpoints, rate limits, update frequencies, sources,
licence. The record titles and descriptions are written here. Every endpoint and category listed
below is checked against the docs text, and anything the docs list that is missing here, or the
reverse, is logged as drift so the adapter gets updated when the docs change.

The API allows 4 requests per minute per API with no token, so probes are spaced out and cached.
Metadata only: probes read the column names of one row, never store values. Standard library only.
"""
import html, json, os, re, time
from net import curl

DOCS = 'https://developer.data.gov.my'
API = 'https://api.data.gov.my'
PAGES = {'weather': '/realtime-api/weather', 'gtfs_static': '/realtime-api/gtfs-static', 'gtfs_realtime': '/realtime-api/gtfs-realtime',
         'data_catalogue': '/static-api/data-catalogue', 'opendosm': '/static-api/opendosm', 'rate': '/rate-limit',
         'changelog': '/changelog', 'faq': '/faq', 'query': '/request-query'}
LICENCE = {'name': 'Creative Commons Attribution 4.0 International (CC BY 4.0)', 'url': 'https://creativecommons.org/licenses/by/4.0/',
           'basis': 'stated in the developer docs FAQ'}
QUERY_NOTE = 'JSON endpoints accept the query parameters filter, ifilter, contains, icontains, range, sort, date_start, date_end, limit, include and exclude.'
BAS = ['kangar', 'alor-setar', 'kota-bharu', 'kuala-terengganu', 'ipoh', 'seremban-a', 'seremban-b', 'melaka', 'johor', 'kuching']
PRASARANA_STATIC = ['rapid-bus-penang', 'rapid-bus-kuantan', 'rapid-bus-mrtfeeder', 'rapid-rail-kl', 'rapid-bus-kl']
PRASARANA_RT = ['rapid-bus-kl', 'rapid-bus-mrtfeeder', 'rapid-bus-kuantan', 'rapid-bus-penang']
# id, kind, agency codes, title en/ms, description en/ms, topic, endpoints [(label, path)], doc page, frequency, geography, probe path, extra caveat
SPECS = [
    ('api:data_catalogue_api', 'api', [], 'Data Catalogue API: query any data.gov.my catalogue dataset by id',
     'API untuk Katalog Data: pertanyaan mana-mana set data katalog data.gov.my mengikut id',
     'Programmatic access to the data.gov.my data catalogue. Send GET /data-catalogue?id=<dataset id> and filter, sort and limit the rows. The id of each dataset is on its catalogue page, under "Sample OpenAPI query".',
     'Akses secara programatik kepada katalog data data.gov.my. Hantar GET /data-catalogue?id=<id set data> dan tapis, isih serta hadkan baris.',
     'Developer API', [('API (needs ?id=<dataset id>)', '/data-catalogue?id=fuelprice&limit=1')], 'data_catalogue', 'UNKNOWN', [], None,
     'Coverage and frequency depend on the dataset you request. A dataset not available through the API is marked on its catalogue page.'),
    ('api:opendosm_api', 'api', [], 'OpenDOSM API: query any OpenDOSM catalogue dataset by id',
     'API OpenDOSM: pertanyaan mana-mana set data katalog OpenDOSM mengikut id',
     'Programmatic access to the OpenDOSM data catalogue only. Send GET /opendosm?id=<dataset id>, for example cpi_core. For datasets across all of data.gov.my use the Data Catalogue API instead.',
     'Akses secara programatik kepada katalog data OpenDOSM sahaja. Hantar GET /opendosm?id=<id set data>, contohnya cpi_core.',
     'Developer API', [('API (needs ?id=<dataset id>)', '/opendosm?id=cpi_core&limit=1')], 'opendosm', 'UNKNOWN', [], None,
     'Coverage and frequency depend on the dataset you request.'),
    ('api:weather_forecast', 'live_api', ['met'], 'Weather forecast by location (7-day general forecast)', 'Ramalan cuaca mengikut lokasi (ramalan am 7 hari)',
     '7-day general weather forecast for states, districts, towns, divisions and recreation centres, from the Malaysian Meteorological Department (MET Malaysia).',
     'Ramalan cuaca am 7 hari bagi negeri, daerah, bandar, bahagian dan pusat rekreasi, daripada Jabatan Meteorologi Malaysia (MET Malaysia).',
     'Environment', [('API: forecast', '/weather/forecast')], 'weather', 'DAILY', ['DISTRICT'], '/weather/forecast',
     'Marine forecasts are not available. Filter by location type with ?contains=<St|Ds|Tn|Dv|Rc>@location__location_id.'),
    ('api:weather_warning', 'live_api', ['met'], 'Weather warnings', 'Amaran cuaca',
     'Current weather warnings such as strong winds, rough seas and heavy rain, from MET Malaysia. Updated when a warning is issued.',
     'Amaran cuaca semasa seperti angin kencang, laut bergelora dan hujan lebat, daripada MET Malaysia. Dikemas kini apabila amaran dikeluarkan.',
     'Environment', [('API: warnings', '/weather/warning')], 'weather', 'REALTIME', [], '/weather/warning', ''),
    ('api:weather_earthquake', 'live_api', ['met'], 'Earthquake warnings', 'Amaran gempa bumi',
     'Earthquake warnings from MET Malaysia, in a separate endpoint because of their different format. Updated when a warning is issued.',
     'Amaran gempa bumi daripada MET Malaysia, dalam endpoint berasingan kerana formatnya berbeza.',
     'Environment', [('API: earthquake warnings', '/weather/warning/earthquake')], 'weather', 'REALTIME', [], '/weather/warning/earthquake', ''),
    ('api:flood_warning', 'live_api', ['jps'], 'Flood warning: river and rainfall station readings', 'Amaran banjir: bacaan stesen sungai dan hujan',
     'Near real-time water level and rainfall readings by station, with warning levels, from the Department of Irrigation and Drainage (JPS).',
     'Bacaan paras air dan hujan hampir masa nyata mengikut stesen, beserta tahap amaran, daripada Jabatan Pengairan dan Saliran (JPS).',
     'Environment', [('API: flood warning', '/flood-warning')], 'changelog', 'REALTIME', ['STATE', 'DISTRICT'], '/flood-warning',
     'This endpoint is listed in the docs changelog (release 1.0.0) but has no page of its own.'),
    ('api:gtfs_static_ktmb', 'live_api', ['ktmb'], 'KTMB train timetables and routes (GTFS Static)', 'Jadual dan laluan keretapi KTMB (GTFS Static)',
     'Routes, stops, trips and schedules for KTM Komuter and ETS in GTFS format, returned as a ZIP file.',
     'Laluan, stesen, perjalanan dan jadual KTM Komuter dan ETS dalam format GTFS, dipulangkan sebagai fail ZIP.',
     'Transportation', [('API: KTMB (ZIP)', '/gtfs-static/ktmb')], 'gtfs_static', 'DAILY', [], None, 'Updated daily at 00:01. Refresh at least once a day, around 4am.'),
    ('api:gtfs_static_prasarana', 'live_api', ['prasarana'], 'Rapid KL bus and rail timetables and routes (GTFS Static)', 'Jadual dan laluan bas dan rel Rapid KL (GTFS Static)',
     'Routes, stops, trips and schedules for Prasarana services (Rapid Rail KL, Rapid Bus KL, MRT Feeder, Penang, Kuantan) in GTFS format, returned as a ZIP file. Choose a service with ?category=.',
     'Laluan, perhentian, perjalanan dan jadual perkhidmatan Prasarana dalam format GTFS, dipulangkan sebagai fail ZIP.',
     'Transportation', [('API: Prasarana %s (ZIP)' % c, '/gtfs-static/prasarana?category=' + c) for c in PRASARANA_STATIC], 'gtfs_static', 'UNKNOWN', [], None,
     'Categories: %s. Updated as required. About 2%% of rapid-bus-kl trips are missing from stop_times.txt.' % ', '.join(PRASARANA_STATIC)),
    ('api:gtfs_static_mybas', 'live_api', [], 'BAS.MY stage bus timetables and routes (GTFS Static)', 'Jadual dan laluan bas BAS.MY (GTFS Static)',
     'Routes, stops and schedules for BAS.MY stage bus services in Kangar, Alor Setar, Kota Bharu, Kuala Terengganu, Ipoh, Seremban, Melaka, Johor Bahru and Kuching, in GTFS format, returned as ZIP files.',
     'Laluan, perhentian dan jadual perkhidmatan bas berperingkat BAS.MY di Kangar, Alor Setar, Kota Bharu, Kuala Terengganu, Ipoh, Seremban, Melaka, Johor Bahru dan Kuching.',
     'Transportation', [('API: BAS.MY %s (ZIP)' % c, '/gtfs-static/mybas-' + c) for c in BAS], 'gtfs_static', 'UNKNOWN', ['STATE'], None,
     'One endpoint per city (Seremban has two, a and b: query both). Updated as required.'),
    ('api:gtfs_realtime_ktmb', 'live_api', ['ktmb'], 'KTMB live train positions (GTFS Realtime)', 'Kedudukan keretapi KTMB secara langsung (GTFS Realtime)',
     'Live vehicle positions for KTMB trains as a GTFS Realtime protobuf feed, refreshed every 30 seconds.',
     'Kedudukan keretapi KTMB secara langsung sebagai suapan protobuf GTFS Realtime, dikemas kini setiap 30 saat.',
     'Transportation', [('API: KTMB (protobuf)', '/gtfs-realtime/vehicle-position/ktmb')], 'gtfs_realtime', 'REALTIME', [], None, 'Vehicle positions only. Service alerts and trip updates are planned.'),
    ('api:gtfs_realtime_prasarana', 'live_api', ['prasarana'], 'Rapid KL live bus positions (GTFS Realtime)', 'Kedudukan bas Rapid KL secara langsung (GTFS Realtime)',
     'Live vehicle positions for Prasarana buses as a GTFS Realtime protobuf feed, refreshed every 30 seconds. Choose a service with ?category=.',
     'Kedudukan bas Prasarana secara langsung sebagai suapan protobuf GTFS Realtime, dikemas kini setiap 30 saat.',
     'Transportation', [('API: Prasarana %s (protobuf)' % c, '/gtfs-realtime/vehicle-position/prasarana?category=' + c) for c in PRASARANA_RT], 'gtfs_realtime', 'REALTIME', [], None,
     'Categories: %s. Rapid Rail KL has no stable realtime feed yet. Rapid Bus Kuantan and Penang have known trip and route id errors. Useful for arrival tracking, not historical ridership.' % ', '.join(PRASARANA_RT)),
    ('api:gtfs_realtime_mybas', 'live_api', [], 'BAS.MY live bus positions (GTFS Realtime)', 'Kedudukan bas BAS.MY secara langsung (GTFS Realtime)',
     'Live vehicle positions for BAS.MY stage buses as GTFS Realtime protobuf feeds, refreshed every 30 seconds, one feed per city.',
     'Kedudukan bas berperingkat BAS.MY secara langsung sebagai suapan protobuf GTFS Realtime, dikemas kini setiap 30 saat.',
     'Transportation', [('API: BAS.MY %s (protobuf)' % c, '/gtfs-realtime/vehicle-position/mybas-' + c) for c in BAS], 'gtfs_realtime', 'REALTIME', ['STATE'], None,
     'One feed per city (Seremban has a and b). Buses can briefly appear outside the service area because of GPS errors.'),
]
RATE_KEYS = {'weather': 'Weather', 'gtfs_static': 'GTFS Static', 'gtfs_realtime': 'GTFS Realtime', 'data_catalogue': 'Data Catalogue', 'opendosm': 'OpenDOSM'}


def page_text(path):
    for attempt in range(3):
        st, body = curl(DOCS + path, timeout=60)
        if st == 200:
            break
        time.sleep(3 * (attempt + 1))
    if st != 200:
        raise IOError('HTTP %s for %s' % (st, path))
    s = body.decode('utf-8', 'replace')
    m = re.search(r'<main.*?</main>', s, re.S) or re.search(r'<article.*?</article>', s, re.S)
    t = re.sub(r'<script.*?</script>|<style.*?</style>|<nav.*?</nav>', '', m.group(0) if m else s, flags=re.S)
    return html.unescape(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', t))).strip()


def flatten(o, p=''):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from flatten(v, p + k + '.')
    elif isinstance(o, list):
        for v in o[:1]:
            yield from flatten(v, p)
    else:
        yield p[:-1]


def probe_columns(path, cache_dir, log):
    """Column names of one row. The API allows 4 requests per minute, so results are cached and calls spaced."""
    cp = os.path.join(cache_dir, 'probe_%s.json' % re.sub(r'[^a-z0-9]+', '_', path))
    if os.path.exists(cp):
        return json.load(open(cp))
    time.sleep(16)
    st, body = curl('%s%s?limit=1' % (API, path))
    if st != 200:
        log('probe %s: HTTP %s (columns left empty)' % (path, st))
        return []
    try:
        cols = list(dict.fromkeys(flatten(json.loads(body))))
    except ValueError:
        return []
    os.makedirs(cache_dir, exist_ok=True)
    json.dump(cols, open(cp, 'w'))
    return cols


def build_devdocs(ag, infer_keys, cache_dir, log, probe=True):
    texts, failed = {}, []
    for key, path in PAGES.items():
        try:
            texts[key] = page_text(path)
        except Exception as e:
            failed.append('%s: %s' % (path, e))
    if failed:
        log('devdocs: could not read %s' % '; '.join(failed))
    rates = {}
    for k, label in RATE_KEYS.items():
        m = re.search(re.escape(label) + r' (\d+) requests per minute', texts.get('rate', ''))
        rates[k] = int(m.group(1)) if m else None
    # drift check: every endpoint and category we describe must still appear in the docs, and vice versa
    documented = set()
    readable = [k for k in ('weather', 'gtfs_static', 'gtfs_realtime', 'data_catalogue', 'opendosm', 'changelog') if k in texts]
    for k in readable:
        documented |= {re.sub(r'[<?].*', '', u).rstrip('/') for u in re.findall(r'https://api\.data\.gov\.my(/[^\s]*)', texts[k])}
    # the changelog names endpoints as bare paths, for example "/flood-warning for accessing ..."
    documented |= set(re.findall(r'(?<![\w/])(/(?:weather|flood-warning|data-catalogue|opendosm|gtfs-static|gtfs-realtime)[a-z0-9/-]*)', texts.get('changelog', '')))
    ours = {re.sub(r'[?].*', '', p) for s in SPECS for _, p in s[8]}
    unread = {'gtfs_static': '/gtfs-static', 'gtfs_realtime': '/gtfs-realtime', 'weather': '/weather'}
    skip = tuple(v for k, v in unread.items() if k not in texts)  # a page that failed to load cannot confirm its endpoints
    missing = sorted(o for o in ours - documented - {'/data-catalogue', '/opendosm'} if not o.startswith(skip))
    extra = sorted(d for d in documented if d and d not in ours and d not in ('/gtfs-static', '/gtfs-realtime') and '<' not in d and not d.endswith('/')
                   and not any(o.startswith(d + '/') for o in ours))  # generic prefixes such as /gtfs-realtime/vehicle-position
    for cat in PRASARANA_STATIC + PRASARANA_RT:
        if cat not in texts.get('gtfs_static', '') + texts.get('gtfs_realtime', ''):
            missing.append('category ' + cat)
    if missing or extra:
        log('devdocs DRIFT: described here but not in the docs: %s | in the docs but not described here: %s' % (missing or 'none', extra or 'none'))
    out = []
    for rid, kind, codes, ten, tms, den, dms, topic, eps, pagekey, freq, geo, probe_path, extra_cav in SPECS:
        agencies, tier, basis = ag.resolve(codes)
        cols = probe_columns(probe_path, cache_dir, log) if (probe and probe_path) else []
        columns = [{'name': c, 'title': '', 'description': ''} for c in cols]
        keys, geo_inf = infer_keys(columns)
        rate = rates.get(pagekey) if pagekey in rates else rates.get('weather' if pagekey == 'changelog' else None)
        cav = ' '.join(x for x in (
            'No API token needed. Rate limit: %s requests per minute.' % rate if rate else 'No API token needed.',
            QUERY_NOTE if kind == 'api' or (probe_path and 'gtfs' not in rid) else '', extra_cav) if x)
        out.append({
            'kind': kind, 'id': rid, 'title': {'en': ten, 'ms': tms}, 'description': {'en': den, 'ms': dms},
            'category': {'en': topic, 'ms': topic, 'sub': 'Open API' if kind == 'live_api' else 'Developer API'},
            'portals': ['devdocs'], 'agencies': agencies, 'tier': tier, 'tier_basis': basis,
            'access': [{'type': 'api', 'label': l, 'url': API + p} for l, p in eps],
            'pages': [{'portal': 'devdocs', 'url': DOCS + PAGES[pagekey]}],
            'licence': LICENCE, 'frequency': freq, 'geography': geo, 'geography_inferred': [g for g in geo_inf if g not in geo],
            'demography': [], 'coverage': {'begin': None, 'end': None},
            'data_as_of': None, 'last_updated': None, 'next_update': None,
            'columns': columns, 'join_keys': keys, 'methodology': '', 'caveats': cav,
            'related': [], 'see_also': [], 'source_agencies_raw': [c.upper() for c in codes] or ['data.gov.my'],
        })
    log('devdocs: %d API records from %d docs pages; rate limits %s' % (len(out), len(texts), {k: v for k, v in rates.items() if v}))
    return out
