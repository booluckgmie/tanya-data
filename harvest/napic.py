"""NAPIC adapter: the National Property Information Centre (JPPH) publications portal.

Four sections (market, stock, status, indices) each link to report series under
https://napic.jpph.gov.my/archives/<series>. One registry record per series. A series page
shows the files of its latest edition(s) and a year filter listing every year available, which
gives the coverage. The open transaction data page is an embedded Tableau dashboard and is
recorded as a dashboard. Metadata only: file titles and links, never file contents.
Standard library only.
"""
import html, re, urllib.parse
from datetime import date
from concurrent.futures import ThreadPoolExecutor
from net import curl

BASE = 'https://napic.jpph.gov.my'
SECTIONS = ['pasaran-harta-tanah', 'inventori-harta-tanah', 'status-harta-tanah', 'indeks-harga-dan-sewaan-harta-tanah']
MENU = set(SECTIONS) | {'inventori-harta-tanah2'}
TITLES = {  # slug: (English, Malay as published). English is a translation of the Malay name.
    'laporan-pasaran-harta-tahunan': ('Annual Property Market Report', 'Laporan Pasaran Harta Tahunan'),
    'laporan-pasaran-harta-separuh-pertama-wilayah': ('Half-Year Property Market Report by Region', 'Laporan Pasaran Harta Separuh Pertama / Wilayah'),
    'jadual-data-transaksi-harta-tanah': ('Property Transaction Data Tables by State', 'Jadual Data Transaksi Harta Tanah'),
    'harga-kediaman-sukuantahunan-terkini': ('Latest Quarterly and Annual Residential Prices', 'Harga Kediaman Sukuan/Tahunan Terkini'),
    'Transaksi RM30 Juta': ('Transactions of RM30 Million and Above', 'Transaksi RM30 Juta'),
    'transaksi-tanah-ladang': ('Plantation Land Transactions', 'Transaksi Tanah Ladang'),
    'laporan-status-harta-tanah': ('Property Market Status Report and Tables', 'Laporan Status Harta Tanah'),
    'laporan-jadual-penghunian-dan-ketersediaan-ruang-bangunan-perdagangan-cbsa': ('Occupancy and Availability of Commercial Building Space (CBSA)', 'Laporan Jadual Penghunian dan Ketersediaan Ruang Bangunan Perdagangan (CBSA)'),
    'indeks-harga-rumah-malaysia': ('Malaysian House Price Index (MHPI)', 'Indeks Harga Rumah Malaysia'),
    'indeks-sewaan-pejabat-binaan-khas': ('Purpose-Built Office Rental Index', 'Indeks Sewaan Pejabat Binaan Khas'),
    'indeks-sewaan-pusat-beli-belah-sc-ri': ('Shopping Centre Rental Index (SC-RI)', 'Indeks Sewaan Pusat Beli-Belah (SC-RI)'),
    'indeks-harga-pangsapuri-khidmat-ihpk': ('Serviced Apartment Price Index (IHPK)', 'Indeks Harga Pangsapuri Khidmat (IHPK)'),
    'indeks-harga-kedai-lembah-klang-ihk-lk': ('Klang Valley Shophouse Price Index (IHK-LK)', 'Indeks Harga Kedai Lembah Klang (IHK-LK)'),
    'inventori-harta-tanah': ('Property Stock Report and Tables', 'Laporan Stok Harta Tanah'),
}
TOPIC = {'pasaran-harta-tanah': 'Property market', 'inventori-harta-tanah': 'Property stock',
         'status-harta-tanah': 'Property status', 'indeks-harga-dan-sewaan-harta-tanah': 'Price and rental indices'}
STATES = ('johor', 'kedah', 'kelantan', 'melaka', 'negeri sembilan', 'pahang', 'perak', 'perlis', 'pulau pinang', 'selangor',
          'terengganu', 'sabah', 'sarawak', 'kuala lumpur', 'putrajaya', 'labuan', 'wilayah', 'region')
