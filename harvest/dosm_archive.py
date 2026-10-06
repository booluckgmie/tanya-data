"""DOSM release archive adapter: the legacy DOSM portal's per-series release archives.

https://www.dosm.gov.my/portal-main/release-archive/<release> lists every edition of a statistical
release with its release date. The OpenDOSM publication feed (datagovmy-meta) only goes back to about
2018, so the labour and wage series are enriched here with their longer edition history, for example
the Salaries & Wages Survey Report back to 2014 and the labour force releases back to 2014. A series
that OpenDOSM does not carry (online job vacancies) is added as a new record.

Edition titles, dates and page links only: no report contents or figures are read or stored.
Standard library only.
"""
import html, re
from net import curl

BASE = 'https://www.dosm.gov.my'
SUBTHEME = '/portal-main/release-subthemes/labour-market-information'
# Series card title on the labour market information page -> existing registry record (None = add a new record).
SERIES = {
    'Labour Force': 'pub:labour_force', 'Labour Market Review': 'pub:labour_market_review', 'Employment': 'pub:employment',
    'Labour Productivity': 'pub:labour_productivity', 'Graduates': 'pub:graduates', 'Informal Sector': 'pub:informal_sector_workforce',
    'Salaries & Wages': 'pub:salaries_wages', 'Employee Wages Statistics': 'pub:formal_sector_wages',
    'Job Vacancies Advertised Online': None,
}
NEW = {
    'Job Vacancies Advertised Online': {
        'id': 'dosm:job_market_insights',
        'en': 'Job Vacancies Advertised Online: Job Market Insights (DOSM big data analytics)',
        'ms': 'Kekosongan Jawatan Diiklankan Dalam Talian: Job Market Insights (analitik data raya DOSM)',
        'desc_en': 'Quarterly DOSM releases based on job offerings advertised online through major private recruitment platforms, with key information on job offerings by major occupational group and economic activity. The official statistical counterpart to commercial job-market reports.',
        'desc_ms': 'Keluaran suku tahunan DOSM berdasarkan tawaran pekerjaan yang diiklankan dalam talian melalui platform pengambilan pekerja swasta utama, mengikut kumpulan pekerjaan dan aktiviti ekonomi.',
        'freq': 'QUARTERLY',
    },
}
ROW = re.compile(r'<a[^>]*href="(/portal-main/release-content/[^"#]+)"[^>]*>\s*(\d{2})\.(\d{2})\.(\d{4})\s*-\s*(.*?)</a>', re.S)


def fetch(path):
    st, body = curl(BASE + path, timeout=60)
    if st != 200:
        raise IOError('HTTP %s for %s' % (st, path))
    return body.decode('utf-8', 'replace')


def clean(s):
    return html.unescape(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', s))).strip()


def series_cards(page):
    """-> {card title: latest release slug}"""
    out = {}
    for href, inner in re.findall(r'href="(/portal-main/release-content/[^"#?]+)"[^>]*>(.*?)</a>', page, re.S):
        t = clean(inner)
        title = re.split(r'\s+Latest update', t)[0].strip()
        if title and title not in out:
            out[title] = href.rsplit('/', 1)[1]
    return out


def editions(page):
    eds = []
    for href, d, m, y, title in ROW.findall(page):
        eds.append({'date': '%s-%s-%s' % (y, m, d), 'title': clean(title), 'url': BASE + href})
    return eds


def ref_year(e):
    ys = [int(y) for y in re.findall(r'\b(19\d{2}|20\d{2})\b', e['title'])]
    return min(ys) if ys else int(e['date'][:4])


def enrich(records, ag, log):
    by_id = {r['id']: r for r in records}
    try:
        cards = series_cards(fetch(SUBTHEME))
    except Exception as e:
        log('dosm_archive: could not read the labour market information page: %s' % e)
        return []
    added, report = [], []
    for title, slug in cards.items():
        if title not in SERIES:
            continue
        try:
            eds = editions(fetch('/portal-main/release-archive/' + slug))
        except Exception as e:
            report.append('%s: %s' % (title, e))
            continue
        if len(eds) < 2:
            report.append('%s: archive lists %d edition(s), skipped' % (title, len(eds)))
            continue
        eds.sort(key=lambda e: e['date'], reverse=True)
        first = min(ref_year(e) for e in eds)
        archive = BASE + '/portal-main/release-archive/' + slug
        target = by_id.get(SERIES[title]) if SERIES[title] else None
        if SERIES[title] and not target:
            report.append('%s: registry record %s not found' % (title, SERIES[title]))
            continue
        if target is None:
            spec = NEW[title]
            agencies, tier, basis = ag.resolve(['dosm'])
            target = {
                'kind': 'publication', 'id': spec['id'], 'title': {'en': spec['en'], 'ms': spec['ms']},
                'description': {'en': spec['desc_en'], 'ms': spec['desc_ms']},
                'category': {'en': 'Labour Market', 'ms': 'Pasaran Buruh', 'sub': 'DOSM release'},
                'portals': ['dosm'], 'agencies': agencies, 'tier': tier, 'tier_basis': basis,
                'access': [], 'pages': [{'portal': 'dosm', 'url': BASE + '/portal-main/release-content/' + slug}],
                'licence': None, 'frequency': spec['freq'], 'geography': ['NATIONAL'], 'geography_inferred': [], 'demography': [],
                'coverage': {'begin': first, 'end': int(eds[0]['date'][:4])}, 'data_as_of': None, 'last_updated': eds[0]['date'],
                'next_update': None, 'columns': [], 'join_keys': [], 'methodology': '', 'caveats': 'Edition titles changed over time (for example "and My Job Profile" in 2024-25).',
                'related': ['pub:labour_market_review', 'pub:labour_force'], 'see_also': [], 'source_agencies_raw': ['DOSM'],
                'releases': [], 'methodology_docs': [],
            }
            by_id[spec['id']] = target
            added.append(target)
        target['history'] = eds
        target['archive_url'] = archive
        if not any(p['url'] == archive for p in target['pages']):
            target['pages'].append({'portal': 'dosm', 'url': archive})  # so the link checker verifies it
        cov = target['coverage']
        cov['begin'] = min(x for x in (cov.get('begin'), first) if x)
        report.append('%s: %d editions from %d' % (title, len(eds), first))
    log('dosm_archive: ' + '; '.join(report))
    return added
