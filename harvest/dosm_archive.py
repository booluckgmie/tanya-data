"""DOSM release archive adapter: the legacy DOSM portal's per-series release archives.

https://www.dosm.gov.my/portal-main/release-archive/<release> lists every edition of a statistical
release with its release date. The OpenDOSM publication feed (datagovmy-meta) only goes back to about
2018, while the legacy portal reaches back to 2011 and covers series OpenDOSM does not carry (the
population census, environment compendium, social indicators, small area statistics and more).

The adapter reads the portal's release index (alphabet pages plus every subtheme page), fetches each
series' archive, and either
  - enriches the matching registry record with the full edition history, or
  - adds a new record for the series.
Matching is deliberately strict: an alias list, an exact normalised title, or a unique near match.
A duplicate record is better than attaching a history to the wrong series.

Edition titles, dates and page links only. No report contents or figures are stored. The one text
field read from a release page is the first descriptive sentence of its "Overview".
Standard library only.
"""
import html, re, string
from concurrent.futures import ThreadPoolExecutor
from statistics import median
from datetime import date
from net import curl

BASE = 'https://www.dosm.gov.my'
ROW = re.compile(r'<a[^>]*href="(/portal-main/release-content/[^"#]+)"[^>]*>\s*(\d{2})\.(\d{2})\.(\d{4})\s*-\s*(.*?)</a>', re.S)
STOP = {'archive', 'malaysia', 'statistics', 'statistic', 'report', 'survey', 'the', 'of', 'in', 'and', 'by', 'for', 'a', 'on', 'selected', '&'}
# Cleaned archive heading (regex) -> existing registry record.
ALIASES = [
    (r'^labour force$', 'pub:labour_force'), (r'^labour market review$', 'pub:labour_market_review'), (r'^employment$', 'pub:employment'),
    (r'^labour productivity$', 'pub:labour_productivity'), (r'^graduates$', 'pub:graduates'), (r'^informal sector', 'pub:informal_sector_workforce'),
    (r'^salaries & wages$', 'pub:salaries_wages'), (r'^employee wages statistics$', 'pub:formal_sector_wages'),
    (r'^industrial production$', 'pub:industrial_production_index'), (r'^external trade indices$', 'pub:trade_indices'),
    (r'^malaysia external trade statistics$', 'pub:external_trade'), (r'^malaysian economic indicators', 'pub:malaysian_economic_indicators'),
    (r'^statistics on ict use and access', 'pub:ict_use_access'), (r'^micro, small & medium enterprises', 'pub:micro_small_medium_enterprises'),
    (r'^malaysian economic statistics review$', 'pub:economic_statistics_review'), (r'^regional tourism satellite account sabah', 'pub:tourism_satellite_account_for_sabah'),
    (r'^advance gross domestic product', 'pub:advance_gross_domestic_product'), (r'^gross domestic product income approach', 'pub:gross_domestic_product_income_approach'),
    (r'^statistics on income inequality', 'pub:income_inequality'), (r'^statistics on household expenditure', 'pub:household_expenditure'),
    (r'^statistics on poverty', 'pub:poverty'), (r'^malaysia social statistics review', 'pub:social_statistics_review'),
    (r'^petroleum and natural gas$', 'pub:mining_of_petroleum_natural_gas'), (r'^malaysia human development index', 'pub:human_development_index'),
    (r'^living cost$', 'pub:cost_of_living'), (r'^women empowerment', 'pub:women_empowerment'), (r'^sustainable development goals$', 'pub:sustainable_development_goals_sdgs'),
]
SPECIAL = {  # cleaned heading -> hand-written record (series with no OpenDOSM counterpart that need better text)
    'job vacancies advertised online': {
        'id': 'dosm:job_market_insights',
        'en': 'Job Vacancies Advertised Online: Job Market Insights (DOSM big data analytics)',
        'ms': 'Kekosongan Jawatan Diiklankan Dalam Talian: Job Market Insights (analitik data raya DOSM)',
        'desc_en': 'Quarterly DOSM releases based on job offerings advertised online through major private recruitment platforms, with key information on job offerings by major occupational group and economic activity. The official statistical counterpart to commercial job-market reports.',
        'desc_ms': 'Keluaran suku tahunan DOSM berdasarkan tawaran pekerjaan yang diiklankan dalam talian melalui platform pengambilan pekerja swasta utama, mengikut kumpulan pekerjaan dan aktiviti ekonomi.',
        'related': ['pub:labour_market_review', 'pub:labour_force'],
    },
}
THEME_CATEGORY = {'Labour Market Information': 'Labour Market', 'Labour Market': 'Labour Market', 'Population & Demography': 'Population',
                  'Population & Demographic': 'Population', 'Social Indicators': 'Social', 'Household Income & Expenditure': 'Household Income & Expenditure',
                  'Small Area Statistics': 'Small Area Statistics', 'Environment': 'Environment', 'External Sector': 'Trade and Investment',
                  'Prices': 'Prices', 'National Accounts': 'National Accounts', 'Agriculture': 'Agriculture', 'Agriculture Census': 'Agriculture',
                  'Construction': 'Construction', 'Manufacturing': 'Manufacturing', 'Services': 'Services', 'Mining & Quarrying': 'Mining',
                  'Economics Indicator': 'Economy', 'Economy': 'Economy'}


