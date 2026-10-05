"""Toll sources: Lembaga Lebuhraya Malaysia (LLM, the Malaysian Highway Authority).

VERIFIED (read directly): LLM's highway directory at https://www.llm.gov.my/awam/highway, with the
highways under construction at /awam/highway_constr. Name, length, opening date and concessionaire
are read from the pages. Contact details are not stored.

NOT READ (identified through web search only): the official toll rate lookup kadartol.llm.gov.my and
two datasets on the old data.gov.my portal. From this environment those hosts answered 503, a reset,
or a 403 firewall block, so their contents were never seen. The records say so and carry only what the
search results stated. Toll rate values themselves are never stored.
Standard library only.
"""
import html, re
from net import curl

BASE = 'https://www.llm.gov.my'
UNREAD = ('Not read by the pipeline: this page was identified through a web search result, and from the harvesting '
          'environment it answered %s. Contents, update date and links are unverified. Open the page to confirm. ')
HIGHWAY_RE = re.compile(r'Nama Lebuh Raya \| (.*?) \| Jarak \| (.*?) \| Tarih Pembukaan \| (.*?) \| Alamat \| (.*?) \| Konsesi \| (.*?) \|')


def text_of(page):
    body = re.sub(r'<script.*?</script>|<style.*?</style>', '', page, flags=re.S)
    t = html.unescape(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' | ', body)))
    return re.sub(r'(\| )+', '| ', t)


def read_list(path):
    """All highways from a paginated LLM list page. Offsets run in steps of 8 until a page adds nothing."""
    seen, offset = {}, 0
    while offset <= 200:
        st, body = curl('%s%s%s' % (BASE, path, '/%d' % offset if offset else ''), timeout=60)
        if st != 200:
            if offset == 0:
                raise IOError('HTTP %s for %s' % (st, path))
            break
        found = HIGHWAY_RE.findall(text_of(body.decode('utf-8', 'replace')))
        new = [f for f in found if f[0] not in seen]
        for f in new:
            seen[f[0]] = f
        if not new:
            break
        offset += 8
    return list(seen.values())


def years_of(rows):
    ys = [int(m.group(0)) for r in rows for m in [re.search(r'(19|20)\d{2}', r[2])] if m]
    return (min(ys), max(ys)) if ys else (None, None)


def base(rid, kind, title_en, title_ms, desc_en, desc_ms, agencies, tier, basis, pages, access, cav, cols=(), cov=(None, None), related=()):
    return {
        'kind': kind, 'id': rid, 'title': {'en': title_en, 'ms': title_ms}, 'description': {'en': desc_en, 'ms': desc_ms},
        'category': {'en': 'Transportation', 'ms': 'Pengangkutan', 'sub': 'Highways and tolls'},
        'portals': ['llm'], 'agencies': agencies, 'tier': tier, 'tier_basis': basis,
        'access': access, 'pages': pages, 'licence': None, 'frequency': 'UNKNOWN',
        'geography': ['NATIONAL'], 'geography_inferred': [], 'demography': [],
        'coverage': {'begin': cov[0], 'end': cov[1]}, 'data_as_of': None, 'last_updated': None, 'next_update': None,
        'columns': [{'name': c, 'title': '', 'description': ''} for c in cols], 'join_keys': [], 'methodology': '', 'caveats': cav,
        'related': list(related), 'see_also': [], 'source_agencies_raw': ['LLM'],
    }


