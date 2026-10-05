#!/usr/bin/env python3
"""Build dist/index.html: the Tanya Data discovery page, with the registry inlined.

    python harvest/build_app.py

Reads registry/registry.json (run harvest.py, then verify_links.py first) and
app/index.template.html. Records whose official portal page returned 404/410 are
withheld; dead file links are dropped from a record instead of hiding it.

Standard library only.
"""
import json, math, os, re
from datetime import date, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEAD = (404, 410)
PORTAL_NAME = {'datagovmy': 'data.gov.my', 'opendosm': 'OpenDOSM', 'kkmnow': 'KKMNOW', 'databnm': 'data.bnm.gov.my',
               'bnmapi': 'BNM Open API', 'mohgithub': 'MOH on GitHub', 'electiondata': 'ElectionData.MY'}
TYPE_LABEL = {'csv': 'CSV', 'parquet': 'Parquet', 'api': 'API', 'pdf': 'PDF', 'excel': 'Excel'}
GEO_RANK = ['DISTRICT', 'DUN', 'PARLIMEN', 'STATE', 'NATIONAL']


def clip(s, n):
    s = (s or '').strip()
    return s if len(s) <= n else s[:n].rstrip()


def as_of(s):
    """'2026-08' -> 2026-08-31, '2024' -> 2024-12-31, '2024-12-31' as is."""
    if not s:
        return None
    m = re.match(r'^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?', s)
    if not m:
        return None
    y, mo, d = int(m.group(1)), m.group(2), m.group(3)
    if d:
        return date(y, int(mo), int(d))
    nxt = date(y + (mo is None or int(mo) == 12), 1 if mo is None or int(mo) == 12 else int(mo) + 1, 1)
    return date.fromordinal(nxt.toordinal() - 1)


def fit(d, today):
    """Mean of the five meters the page shows (history, freshness, detail, documentation, schedule)."""
    b, e = d['b'], d['e']
    span = (e - b + 1) if (b and e) else None
    history = min(1, span / 25) if span else .1
    da = as_of(d['da'])
    lag = (today - da).days if da else None
    if lag is not None:
        fresh = 1 if lag <= 60 else .7 if lag <= 200 else .4 if lag <= 500 else .15
    else:
        fresh = (.7 if e >= 2025 else .4 if e >= 2023 else .15) if e else .2
    finest = next((g for g in GEO_RANK if g in d['geo']), None)
    detail = {'DISTRICT': 1, 'DUN': 1, 'PARLIMEN': 1, 'STATE': .7, 'NATIONAL': .35}.get(finest, .1)
    doc = (.4 if d['meth'] else 0) + (.2 if d['hascav'] else 0) + (.2 if len(d['fields']) >= 4 else .1) + (.2 if d['d'] else 0)
    nu = as_of(d['nu'])
    over = (today - nu).days if nu else None
    sched = .4 if over is None else 1 if over <= 0 else .5 if over <= 60 else .15
    return round(100 * (history + fresh + detail + doc + sched) / 5)


