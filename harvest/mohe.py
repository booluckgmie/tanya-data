"""Ministry of Higher Education (MOHE) adapter: the Repositori Digital KPT (an EPrints repository).

https://repositori.mohe.gov.my lists items by year at /view/year/YYYY.html. Two annual series that
students and researchers use are indexed:
  - Statistik Pendidikan Tinggi (higher education statistics), one PDF per year
  - Laporan Tahunan Kementerian Pendidikan Tinggi (the ministry's annual report)
Edition titles, years and PDF links only. The newest statistics editions (2024 onward) are published on
mohe.gov.my, which refuses the harvesting environment, so they are not listed here and the record says so.
Standard library only.
"""
import html, re
from urllib.parse import unquote
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from net import curl

BASE = 'https://repositori.mohe.gov.my'
SERIES = [
    ('mohe:statistik_pendidikan_tinggi', re.compile(r'STATISTIK PENDIDIKAN TINGGI|PERANGKAAN PENDIDIKAN', re.I),
     'Higher Education Statistics (Statistik Pendidikan Tinggi), MOHE', 'Statistik Pendidikan Tinggi (KPT)',
     'Annual statistics on Malaysian higher education from the Ministry of Higher Education: institutions, intake, enrolment and output (graduates) by level of study, with breakdowns by state, gender, citizenship and field of study, one PDF per year.',
     'Statistik tahunan pendidikan tinggi Malaysia daripada Kementerian Pendidikan Tinggi: institusi, pengambilan, enrolmen dan output pelajar mengikut peringkat pengajian.',
     'The 2024 and later editions are published on mohe.gov.my (chapter PDFs, including graduate tracer study tables), which refuses the harvesting environment, so they are not listed here. Edition 93 is labelled 2019 but its file is named for 2018; the file name is shown.'),
    ('mohe:laporan_tahunan_kpt', re.compile(r'LAPORAN TAHUNAN KEMENTERIAN PENDIDIKAN TINGGI', re.I),
     'Annual Report of the Ministry of Higher Education (Laporan Tahunan KPT)', 'Laporan Tahunan Kementerian Pendidikan Tinggi (KPT)',
     'The annual report of the Ministry of Higher Education, one PDF per year.',
     'Laporan tahunan Kementerian Pendidikan Tinggi, satu PDF setiap tahun.', ''),
]


def get(path):
    st, body = curl(BASE + path, timeout=60)
    return st, body.decode('utf-8', 'replace')


def meta(page, name):
    return [html.unescape(x) for x in re.findall(r'<meta name="%s" content="([^"]*)"' % re.escape(name), page)]


def build_mohe(ag, log):
    years = range(2008, date.today().year + 1)

    def year_items(y):
        st, p = get('/view/year/%d.html' % y)
        if st != 200:
            return []
        return [(int(i), html.unescape(re.sub(r'<[^>]+>', '', t)).strip().rstrip('.')) for _, i, t in re.findall(r'<a href="(https://repositori\.mohe\.gov\.my/(\d+)/)"[^>]*>(.*?)</a>', p, re.S)]
    with ThreadPoolExecutor(6) as ex:
        found = sorted({it for items in ex.map(year_items, years) for it in items})
    agencies, tier, basis = ag.resolve(['mohe'])
    out, notes = [], []
    for rid, pat, en, ms, den, dms, cav in SERIES:
        ids = [i for i, t in found if pat.search(t)]

        def item(i):
            st, p = get('/%d/' % i)
            if st != 200:
                return None
            pdf = next((u for u in meta(p, 'DC.identifier') if u.lower().endswith('.pdf')), None)
            yr = (meta(p, 'DC.date') or [''])[0][:4]
            title = (meta(p, 'DC.title') or [''])[0].strip()
            return {'id': i, 'title': title, 'year': int(yr) if yr.isdigit() else None, 'pdf': pdf, 'page': '%s/%d/' % (BASE, i)}
        with ThreadPoolExecutor(6) as ex:
            eds = [e for e in ex.map(item, ids) if e and e['pdf']]
        if not eds:
            notes.append('%s: nothing found' % rid)
            continue
        eds.sort(key=lambda e: (e['year'] or 0, e['id']), reverse=True)
        hist = []
        for e in eds:
            fy = re.findall(r'(?<!\d)(20\d{2})(?!\d)', unquote(e['pdf'].rsplit('/', 1)[-1]))  # decode %20 first: '%2020' is not a year
            note = ' (file name says %s)' % fy[-1] if fy and e['year'] and int(fy[-1]) != e['year'] else ''
            hist.append({'date': None, 'title': '%s%s' % (e['title'].title().replace('Kpt', 'KPT'), note), 'url': e['pdf']})
        ys = [e['year'] for e in eds if e['year']]
        out.append({
            'kind': 'publication', 'id': rid, 'title': {'en': en, 'ms': ms}, 'description': {'en': den, 'ms': dms},
            'category': {'en': 'Education', 'ms': 'Pendidikan', 'sub': 'MOHE repository'},
            'portals': ['mohe'], 'agencies': agencies, 'tier': tier, 'tier_basis': basis,
            'access': [{'type': 'pdf', 'label': h['title'], 'url': h['url']} for h in hist],
            'pages': [{'portal': 'mohe', 'url': eds[0]['page']}, {'portal': 'mohe', 'url': BASE + '/view/year/'}],
            'licence': None, 'frequency': 'YEARLY', 'geography': ['NATIONAL'], 'geography_inferred': [], 'demography': [],
            'coverage': {'begin': min(ys), 'end': max(ys)}, 'data_as_of': None, 'last_updated': None, 'next_update': None,
            'columns': [], 'join_keys': [], 'methodology': '', 'caveats': cav,
            'related': ['dosm:graduates'] if 'statistik' in rid else [], 'see_also': [], 'source_agencies_raw': ['MOHE'],
            'releases': [], 'methodology_docs': [], 'history': hist, 'archive_url': BASE + '/view/year/',
        })
        notes.append('%s: %d editions %d-%d' % (rid, len(eds), min(ys), max(ys)))
    log('mohe: ' + '; '.join(notes))
    return out
