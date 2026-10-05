"""Bank Negara Malaysia adapter: the BNM Open API (API Kijang) specification.

BNM publishes a machine-readable spec per statistical table at
https://api.bnm.gov.my/api/specification/ (categories -> tags -> tag spec). One
registry record is built per tag (a table such as "1.1 : Reserve Money").

Metadata only. The "latest" endpoint of each table is read once, for its
last_updated stamp and the period of its newest row, never to store values.
Standard library only.
"""
import json, os, re, urllib.parse
from concurrent.futures import ThreadPoolExecutor
from net import curl_json

SPEC = 'https://api.bnm.gov.my/api/specification/'
API = 'https://api.bnm.gov.my/public'
PORTAL = 'https://apikijangportal.bnm.gov.my'
ACCEPT = 'application/vnd.BNM.API.v1+json'
HEADER_NOTE = 'Requests to the BNM Open API must send the header "Accept: %s".' % ACCEPT


def get(url, cache_path=None, accept=False):
    if cache_path and os.path.exists(cache_path):
        return json.load(open(cache_path, encoding='utf-8'))
    data = curl_json(url, {'Accept': ACCEPT})
    if cache_path:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        json.dump(data, open(cache_path, 'w', encoding='utf-8'), ensure_ascii=False)
    return data


def slug(s):
    return re.sub(r'[^a-z0-9]+', '_', s.lower()).strip('_')


def title_of(tag):
    m = re.match(r'^([\w.]+(?: \d[\w.]*)?) : (.+)$', tag)
    return '%s (BNM table %s)' % (m.group(2), m.group(1)) if m else tag


def frequency_of(cols, specs):
    names = {c['name'] for c in cols}
    paths = ' '.join(s['uri'] for s in specs)
    if names & {'year_month', 'month_dt', 'month'} or '/month/' in paths:
        return 'MONTHLY'
    if 'quarter' in names or '/quarter/' in paths:
        return 'QUARTERLY'
    if 'date' in names or '/date/' in paths:
        return 'DAILY'
    if names & {'year_dt', 'year'}:
        return 'YEARLY'
    return 'UNKNOWN'


def child_columns(spec):
    try:
        data = spec['responses']['200']['content']['application/json']['schema']['properties']['data']
    except (KeyError, TypeError):
        return []
    return [{'name': k, 'title': (v.get('description') or '').strip(), 'description': (v.get('description') or '').strip()}
            for k, v in (data.get('children') or {}).items()]


def fetch_tag(args):
    cat, tag, cache_dir = args
    try:
        j = get(SPEC + 'tag?name=' + urllib.parse.quote(tag), os.path.join(cache_dir, 'tag_%s.json' % slug(tag)))
    except Exception as e:
        return cat, tag, None, None, str(e)
    specs = list((j.get('spec') or {}).values())
    latest = next((s for s in specs if not s['parameters']['path'] and s.get('summary', '').lower() == 'latest'),
                  next((s for s in specs if not s['parameters']['path']), None))
    meta = {}
    if latest:
        try:
            r = get(API + '/' + latest['uri'].lstrip('/'))  # not cached: freshness is the point
            rows = r.get('data')
            row = rows[0] if isinstance(rows, list) and rows else (rows if isinstance(rows, dict) else {})
            meta = {'last_updated': (r.get('meta') or {}).get('last_updated', ''), 'row': row}
        except Exception:
            meta = {}
    return cat, tag, specs, meta, None


def period_of(row):
    for k in ('date', 'year_month', 'month_dt', 'year_dt', 'year'):
        v = row.get(k) if isinstance(row, dict) else None
        if v and re.match(r'^\d{4}', str(v)):
            return str(v)
    return None


def build_bnm(ag, infer_keys, cache_dir, log):
    cats = get(SPEC + 'categories', os.path.join(cache_dir, 'categories.json'))['categories']
    jobs = [(c['name'], t, cache_dir) for c in cats if c.get('enabled') for t in c['tags']]
    with ThreadPoolExecutor(6) as ex:
        results = list(ex.map(fetch_tag, jobs))
    agencies, tier, basis = ag.resolve(['bnm'])
    out, failed, seen = [], [], set()
    for cat, tag, specs, meta, err in results:
        if not specs:
            failed.append(tag + (': ' + err if err else ': no endpoints'))
            continue
        rid = 'bnm:' + slug(tag)
        if rid in seen:
            continue
        seen.add(rid)
        cols = []
        for s in specs:
            for c in child_columns(s):
                if c['name'] not in [x['name'] for x in cols]:
                    cols.append(c)
        keys, geo_inf = infer_keys(cols)
        desc = next((s['description'] for s in specs if s.get('description')), '').strip()
        latest = next((s for s in specs if not s['parameters']['path'] and s.get('summary', '').lower() == 'latest'),
                      next((s for s in specs if not s['parameters']['path']), None))
        access = []
        if latest:
            access.append({'type': 'api', 'label': 'API: ' + latest.get('summary', 'latest'), 'url': API + '/' + latest['uri'].lstrip('/')})
        access += [{'type': 'api', 'label': 'API: %s (template)' % s.get('summary', ''), 'url': API + '/' + s['uri'].lstrip('/')}
                   for s in specs if s is not latest]
        freq = frequency_of(cols, specs)
        period = period_of((meta or {}).get('row'))
        lu = (meta or {}).get('last_updated', '')[:10] or None
        out.append({
            'kind': 'dataset', 'id': rid,
            'title': {'en': title_of(tag), 'ms': title_of(tag)},
            'description': {'en': desc, 'ms': ''},
            'category': {'en': cat, 'ms': cat, 'sub': 'BNM Open API'},
            'portals': ['bnmapi'], 'agencies': agencies, 'tier': tier, 'tier_basis': basis,
            'access': access,
            'pages': [{'portal': 'bnmapi', 'url': PORTAL + '/openapi?category=' + urllib.parse.quote(cat)}],
            'licence': None, 'frequency': freq, 'frequency_inferred': True,
            'geography': ['NATIONAL'], 'geography_inferred': [g for g in geo_inf if g != 'NATIONAL'],
            'demography': [], 'coverage': {'begin': None, 'end': int(period[:4]) if period else None},
            'data_as_of': period[:10] if period and len(period) >= 10 else period, 'last_updated': lu, 'next_update': None,
            'columns': cols, 'join_keys': keys, 'methodology': '', 'caveats': HEADER_NOTE,
            'related': [], 'see_also': [], 'source_agencies_raw': ['BNM'],
            'endpoints': [s['uri'] for s in specs],
        })
    log('BNM: %d tables from %d categories; %d failed%s' % (len(out), len(cats), len(failed), (': ' + '; '.join(failed[:5])) if failed else ''))
    return out
