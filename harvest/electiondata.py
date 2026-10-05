"""ElectionData.MY adapter: the data catalogue at https://electiondata.my/data-catalogue/.

ElectionData.MY is an independent open-data project, not an agency portal. Its methodology
states the data is compiled from results published by the Election Commission of Malaysia
(SPR). The registry therefore names SPR as the source agency but records the independent
publisher, and sets the reliability tier to 3 (verify against spr.gov.my) rather than
letting it default to the agency tier.

Each dataset page embeds its metadata as serialised Astro island props. Only metadata
fields are kept: the page also embeds a query-widget token and sample rows, which are
never stored. Standard library only.
"""
import html, json, os, re
from concurrent.futures import ThreadPoolExecutor
from net import curl

BASE = 'https://electiondata.my'
LICENCE = {'name': 'Creative Commons Zero (CC0), dedicated to the public domain',
           'url': 'https://creativecommons.org/publicdomain/zero/1.0/',
           'basis': 'stated on the dataset page'}
KEEP = ('title', 'data_as_of', 'last_updated', 'next_update', 'description', 'methodology', 'download', 'fields', 'catalogue_type')
PUBLISHER = {'name': 'ElectionData.MY (independent project)', 'official': False,
             'note': 'Compiled from Election Commission of Malaysia results. Not published by the agency.'}
CAVEAT = ('Compiled and published by the independent ElectionData.MY project from Election Commission of Malaysia '
          'results, not by the Commission itself. Check headline figures against spr.gov.my before citing.')


def decode(v):
    """Astro serialises props as [0, value] (plain) and [1, [items]] (array)."""
    if isinstance(v, list) and len(v) == 2 and v[0] in (0, 1):
        return decode(v[1]) if v[0] == 0 else [decode(x) for x in v[1]]
    if isinstance(v, dict):
        return {k: decode(x) for k, x in v.items()}
    return v


def page_meta(did):
    st, body = curl('%s/data-catalogue/%s' % (BASE, did), timeout=60)
    if st != 200:
        raise IOError('HTTP %s' % st)
    m = re.search(r'<astro-island[^>]*DataCatalogueShow[^>]*props="([^"]*)"', body.decode('utf-8', 'replace'))
    if not m:
        raise ValueError('no metadata island')
    d = decode(json.loads(html.unescape(m.group(1))))
    data = d['data']
    meta = {k: data.get(k) for k in KEEP}
    meta.update(id=d.get('id', did), category=d.get('category', ''), subcategory=d.get('subcategory', ''))
    return meta


def load(did, cache_dir):
    path = os.path.join(cache_dir, did + '.json')
    if os.path.exists(path):
        return json.load(open(path, encoding='utf-8'))
    meta = page_meta(did)
    os.makedirs(cache_dir, exist_ok=True)
    json.dump(meta, open(path, 'w', encoding='utf-8'), ensure_ascii=False)
    return meta


def geography_of(title, cols):
    t = title.lower()
    geo = []
    federal = 'parliament' in t or 'pru' in t or 'federal' in t
    state = 'dun' in t or 'prn' in t or 'state' in t
    allel = 'all elections' in t
    if federal or allel:
        geo.append('PARLIMEN')
    if state or allel:
        geo.append('DUN')
    if 'state' in cols and 'STATE' not in geo:
        geo.append('STATE')
    return geo


def build_electiondata(ag, infer_keys, cache_dir, log):
    st, body = curl(BASE + '/data-catalogue/', timeout=60)
    ids = list(dict.fromkeys(re.findall(r'href="/data-catalogue/([\w-]+)"', body.decode('utf-8', 'replace'))))
    if st != 200 or not ids:
        raise IOError('could not read the ElectionData.MY catalogue (HTTP %s)' % st)

    def one(did):
        try:
            return did, load(did, cache_dir), None
        except Exception as e:
            return did, None, str(e)

    with ThreadPoolExecutor(6) as ex:
        results = list(ex.map(one, ids))
    agencies, _, _ = ag.resolve(['spr'])
    out, failed = [], []
    for did, m, err in results:
        if not m:
            failed.append('%s: %s' % (did, err))
            continue
        cols = [{'name': f['name'], 'title': f.get('title', ''), 'description': f.get('description', '')} for f in (m['fields'] or [])]
        keys, geo_inf = infer_keys(cols)
        if any(c['name'] == 'seat' for c in cols) and 'seat' not in keys:
            keys.append('seat')
        names = [c['name'] for c in cols]
        geo = geography_of(m['title'] or '', names)
        dl = m.get('download') or {}
        access = [{'type': {'xlsx': 'excel'}.get(k, k), 'url': v['link']} for k, v in dl.items() if isinstance(v, dict) and v.get('link')]
        desc = (m.get('description') or '').strip()
        span = re.search(r'(\d{4})\s*-\s*(?:present|\d{4})', desc)
        asof = m.get('data_as_of') if re.match(r'^\d{4}-\d{2}-\d{2}', m.get('data_as_of') or '') else None
        nxt = m.get('next_update') if re.match(r'^\d{4}-\d{2}-\d{2}', m.get('next_update') or '') else None
        out.append({
            'kind': 'dataset', 'id': 'electiondata:' + did,
            'title': {'en': m['title'], 'ms': m['title']},
            'description': {'en': desc, 'ms': ''},
            'category': {'en': 'Elections', 'ms': 'Pilihan Raya', 'sub': '%s: %s' % (m['category'], m['subcategory'])},
            'portals': ['electiondata'], 'agencies': agencies, 'tier': 3,
            'tier_basis': 'independent publisher: compiled from Election Commission of Malaysia results, not published by the agency',
            'publisher': PUBLISHER,
            'access': access, 'pages': [{'portal': 'electiondata', 'url': '%s/data-catalogue/%s' % (BASE, did)}],
            'licence': LICENCE, 'frequency': 'UNKNOWN', 'geography': [],
            'geography_inferred': list(dict.fromkeys(geo + [g for g in geo_inf if g not in geo])),
            'demography': [], 'coverage': {'begin': int(span.group(1)) if span else None, 'end': int(asof[:4]) if asof else None},
            'data_as_of': asof, 'last_updated': m.get('last_updated') if re.match(r'^\d{4}', m.get('last_updated') or '') else None,
            'next_update': nxt,
            'columns': cols, 'join_keys': keys,
            'methodology': (m.get('methodology') or '').strip(), 'caveats': CAVEAT,
            'related': [], 'see_also': [], 'source_agencies_raw': ['SPR', 'ElectionData.MY'],
        })
    log('ElectionData.MY: %d datasets from %d listed; %d failed%s' % (len(out), len(ids), len(failed), (': ' + '; '.join(failed[:4])) if failed else ''))
    return out