FILE_RE = re.compile(r'\.(pdf|xlsx?|csv|zip|docx?)$', re.I)
TYPE = {'pdf': 'pdf', 'xls': 'excel', 'xlsx': 'excel', 'csv': 'csv', 'zip': 'zip', 'doc': 'word', 'docx': 'word'}
PERIOD = re.compile(r'\b(?:(Q[1-4])|(H[12]))\s*(\d{4})P?\b|\b(20\d{2})P?\b')  # trailing P marks provisional figures
DASHBOARD_URL = BASE + '/ms/data-transaksi?category=36&id=241'


def fetch(url):
    st, body = curl(url.replace(' ', '%20'), timeout=60)
    if st != 200:
        raise IOError('HTTP %s for %s' % (st, url))
    return body.decode('utf-8', 'replace')


def clean(s):
    return html.unescape(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', s))).strip()


def period_end(label):
    """'Q2 2026' / 'H1 2026' -> 2026-06-30; '2025' -> 2025-12-31."""
    m = PERIOD.search(label or '')
    if not m:
        return None
    if m.group(1):
        q, y = int(m.group(1)[1]), m.group(3)
        return '%s-%s' % (y, ['03-31', '06-30', '09-30', '12-31'][q - 1])
    if m.group(2):
        return '%s-%s' % (m.group(3), '06-30' if m.group(2) == 'H1' else '12-31')
    return '%s-12-31' % m.group(4)


def discover(section_pages):
    slugs = {}
    for sec, page in section_pages.items():
        for h in re.findall(r'href="https://napic\.jpph\.gov\.my/archives/([^"#?]+)"', page):
            if h not in MENU:
                slugs.setdefault(urllib.parse.unquote(h), sec)
    slugs.setdefault('inventori-harta-tanah', 'inventori-harta-tanah')  # its files sit on the section page
    return slugs


def parse_series(page):
    years = sorted({int(y) for y in re.findall(r'<option value="(\d{4})"', page)})
    files, ebooks = [], []
    for row in re.findall(r'<tr>.*?</tr>', page, re.S):
        for href, text in re.findall(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', row, re.S):
            t = clean(text)
            if FILE_RE.search(urllib.parse.urlparse(href).path):
                files.append((t, href, clean(row)))
            elif 'myebook' in href:
                ebooks.append((t or 'e-book', href))
    if not files:  # section pages list files as plain anchors
        for href, text in re.findall(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', page, re.S):
            if FILE_RE.search(urllib.parse.urlparse(href).path) and 'storage/app/media' in href:
                files.append((clean(text), href, clean(text)))
    return years, files, ebooks


def build_napic(ag, infer_keys, log):
    sec_pages = {}
    for sec in SECTIONS:
        sec_pages[sec] = fetch('%s/ms/archives/%s' % (BASE, sec))
    slugs = discover(sec_pages)
    page_url = lambda slug, sec: ('%s/ms/archives/%s' % (BASE, sec)) if slug == 'inventori-harta-tanah' else '%s/archives/%s' % (BASE, urllib.parse.quote(slug))

    def one(item):
        slug, sec = item
        try:
            return slug, sec, fetch(page_url(slug, sec)), None
        except Exception as e:
            return slug, sec, None, str(e)

    with ThreadPoolExecutor(5) as ex:
        results = list(ex.map(one, slugs.items()))
    agencies, tier, basis = ag.resolve(['napic'])
    out, failed = [], []
    for slug, sec, page, err in results:
        if page is None:
            failed.append('%s: %s' % (slug, err))
            continue
        years, files, ebooks = parse_series(page)
        if not files:
            failed.append('%s: no files listed' % slug)
            continue
        en, ms = TITLES.get(slug, (None, None))
        if not en:
            ms = en = slug.replace('-', ' ').title()
        labels = [f[0] + ' ' + f[2] for f in files]
        ends = [e for e in (period_end(f[0]) or period_end(f[2]) for f in files) if e]  # title first, then the year column
        latest = min(max(ends), date.today().isoformat()) if ends else None  # never later than today
        freq = 'QUARTERLY' if any(re.search(r'\bQ[1-4]\b', l) for l in labels) else \
               'HALF-YEARLY' if any(re.search(r'\bH[12]\b', l) for l in labels) else 'YEARLY'
        text = ' '.join(f[0] for f in files).lower()
        geo = ['STATE'] if any(s in text for s in STATES) else []
        access = [{'type': TYPE.get(FILE_RE.search(urllib.parse.urlparse(h).path).group(1).lower(), 'file'), 'label': t, 'url': h.replace(' ', '%20')}
                  for t, h, _ in files[:10]]
        access += [{'type': 'web', 'label': t, 'url': h} for t, h in ebooks[:2]]
        sample = '; '.join(f[0] for f in files[:3])
        out.append({
            'kind': 'publication', 'id': 'napic:' + re.sub(r'[^a-z0-9]+', '_', slug.lower()).strip('_'),
            'title': {'en': en, 'ms': ms},
            'description': {'en': '%s, published by the National Property Information Centre (NAPIC), JPPH. Latest files include: %s.' % (en, sample),
                            'ms': '%s, diterbitkan oleh Pusat Maklumat Harta Tanah Negara (NAPIC), JPPH. Fail terkini termasuk: %s.' % (ms, sample)},
            'category': {'en': TOPIC[sec], 'ms': TOPIC[sec], 'sub': 'NAPIC publication'},
            'portals': ['napic'], 'agencies': agencies, 'tier': tier, 'tier_basis': basis,
            'access': access, 'pages': [{'portal': 'napic', 'url': page_url(slug, sec)}],
            'licence': None, 'frequency': freq, 'frequency_inferred': True,
            'geography': [], 'geography_inferred': geo, 'demography': [],
            'coverage': {'begin': years[0] if years else None, 'end': years[-1] if years else None},
            'data_as_of': latest, 'last_updated': None, 'next_update': None,
            'columns': [], 'join_keys': [], 'methodology': '',
            'caveats': 'The page lists the latest edition; earlier years are behind its year filter (coverage years are taken from that filter). English title is a translation of the Malay name. Files are PDF and Excel tables.',
            'related': [], 'see_also': [], 'source_agencies_raw': ['NAPIC'],
            'releases': [], 'methodology_docs': [],
        })
    # open transaction data: an embedded Tableau Public dashboard
    page = fetch(DASHBOARD_URL)
    tab = re.search(r'https://public\.tableau\.com/views/[^"\s]+', page)
    out.append({
        'kind': 'dashboard', 'id': 'napic:data_transaksi_terbuka',
        'title': {'en': 'Residential, Commercial and Industrial Property Transaction Data (open data dashboard)', 'ms': 'Data Transaksi Terbuka: Data Transaksi Harta Kediaman, Komersial dan Industri'},
        'description': {'en': 'NAPIC open transaction data for residential, commercial and industrial property, shown as an interactive dashboard.', 'ms': 'Data transaksi terbuka NAPIC bagi harta kediaman, komersial dan industri, dipaparkan sebagai papan pemuka interaktif.'},
        'category': {'en': 'Property market', 'ms': 'Pasaran harta tanah', 'sub': 'NAPIC open data'},
        'portals': ['napic'], 'agencies': agencies, 'tier': tier, 'tier_basis': basis,
        'access': ([{'type': 'web', 'label': 'Tableau dashboard', 'url': html.unescape(tab.group(0)).split('&')[0]}] if tab else []),
        'pages': [{'portal': 'napic', 'url': DASHBOARD_URL}],
        'licence': None, 'frequency': 'UNKNOWN', 'geography': [], 'geography_inferred': [], 'demography': [],
        'coverage': {'begin': None, 'end': None}, 'data_as_of': None, 'last_updated': None, 'next_update': None,
        'columns': [], 'join_keys': [], 'methodology': '',
        'caveats': 'The dashboard is embedded from Tableau Public. Its view name suggests a May 2024 publication; check the dashboard for its current date range.',
        'related': [], 'see_also': [], 'source_agencies_raw': ['NAPIC'],
    })
    log('NAPIC: %d series from %d found, plus the open transaction dashboard; %d failed%s' % (len(out) - 1, len(slugs), len(failed), (': ' + '; '.join(failed[:4])) if failed else ''))
    return out