def fetch(path):
    for attempt in range(3):
        st, body = curl(BASE + path, timeout=60)
        if st == 200:
            return body.decode('utf-8', 'replace')
    raise IOError('HTTP %s for %s' % (st, path))


def clean(s):
    return html.unescape(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', s))).strip()


def norm(t):
    return frozenset(w for w in re.sub(r'[^a-z0-9 ]+', ' ', t.lower()).split() if w not in STOP)


def heading_of(page, fallback):
    m = re.search(r'<h3>([^<]*?)\s*Archive\s*</h3>', page)
    return re.sub(r'\s+', ' ', m.group(1)).strip() if m else fallback


def editions(page):
    return [{'date': '%s-%s-%s' % (y, m, d), 'title': clean(t), 'url': BASE + h} for h, d, m, y, t in ROW.findall(page)]


def ref_year(e):
    ys = [int(y) for y in re.findall(r'\b(19\d{2}|20\d{2})\b', e['title'])]
    return min(ys) if ys else int(e['date'][:4])


def frequency_of(eds):
    ds = sorted(date.fromisoformat(e['date']) for e in eds)
    if len(ds) < 3:
        return 'UNKNOWN'
    if (ds[-1] - ds[0]).days < 400:
        return 'ONE-OFF'  # a batch released together, such as one report per state
    gap = median((b - a).days for a, b in zip(ds, ds[1:]) if (b - a).days > 0) if len(set(ds)) > 1 else 0
    return 'MONTHLY' if gap <= 40 else 'QUARTERLY' if gap <= 110 else 'HALF-YEARLY' if gap <= 220 else 'YEARLY'


def discover(log):
    """-> {latest release slug: {'title', 'themes'}} from the alphabet index and every subtheme page."""
    def letter(L):
        try:
            return fetch('/portal-main/release-alphabet?alphabet=' + L)
        except IOError:
            return ''
    with ThreadPoolExecutor(6) as ex:
        pages = list(ex.map(letter, string.ascii_uppercase))
    series, subs = {}, []
    for p in pages:
        for kind, slug, inner in re.findall(r'<a href="/portal-main/(release-content|release-subthemes)/([^"#?]+)"[^>]*class="theme_alphabet"[^>]*>(.*?)</a>', p, re.S):
            if kind == 'release-content':
                series.setdefault(slug, {'title': clean(inner), 'themes': []})
            else:
                subs.append((slug, clean(inner)))

    def sub(x):
        slug, theme = x
        try:
            p = fetch('/portal-main/release-subthemes/' + slug)
        except IOError:
            return []
        out = []
        for h, inner in re.findall(r'href="/portal-main/release-content/([^"#?]+)"[^>]*>(.*?)</a>', p, re.S):
            t = re.split(r'\s+Latest update', clean(inner))[0].strip()
            if t:
                out.append((h, t, theme))
        return out
    with ThreadPoolExecutor(6) as ex:
        for rows in ex.map(sub, subs):
            for slug, t, theme in rows:
                s = series.setdefault(slug, {'title': t, 'themes': []})
                if theme not in s['themes']:
                    s['themes'].append(theme)
    log('dosm_archive: %d release entries from %d letters and %d subthemes' % (len(series), len(pages), len(subs)))
    return series


def overview_of(slug):
    """First descriptive sentence(s) of a release's Overview, stopping before any sentence with a headline figure."""
    try:
        page = fetch('/portal-main/release-content/' + slug)
    except IOError:
        return None
    body = re.sub(r'<script.*?</script>|<style.*?</style>', '', page, flags=re.S)
    t = clean(re.sub(r'</?(?:p|br|li|div|h\d)[^>]*>', ' | ', body))
    m = re.search(r'\bOverview\b\s*\|?\s*(.{60,900})', t)
    if not m:
        return None
    seg = re.sub(r'\s*\|\s*', ' ', m.group(1))
    out = []
    for s in re.split(r'(?<=[.!?])\s+', seg):
        if re.search(r'\d+(?:\.\d+)?\s*(?:per cent|%|million|billion|thousand)', s):
            break
        out.append(s)
        if sum(len(x) for x in out) > 260:
            break
    text = re.sub(r'^(?:[A-Z0-9][A-Z0-9,&:()\-./ ]{7,}?\s+)(?=[A-Z][a-z])', '', ' '.join(out).strip())  # drop a leading ALL-CAPS heading
    junk = re.compile(r'click here|subscribe|newsletter|infographic|publications|download|share this|latest release|upcoming release|^data\b', re.I)
    if len(text) < 50 or junk.search(text) or not re.match(r'[A-Z][a-z]', text):
        return None
    return text


TITLE_OVERRIDE = {'social': 'Social Statistics Bulletin and Monthly Statistical Bulletin'}


def clean_edition_title(t):
    t = re.sub(r'\b(?:19|20)\d{2}\b', '', t)
    t = re.sub(r'\b(?:First|Second|Third|Fourth)\s+Quarter(?:\s+of)?\b|\bQ[1-4]\b|\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\b', '', t, flags=re.I)
    t = re.sub(r',?\s*\bMalaysia\b', '', t)
    return re.sub(r'\s+', ' ', re.sub(r'[,\-:\s]+$', '', re.sub(r'^[,\-:\s]+', '', t))).strip(' ,-')


def descriptive_title(heading, eds):
    """A short archive heading such as "Education" becomes the cleaned latest edition title when that adds context."""
    if heading.lower() in TITLE_OVERRIDE:
        return TITLE_OVERRIDE[heading.lower()]
    if len(heading.split()) > 3:
        return heading
    cand = clean_edition_title(eds[0]['title'])
    hw = {w for w in re.sub(r'[^a-z0-9 ]+', ' ', heading.lower()).split() if w not in STOP}
    cw = set(re.sub(r'[^a-z0-9 ]+', ' ', cand.lower()).split())
    return cand if hw and hw <= cw and len(cand.split()) > len(heading.split()) else heading


def slugify(s):
    return re.sub(r'[^a-z0-9]+', '_', s.lower()).strip('_')


def enrich(records, ag, log):
    by_id = {r['id']: r for r in records}
    pubs = [r for r in records if r['kind'] == 'publication']
    exact = {}
    for r in pubs:
        exact.setdefault(norm(r['title']['en']), []).append(r)
    try:
        cards = discover(log)
    except Exception as e:
        log('dosm_archive: could not read the release index: %s' % e)
        return []

    def archive(slug):
        try:
            page = fetch('/portal-main/release-archive/' + slug)
        except IOError:
            return slug, None, []
        return slug, heading_of(page, cards[slug]['title']), editions(page)
    with ThreadPoolExecutor(8) as ex:
        results = list(ex.map(archive, cards))
    groups = {}  # one series per distinct set of editions
    for slug, heading, eds in results:
        if eds:
            groups.setdefault(tuple(sorted(e['url'] for e in eds)), []).append((slug, heading, eds))
    merged = {}  # archives that share a heading are one series (for example one list per language or state)
    for members in groups.values():
        for slug, heading, eds in members:
            m = merged.setdefault(heading.lower().strip(), {'members': [], 'eds': {}})
            m['members'].append((slug, heading, eds))
            for e in eds:
                m['eds'][(e['date'], e['title'])] = e
    groups = {k: [(v['members'][0][0], v['members'][0][1], list(v['eds'].values()))] for k, v in merged.items()}
    agencies, tier, basis = ag.resolve(['dosm'])
    added, enriched, skipped, ambiguous = [], 0, 0, []
    todo_new = []
    for members in groups.values():
        slug, heading, eds = members[0]
        eds = sorted(eds, key=lambda e: e['date'], reverse=True)
        key = heading.lower().strip()
        target = None
        if key in SPECIAL:
            sid = SPECIAL[key]['id']
            target = by_id.get(sid)
        else:
            for pat, rid in ALIASES:
                if re.search(pat, key):
                    target = by_id.get(rid)
                    break
            if target is None:
                hits = exact.get(norm(heading), [])
                if len(hits) == 1:
                    target = hits[0]
                elif len(hits) > 1:
                    ambiguous.append(heading)
        if target is not None and len(eds) < 2:
            skipped += 1
            continue
        if target is not None:
            attach(target, eds, slug)
            enriched += 1
        else:
            todo_new.append((slug, heading, eds, members))
    # new records: read each series' overview sentence
    with ThreadPoolExecutor(6) as ex:
        overviews = list(ex.map(lambda t: None if t[1].lower().strip() in SPECIAL else overview_of(t[0]), todo_new))
    used = set(by_id)
    for (slug, heading, eds, members), ov in zip(todo_new, overviews):
        key = heading.lower().strip()
        sp = SPECIAL.get(key)
        rid = sp['id'] if sp else 'dosm:' + slugify(descriptive_title(heading, eds))
        n = 2
        while rid in used and not sp:
            rid, n = 'dosm:%s_%d' % (slugify(descriptive_title(heading, eds)), n), n + 1
        used.add(rid)
        themes = []
        for m in members:
            themes += cards.get(m[0], {}).get('themes', [])
        for m in merged.get(key, {}).get('members', []):
            themes += cards.get(m[0], {}).get('themes', [])
        theme = next((THEME_CATEGORY[t] for t in themes if t in THEME_CATEGORY), None) or (themes[0] if themes else 'Statistics')
        freq = frequency_of(eds)
        title_en = sp['en'] if sp else descriptive_title(heading, eds)
        desc_en = sp['desc_en'] if sp else (ov or '%s: a DOSM statistical release series (%s), with %d editions listed from %d to %d.' % (title_en, theme, len(eds), min(ref_year(e) for e in eds), int(eds[0]['date'][:4])))
        rec = {
            'kind': 'publication', 'id': rid, 'title': {'en': title_en, 'ms': sp['ms'] if sp else heading},
            'description': {'en': desc_en, 'ms': sp['desc_ms'] if sp else ''},
            'category': {'en': theme, 'ms': theme, 'sub': 'DOSM release archive'},
            'portals': ['dosm'], 'agencies': agencies, 'tier': tier, 'tier_basis': basis,
            'access': [], 'pages': [{'portal': 'dosm', 'url': eds[0]['url']}],
            'licence': None, 'frequency': freq, 'geography': [], 'geography_inferred': [], 'demography': [],
            'coverage': {'begin': None, 'end': int(eds[0]['date'][:4])}, 'data_as_of': None, 'last_updated': eds[0]['date'], 'next_update': None,
            'columns': [], 'join_keys': [], 'methodology': '',
            'caveats': 'Edition titles and layouts change over time. The release pages hold the reports and tables; this record stores only edition titles, dates and links.',
            'related': (sp or {}).get('related', []), 'see_also': [], 'source_agencies_raw': ['DOSM'], 'releases': [], 'methodology_docs': [],
        }
        by_id[rid] = rec
        attach(rec, eds, slug)
        added.append(rec)
    log('dosm_archive: %d series with archives; %d enriched existing records, %d new records, %d skipped (single edition)%s'
        % (len(groups), enriched, len(added), skipped, ('; ambiguous title matches made new records: ' + ', '.join(ambiguous[:6])) if ambiguous else ''))
    return added


def attach(target, eds, slug):
    eds = sorted(eds, key=lambda e: e['date'], reverse=True)
    first = min(ref_year(e) for e in eds)
    archive = BASE + '/portal-main/release-archive/' + slug
    target['history'] = eds
    target['archive_url'] = archive
    if not any(p['url'] == archive for p in target['pages']):
        target['pages'].append({'portal': 'dosm', 'url': archive})  # so the link checker verifies it
    cov = target['coverage']
    cov['begin'] = min(x for x in (cov.get('begin'), first) if x)