def build(reg):
    recs = reg['records']
    today = datetime.strptime(reg['harvested_at'][:10], '%Y-%m-%d').date()
    by_id = {r['id']: r for r in recs}
    neighbours = {r['id']: [] for r in recs}
    for r in recs:
        for o in r.get('related', []) + r.get('see_also_ids', []):
            if o in by_id and o != r['id']:
                for a, b in ((r['id'], o), (o, r['id'])):
                    if b not in neighbours[a]:
                        neighbours[a].append(b)
    withheld, out = [], []
    for r in recs:
        v = r.get('verified') or {}
        if v.get('state') == 'page_missing':
            withheld.append(r['id'])
            continue
        dead = {c['url'] for c in v.get('checks', []) if c['status'] in DEAD}
        lk = []
        pages = [p for p in r['pages'] if p['url'] not in dead]
        if r['kind'] == 'publication':
            pages = pages[:1]  # newest edition whose page still resolves
        for p in pages:
            label = 'API documentation' if r['kind'] == 'live_api' else 'Open on %s' % PORTAL_NAME.get(p['portal'], p['portal'])
            lk.append([label if r['kind'] != 'publication' else 'Open latest edition on OpenDOSM', p['url']])
        files = [a for a in r['access'] if a['url'] not in dead and 'YYYY' not in a['url'] and '{' not in a['url']]
        if r['kind'] in ('dataset', 'live_api') and r['access'] and not files and any(c['role'] == 'file' for c in v.get('checks', [])) and dead:
            withheld.append(r['id'])  # listed by the agency but every file or endpoint is gone or empty
            continue
        if r['kind'] == 'dataset':
            lk += [[a.get('label') or TYPE_LABEL.get(a['type'], a['type'].upper()), a['url']] for a in files[:4]]
        elif r['kind'] == 'live_api':
            lk = [['API endpoint', a['url']] for a in files] + lk
        elif r['kind'] == 'dashboard':
            lk += [['Chart data (Parquet)', a['url']] for a in files[:1]]
        raw = r.get('source_agencies_raw') or [a['code'].upper() for a in r['agencies']]
        geo = list(dict.fromkeys(r['geography'] + r['geography_inferred']))
        c = r['coverage']
        d = {
            'id': r['id'], 'kind': r['kind'],
            't': r['title']['en'], 'tm': r['title']['ms'] or r['title']['en'],
            'd': clip(r['description']['en'], 700), 'dm': clip(r['description']['ms'], 700),
            'cat': r['category']['en'], 'sub': r['category'].get('sub', ''), 'catm': r['category']['ms'],
            'freq': r['frequency'], 'geo': geo, 'geoinf': r['geography_inferred'], 'demo': r['demography'],
            'b': c['begin'], 'e': c['end'], 'src': raw, 'agn': [a['name'] for a in r['agencies']],
            'fields': [{'n': f['name'], 't': f['title'], 'd': clip(f['description'], 200)} for f in r['columns']],
            'keys': r['join_keys'], 'meth': clip(r['methodology'], 600),
            'cav': clip(r['caveats'], 420), 'hascav': bool(r['caveats']),
            'lu': r['last_updated'] if r['last_updated'] and len(r['last_updated']) == 10 else None,
            'nu': r['next_update'] if r['next_update'] and len(r['next_update']) == 10 else None,
            'da': r['data_as_of'], 'tier': r['tier'], 'tw': r['tier_basis'],
            'lic': (r['licence'] or {}).get('name'),
            'pub': (r.get('publisher') or {}).get('name'), 'vc': (v.get('checked_at') or '')[:10] or None,
            'lk': lk,
            'rl': [by_id[o]['title']['en'] for o in neighbours[r['id']][:6]],
        }
        if r['frequency'] == 'REALTIME':
            d['da'] = today.isoformat()  # a live feed is current by definition
        if r['kind'] == 'publication':
            d['res'] = [[a['type'], a['label'], a['url']] for a in files]
            d['rn'] = len(r['releases'])
            d['md'] = [[m['label'], m['url']] for m in r.get('methodology_docs', [])]
            d['da'] = r['last_updated']
        d['fit'] = fit(d, today)
        out.append(d)
    return out, withheld


def main():
    reg = json.load(open(os.path.join(ROOT, 'registry', 'registry.json'), encoding='utf-8'))
    cat, withheld = build(reg)
    tpl = open(os.path.join(ROOT, 'app', 'index.template.html'), encoding='utf-8').read()
    checked = max((r.get('verified', {}).get('checked_at', '') for r in reg['records']), default='')[:10] or 'not yet'
    commit = reg['sources'][0].get('commit', '')[:8]
    meta = {'commit': commit, 'harvested': reg['harvested_at'][:10], 'checked': checked, 'withheld': len(withheld)}
    golden = re.search(r'const GOLDEN = \[(.*?)\n\];', tpl, re.S).group(1)
    n_all = len(re.findall(r'^\[".*?",\[', golden, re.M))
    n_gap = len(re.findall(r'^\[".*?",\[\]\]', golden, re.M))
    safe = lambda o: json.dumps(o, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    html = (tpl.replace('__CATALOGUE_JSON__', safe(cat)).replace('__META_JSON__', safe(meta))
               .replace('__NBENCH__', str(n_all - n_gap)).replace('__NGAP__', str(n_gap)))
    os.makedirs(os.path.join(ROOT, 'dist'), exist_ok=True)
    out = os.path.join(ROOT, 'dist', 'index.html')
    open(out, 'w', encoding='utf-8').write(html)
    print('wrote %s: %d records (%d withheld), %.0f KB' % (out, len(cat), len(withheld), len(html) / 1024))
    if withheld:
        print('withheld:', ', '.join(withheld))


if __name__ == '__main__':
    main()
