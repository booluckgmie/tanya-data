#!/usr/bin/env python3
"""Harvest official-data metadata into the Tanya Data registry.

Reads the public datagovmy-meta repository (data.gov.my, OpenDOSM, KKMNOW and
data.bnm.gov.my metadata) and probes a short list of official live APIs. Writes
registry/registry.json. Metadata only: no dataset values are copied.

    python harvest/harvest.py                 # clones/updates .cache/datagovmy-meta
    python harvest/harvest.py --meta PATH     # use an existing checkout

Standard library only.
"""
import argparse, glob, json, os, re, subprocess, sys, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bnm, devdocs, electiondata, moh, napic, sharecode
from collections import defaultdict
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
META_REPO = 'https://github.com/data-gov-my/datagovmy-meta.git'
PORTALS = {
    'datagovmy': ('data.gov.my', 'https://data.gov.my'),
    'opendosm': ('OpenDOSM', 'https://open.dosm.gov.my'),
    'kkmnow': ('KKMNOW', 'https://data.moh.gov.my'),
    'databnm': ('data.bnm.gov.my', 'https://data.bnm.gov.my'),
    'bnmapi': ('BNM Open API', 'https://apikijangportal.bnm.gov.my'),
    'mohgithub': ('MOH on GitHub', 'https://github.com/MoH-Malaysia'),
    'electiondata': ('ElectionData.MY', 'https://electiondata.my'),
    'devdocs': ('data.gov.my API docs', 'https://developer.data.gov.my'),
}
# Portal that owns a dashboard/publication when the metadata names no agency.
PORTAL_AGENCY = {'opendosm': 'dosm', 'kkmnow': 'moh', 'databnm': 'bnm'}
CATALOGUE_LICENCE = {
    'name': 'Creative Commons Attribution 4.0 International (CC BY 4.0)',
    'url': 'https://creativecommons.org/licenses/by/4.0/',
    'basis': 'stated on the portal catalogue page',
}
# DOSM publication_type -> technical-note document type (pub-dosm/documentation).
DOC_ALIAS = {'cpi': 'cpi', 'ppi': 'ppi', 'gdp': 'gdp', 'gdp_sa': 'gdp', 'bop': 'bop', 'iip': 'bop',
             'trade': 'trade', 'labour': 'labour', 'lfs': 'labour', 'lfs_informal': 'labour',
             'wrt': 'iowrt', 'ipi': 'ipi', 'indicators': 'mei', 'crime': 'crime', 'hies': 'hies',
             'demography': 'population'}
# (column name pattern, canonical join key) used for join keys and inferred geography.
KEY_RULES = [
    (r'^date$', 'date'), (r'^year$', 'year'), (r'^state$', 'state'), (r'^district$', 'district'),
    (r'^parlimen$|^parliament$', 'parliament'), (r'^dun$', 'DUN'), (r'^sex$', 'sex'),
    (r'^age$', 'age'), (r'^age_group$', 'age group'), (r'^ethnic', 'ethnicity'),
    (r'^strata$|^urban', 'urban/rural'), (r'^country$', 'country'), (r'^sector$', 'sector'),
    (r'^division$|^mcoicop', 'MCOICOP division'),
    (r'^seat$', 'seat'), (r'^year_month$|^month_dt$|^week$', 'date'), (r'^year_dt$', 'year'),
]
GEO_FROM_KEY = {'state': 'STATE', 'district': 'DISTRICT', 'parliament': 'PARLIMEN', 'DUN': 'DUN'}


def log(*a):
    print(*a, file=sys.stderr)