def build_tolls(ag, log):
    out = []
    llm, tier, basis = ag.resolve(['llm'])
    kkr, ktier, kbasis = ag.resolve(['kkr'])
    cols = ['highway name', 'length (km)', 'opening date', 'address', 'concessionaire', 'contact details']
    # --- verified: highway directories
    for slug, rid, en, ms, what in (
            ('/awam/highway', 'llm:highways_operating', 'Operating toll highways in Malaysia: length, opening date and concessionaire (LLM directory)',
             'Lebuh raya beroperasi di Malaysia: panjang, tarikh pembukaan dan konsesi (direktori LLM)', 'operating'),
            ('/awam/highway_constr', 'llm:highways_under_construction', 'Toll highways under construction in Malaysia (LLM directory)',
             'Lebuh raya dalam pembinaan di Malaysia (direktori LLM)', 'under construction')):
        try:
            rows = read_list(slug)
        except Exception as e:
            log('tolls: could not read %s: %s' % (slug, e))
            continue
        if not rows:
            log('tolls: no highways parsed from %s (page layout may have changed)' % slug)
            continue
        cov = years_of(rows)
        names = '; '.join(r[0] for r in rows)
        concs = sorted({r[4] for r in rows})
        desc = ('Directory of the %d tolled highways %s in Malaysia published by the Malaysian Highway Authority (Lembaga Lebuhraya Malaysia, LLM): '
                'name, length, opening date, address and concessionaire (%d concession companies). Highways listed: %s. '
                'This directory does not give toll rates; use the toll rate lookup for those.' % (len(rows), what, len(concs), names))
        out.append(base(rid, 'dataset', en, ms, desc, desc, llm, tier, basis,
                        [{'portal': 'llm', 'url': BASE + slug}], [{'type': 'web', 'label': 'LLM highway directory (web page)', 'url': BASE + slug}],
                        'A web page listing, not a download. Names are as published by LLM, including any typos. Read directly from the LLM page when harvested.',
                        cols, cov, related=['llm:toll_rate_lookup']))
    # --- not read: toll rate lookup and old-portal datasets
    tr_title = 'Toll rates by highway, entry plaza and exit plaza, per vehicle class (LLM toll rate lookup)'
    out.append(base('llm:toll_rate_lookup', 'dashboard', tr_title, 'Kadar tol lebuhraya mengikut plaza masuk dan keluar, bagi setiap kelas kenderaan (carian kadar tol LLM)',
        'The Malaysian Highway Authority toll rate lookup. Choose a highway, an entry plaza and an exit plaza to see the toll by vehicle class, for example North-South Expressway (PLUS) from Simpang Pulai to Juru.',
        'Carian kadar tol Lembaga Lebuhraya Malaysia. Pilih lebuh raya, plaza masuk dan plaza keluar untuk melihat kadar tol mengikut kelas kenderaan.',
        llm, tier, basis, [{'portal': 'llm', 'url': 'http://kadartol.llm.gov.my/'}], [{'type': 'web', 'label': 'LLM toll rate lookup (web tool)', 'url': 'http://kadartol.llm.gov.my/'}],
        UNREAD % 'HTTP 503 (https reset)' + 'Closed-system highways such as the North-South Expressway charge by distance and vehicle class; open-system plazas charge a flat rate per plaza.',
        (), related=['llm:highways_operating']))
    old = 'On the old data.gov.my portal, which is now archived, so the data may be out of date. '
    out.append(base('datagovarchive:toll_rates_current', 'dataset', 'Current toll rates by highway (Senarai Kadar Tol Semasa Mengikut Lebuhraya, archived data.gov.my)',
        'Senarai Kadar Tol Semasa Mengikut Lebuhraya (data.gov.my lama)',
        'A list of current toll rates by highway, published as an open dataset on the old data.gov.my portal by the Ministry of Works / Malaysian Highway Authority.',
        'Senarai kadar tol semasa mengikut lebuhraya, diterbitkan sebagai set data terbuka di portal data.gov.my lama.',
        kkr, ktier, kbasis,
        [{'portal': 'datagovarchive', 'url': 'https://www.data.gov.my/data/ms_MY/dataset/senarai-kadar-tol-semasa-mengikut-lebuhraya/resource/1b88f96c-e60b-49a5-9c7d-ff3ed94b4313'}],
        [{'type': 'web', 'label': 'Dataset page on old data.gov.my', 'url': 'https://www.data.gov.my/data/ms_MY/dataset/senarai-kadar-tol-semasa-mengikut-lebuhraya/resource/1b88f96c-e60b-49a5-9c7d-ff3ed94b4313'}],
        UNREAD % 'HTTP 403 (a site firewall block)' + old + 'Columns, format and licence are not known.', (), related=['llm:toll_rate_lookup']))
    out.append(base('datagovarchive:toll_abolished', 'dataset', 'Abolished toll plazas (Senarai Tol Dimansuhkan, archived data.gov.my)',
        'Senarai Tol Dimansuhkan (data.gov.my lama)',
        'A list of toll plazas that have been abolished: year, abolishment date, highway name, toll plaza, direction, concession company and road number, according to the archived dataset page.',
        'Senarai plaza tol yang telah dimansuhkan: tahun, tarikh pemansuhan, nama lebuh raya, plaza tol, arah, syarikat konsesi dan nombor jalan.',
        kkr, ktier, kbasis,
        [{'portal': 'datagovarchive', 'url': 'https://archive.data.gov.my/data/dataset/senarai-tol-dimansuhkan/resource/52e5586c-8c86-470a-ba26-c13937e8950a'}],
        [{'type': 'web', 'label': 'Dataset page on archive.data.gov.my', 'url': 'https://archive.data.gov.my/data/dataset/senarai-tol-dimansuhkan/resource/52e5586c-8c86-470a-ba26-c13937e8950a'}],
        UNREAD % 'a connection reset' + old + 'The column list in the description comes from the search result text.',
        ('no', 'year', 'abolishment date', 'highway name', 'toll plaza', 'direction', 'concession company', 'road number')))
    log('tolls: %d records (%s read directly; the rest from search results only)' % (len(out), sum(1 for r in out if r['id'].startswith('llm:highways'))))
    return out