def load(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def day(s):
    """'2026-08-14 12:30' -> '2026-08-14'; '2026-08' stays; junk -> None."""
    if not s or not re.match(r'^\d{4}', str(s)):
        return None
    return str(s)[:10]


def year(v):
    """Catalogue years arrive as int, '2010' or junk; return an int or None."""
    m = re.match(r'^\s*(\d{4})', str(v)) if v is not None else None
    return int(m.group(1)) if m else None


def md_links(text):
    return [{'label': m.group(1), 'url': m.group(2)} for m in re.finditer(r'\[([^\]]+)\]\((https?://[^)\s]+)\)', text or '')]


def ensure_meta(path):
    if path:
        return path
    dest = os.path.join(ROOT, '.cache', 'datagovmy-meta')
    if os.path.isdir(os.path.join(dest, '.git')):
        subprocess.run(['git', '-C', dest, 'pull', '-q', '--ff-only'], check=True)
    else:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        subprocess.run(['git', 'clone', '-q', '--depth', '1', META_REPO, dest], check=True)
    return dest


class Agencies:
    """Agency code -> name, and the written tier policy (registry/tiers.json)."""

    def __init__(self, meta):
        names = load(os.path.join(meta, 'i18n', 'en-GB', 'agencies.json'))['translation']
        self.names = {k.lower(): v['full'] for k, v in names.items()}
        self.abbr = {k.lower(): v['abbr'] for k, v in names.items()}
        self.names.setdefault('dosm', 'Department of Statistics Malaysia')
        self.policy = load(os.path.join(ROOT, 'registry', 'tiers.json'))
        self.unknown = set()

    def tier(self, code):
        p = self.policy
        if code in p['agency_tier']:
            return p['agency_tier'][code], 'named in tier policy'
        if code in p['tier3_non_government']:
            return 3, 'originator is a company or international body'
        if code in self.names:
            return p['default_tier'], 'government agency, default tier'
        self.unknown.add(code)
        return 3, 'agency code not recognised'

    def resolve(self, codes):
        """-> (agency list, weakest-link tier, basis)."""
        out, tiers = [], []
        for c in codes:
            c = c.lower()
            t, why = self.tier(c)
            out.append({'code': c, 'name': self.names.get(c, c.upper()), 'tier': t})
            tiers.append((t, why))
        if not tiers:
            return [], self.policy['default_tier'], 'agency not stated in metadata; portal default (needs review)'
        worst = max(tiers, key=lambda x: x[0])
        return out, worst[0], 'weakest of listed sources: ' + worst[1]


def infer_keys(columns):
    keys, geo = [], []
    for c in columns:
        for pat, key in KEY_RULES:
            if re.search(pat, c['name'].lower()):
                if key not in keys:
                    keys.append(key)
                break
    for k in keys:
        if k in GEO_FROM_KEY:
            geo.append(GEO_FROM_KEY[k])
    return sorted(keys, key=str.lower), geo


def build_datasets(meta, ag):
    out = []
    for f in sorted(glob.glob(os.path.join(meta, 'data-catalogue', '*.json'))):
        j = load(f)
        slug = os.path.basename(f)[:-5]
        sites = [s['site'] for s in j['site_category']]
        cat = j['site_category'][0]
        cols = [{'name': c['name'], 'title': c.get('title_en', ''), 'description': c.get('description_en', '')} for c in j['fields']]
        keys, geo_inf = infer_keys(cols)
        geo = list(j.get('geography') or [])
        inferred = [g for g in geo_inf if g not in geo]
        agencies, tier, basis = ag.resolve(j.get('data_source') or [])
        access = []
        if j.get('link_csv'):
            access.append({'type': 'csv', 'url': j['link_csv']})
        if j.get('link_parquet'):
            access.append({'type': 'parquet', 'url': j['link_parquet']})
        access.append({'type': 'api', 'url': 'https://api.data.gov.my/data-catalogue?id=' + slug})
        pages = [{'portal': s, 'url': '%s/data-catalogue/%s' % (PORTALS[s][1], slug)} for s in sites if s in PORTALS]
        nxt = day(j.get('next_update'))
        out.append({
            'kind': 'dataset', 'id': slug,
            'title': {'en': j['title_en'], 'ms': j['title_ms']},
            'description': {'en': j['description_en'], 'ms': j['description_ms']},
            'category': {'en': cat['category_en'], 'ms': cat['category_ms'], 'sub': cat.get('subcategory_en', '')},
            'portals': sites, 'agencies': agencies, 'tier': tier, 'tier_basis': basis,
            'access': access, 'pages': pages, 'licence': CATALOGUE_LICENCE,
            'frequency': j['frequency'], 'geography': geo, 'geography_inferred': inferred,
            'demography': j.get('demography') or [],
            'coverage': {'begin': year(j.get('dataset_begin')), 'end': year(j.get('dataset_end'))},
            'data_as_of': day(j.get('data_as_of')), 'last_updated': day(j.get('last_updated')),
            'next_update': nxt,
            'columns': cols, 'join_keys': keys,
            'methodology': j.get('methodology_en') or '', 'caveats': j.get('caveat_en') or '',
            'related': [r['id'] for r in (j.get('related_datasets') or [])],
            'see_also': md_links(j.get('publication_en')),
            'source_agencies_raw': j.get('data_source') or [],
        })
    return out


def parse_ref_years(title, release_date):
    m = re.match(r'^\[([^\]]*)\]', title)
    ys = [int(y) for y in re.findall(r'(?:19|20)\d{2}', m.group(1))] if m else []
    if not ys and release_date:
        ys = [int(release_date[:4])]
    return (min(ys), max(ys)) if ys else (None, None)


def build_publications(meta, ag):
    docs = defaultdict(list)
    for f in glob.glob(os.path.join(meta, 'pub-dosm', 'documentation', '*.json')):
        d = load(f)
        for r in d['en']['resources']:
            docs[d['publication_type']].append({'label': d['en']['title'].strip() + ': ' + r['resource_name'],
                                                'url': r['resource_link'], 'type': r['resource_type']})
    fam = defaultdict(list)
    for f in glob.glob(os.path.join(meta, 'pub-dosm', 'publications', '*.json')):
        j = load(f)
        title = re.sub(r'^\[[^\]]*\]\s*', '', j['en']['title']).strip()
        title = re.sub(r'\s*:\s*\d{4}(?:\s*-\s*\d{4})?$', '', title)  # 'Impact of Floods: 2021' joins its series
        fam[title].append(j)  # DOSM renamed publication_type codes over time; the title is the stable key
    agencies, tier, basis = ag.resolve(['dosm'])
    out = []
    for title, rels in sorted(fam.items()):
        rels.sort(key=lambda r: (r['release_date'], r['publication']), reverse=True)
        latest = rels[0]
        yrs = [parse_ref_years(r['en']['title'], r['release_date']) for r in rels]
        b = min(y[0] for y in yrs if y[0]); e = max(y[1] for y in yrs if y[1])
        geo = sorted({g for r in rels for g in r.get('geography', [])})
        ptypes = list(dict.fromkeys(r['publication_type'] for r in rels))
        ptype = latest['publication_type']
        slug = re.sub(r'[^a-z0-9]+', '_', title.lower()).strip('_')
        res = [{'type': r['resource_type'], 'label': r['resource_name'], 'url': r['resource_link']}
               for r in latest['en']['resources']]
        doc_type = next((DOC_ALIAS[t] for t in [ptype] + ptypes if t in DOC_ALIAS), None)
        if 'productivity' in title.lower():
            doc_type = 'productivity'
        if 'services producer' in title.lower():
            doc_type = 'sppi'
        ms = latest['bm']
        out.append({
            'kind': 'publication', 'id': 'pub:' + slug,
            'title': {'en': title, 'ms': re.sub(r'^\[[^\]]*\]\s*', '', ms['title']).strip()},
            'description': {'en': latest['en']['description'], 'ms': ms['description']},
            'category': {'en': latest['en']['publication_type_title'], 'ms': ms['publication_type_title'], 'sub': 'DOSM publication'},
            'portals': ['opendosm'], 'agencies': agencies, 'tier': tier, 'tier_basis': basis,
            'access': res,
            # newest editions first; a series stays reachable if the newest page is missing
            'pages': [{'portal': 'opendosm', 'url': 'https://open.dosm.gov.my/publications/' + r['publication']} for r in rels[:3]],
            'licence': None,
            'frequency': (latest.get('frequency') or 'UNKNOWN').replace('_', '-'), 'geography': geo,
            'geography_inferred': [], 'demography': sorted({d for r in rels for d in r.get('demography', [])}),
            'coverage': {'begin': b, 'end': e},
            'data_as_of': None, 'last_updated': latest['release_date'], 'next_update': None,
            'columns': [], 'join_keys': [], 'methodology': '', 'caveats': '',
            'related': [], 'see_also': [],
            'methodology_docs': docs.get(doc_type, []),
            'releases': [[r['publication'], r['release_date']] for r in rels],
            'publication_type': ptypes,
        })
    return out


# Portal page headers that say nothing about the content.
TITLE_OVERRIDE = {'kawasanku_admin': 'KawasanKu: area profile (administrative areas)',
                  'kawasanku_electoral': 'KawasanKu: area profile (electoral areas)'}


def build_dashboards(meta, ag):
    tr = {}
    for lang in ('en-GB', 'ms-MY'):
        for f in glob.glob(os.path.join(meta, 'i18n', lang, 'dashboard-*.json')):
            j = load(f)
            tr[(lang, j.get('route'))] = j.get('translation') or {}
            tr[(lang, 'file:' + os.path.basename(f)[len('dashboard-'):-5])] = j.get('translation') or {}
    out, skipped, seen_routes = [], [], set()
    for f in sorted(glob.glob(os.path.join(meta, 'dashboards', '*.json')) + glob.glob(os.path.join(meta, 'explorers', '*.json'))):
        j = load(f)
        explorer = '/explorers/' in f.replace('\\', '/')
        route = (j.get('route') or '').split(',')[0]
        en, ms = tr.get(('en-GB', route)), tr.get(('ms-MY', route))
        if not en:  # i18n file with a null route: match on its filename
            fk = 'file:' + route.rstrip('/').split('/')[-1]
            en, ms = tr.get(('en-GB', fk)), tr.get(('ms-MY', fk))
        name = j.get('dashboard_name') or os.path.basename(f)[:-5]
        if route in seen_routes:  # the same page listed as dashboard and explorer
            continue
        seen_routes.add(route)
        if not en or not en.get('header'):
            skipped.append(name)
            continue
        sites = [s for s in j.get('sites', []) if s in PORTALS]
        sources, cols = [], []
        charts = j.get('charts') or {}
        tables = j.get('tables') or {}
        for ch in charts.values():
            if ch.get('chart_source'):
                sources.append(ch['chart_source'])
            v = ch.get('variables') or {}
            for k in ('x', 'y', 'columns'):
                for c in ([v[k]] if isinstance(v.get(k), str) else v.get(k) or []):
                    if isinstance(c, str) and c not in [x['name'] for x in cols]:
                        cols.append({'name': c, 'title': '', 'description': ''})
        for t in tables.values():
            if t.get('source'):
                sources.append(t['source'])
        sources = list(dict.fromkeys(sources))
        keys, geo = infer_keys(cols)
        codes = [PORTAL_AGENCY[s] for s in sites if s in PORTAL_AGENCY]
        agencies, tier, basis = ag.resolve(list(dict.fromkeys(codes)))
        en = dict(en, header=TITLE_OVERRIDE.get(name, en['header']))
        title_ms = TITLE_OVERRIDE.get(name) or (ms or {}).get('header') or en['header']
        out.append({
            'kind': 'dashboard', 'id': 'dash:' + name,
            'title': {'en': en['header'], 'ms': title_ms},
            'description': {'en': en.get('description', ''), 'ms': (ms or {}).get('description', '')},
            'category': {'en': 'Explorer' if explorer else 'Dashboard', 'ms': 'Penjelajah' if explorer else 'Papan pemuka', 'sub': ''},
            'portals': sites, 'agencies': agencies, 'tier': tier, 'tier_basis': basis,
            'access': [{'type': 'parquet', 'url': u} for u in sources if u.endswith('.parquet')],
            'pages': [{'portal': s, 'url': PORTALS[s][1] + route} for s in sites],
            'licence': None,
            'frequency': 'UNKNOWN', 'geography': [], 'geography_inferred': geo, 'demography': [],
            'coverage': {'begin': None, 'end': None},
            'data_as_of': day((next(iter(charts.values()), {}) or {}).get('data_as_of') or j.get('data_last_updated')),
            'last_updated': day(j.get('data_last_updated')), 'next_update': day(j.get('data_next_update')),
            'columns': cols, 'join_keys': keys, 'methodology': '', 'caveats': '',
            'related': [], 'see_also': [], 'route': route,
        })
    log('dashboards skipped (no portal page title in i18n): %s' % ', '.join(skipped))
    return out


def link_graph(records):
    """Add 'see_also' ids that point at other registry records (dataset -> publication/dashboard)."""
    by_pub = defaultdict(list)
    for r in records:
        if r['kind'] == 'publication':
            for rid, _ in r['releases']:
                by_pub[rid].append(r['id'])
    by_route = {r['route']: r['id'] for r in records if r['kind'] == 'dashboard' and r.get('route')}
    for r in records:
        ids = []
        for l in r.get('see_also', []):
            m = re.search(r'/publications/([\w.-]+)', l['url'])
            if m and by_pub.get(m.group(1)):
                ids += by_pub[m.group(1)]
            m = re.search(r'(/dashboard/[\w-]+)', l['url'])
            if m and m.group(1) in by_route:
                ids.append(by_route[m.group(1)])
        r['see_also_ids'] = list(dict.fromkeys(ids))
        r.pop('see_also', None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--meta', help='path to an existing datagovmy-meta checkout')
    ap.add_argument('--no-probe', action='store_true', help='skip live API probes')
    ap.add_argument('--moh-dir', default=os.path.join(ROOT, '.cache', 'moh'), help='where the MoH-Malaysia repositories are cloned')
    ap.add_argument('--sharecode-dir', default=os.path.join(ROOT, '.cache', 'sharecode'), help='where booluckgmie/sharecode is cloned (into a sharecode/ subfolder)')
    ap.add_argument('--skip', nargs='*', default=[], choices=['bnm', 'moh', 'electiondata', 'sharecode', 'napic', 'devdocs'], help='leave a source out')
    ap.add_argument('--out', default=os.path.join(ROOT, 'registry', 'registry.json'))
    a = ap.parse_args()
    meta = ensure_meta(a.meta)
    ag = Agencies(meta)
    recs = build_datasets(meta, ag) + build_publications(meta, ag) + build_dashboards(meta, ag)
    if 'devdocs' not in a.skip:
        recs += devdocs.build_devdocs(ag, infer_keys, os.path.join(ROOT, '.cache', 'devdocs'), log, not a.no_probe)
    if 'bnm' not in a.skip:
        recs += bnm.build_bnm(ag, infer_keys, os.path.join(ROOT, '.cache', 'bnm'), log)
    if 'electiondata' not in a.skip:
        recs += electiondata.build_electiondata(ag, infer_keys, os.path.join(ROOT, '.cache', 'electiondata'), log)
    if 'napic' not in a.skip:
        recs += napic.build_napic(ag, infer_keys, log)
    if 'sharecode' not in a.skip:
        recs += sharecode.build_sharecode(infer_keys, a.sharecode_dir, log)
    if 'moh' not in a.skip:
        recs += moh.build_moh(ag, infer_keys, a.moh_dir, log)
    link_graph(recs)
    try:
        commit = subprocess.run(['git', '-C', meta, 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()
    except Exception:
        commit = ''
    counts = defaultdict(int)
    for r in recs:
        counts[r['kind']] += 1
    reg = {
        'schema': '0.1', 'harvested_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%MZ'),
        'sources': [{'name': 'datagovmy-meta', 'url': META_REPO.replace('.git', ''), 'commit': commit},
                    {'name': 'data.gov.my developer docs (Open API)', 'url': 'https://developer.data.gov.my/'},
                    {'name': 'BNM Open API specification', 'url': 'https://api.bnm.gov.my/api/specification/categories'},
                    {'name': 'MoH-Malaysia GitHub repositories', 'url': 'https://github.com/MoH-Malaysia'},
                    {'name': 'ElectionData.MY data catalogue (independent project)', 'url': 'https://electiondata.my/data-catalogue/'},
                    {'name': 'NAPIC publications portal (JPPH)', 'url': 'https://napic.jpph.gov.my/ms/archives/pasaran-harta-tanah'},
                    {'name': 'booluckgmie/sharecode archive (allowlisted folders only)', 'url': 'https://github.com/booluckgmie/sharecode'}],
        'counts': dict(counts), 'records': recs,
    }
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, 'w', encoding='utf-8') as f:
        json.dump(reg, f, ensure_ascii=False, separators=(',', ':'))
    log('wrote %s: %s' % (a.out, dict(counts)))
    if ag.unknown:
        log('agency codes without a name (add to tiers.json or fix upstream): %s' % ', '.join(sorted(ag.unknown)))


if __name__ == '__main__':
    main()
