#!/usr/bin/env python3
"""Check that every registry record still points at a live official page and file.

    python harvest/verify_links.py [--workers 8] [--limit N]

Writes the result back into registry/registry.json (record['verified']) and a
human-readable registry/link_report.md. A 404/410 is definitive. A network error
or 5xx is recorded as 'unreachable' and does not remove a record: the platform
must never hide a good dataset because of a flaky connection.

Standard library only.
"""
import argparse, json, os, sys, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REG = os.path.join(ROOT, 'registry', 'registry.json')
CACHE = os.path.join(ROOT, '.cache', 'link_cache.json')  # url -> [status, iso time]; skips URLs checked recently
UA = {'User-Agent': 'tanya-data-link-check/0.1 (+metadata referral index)'}


def probe(url):
    """-> (status, note). status is an int HTTP code, or 0 when unreachable."""
    last = (0, 'no response')
    for attempt in range(3):
        for method in ('HEAD', 'GET'):
            req = urllib.request.Request(url, method=method, headers=dict(UA, **({'Range': 'bytes=0-0'} if method == 'GET' else {})))
            try:
                with urllib.request.urlopen(req, timeout=25) as r:
                    return r.status, ''
            except urllib.error.HTTPError as e:
                if e.code in (404, 410):
                    return e.code, ''
                last = (e.code, e.reason)
                if method == 'HEAD' and e.code in (400, 403, 405, 501):
                    continue  # some hosts refuse HEAD
                break
            except Exception as e:
                last = (0, type(e).__name__)
                break
        time.sleep(2 * (attempt + 1))
    return last


def targets(rec):
    t = [('page', p['url']) for p in rec['pages'] if p['portal'] != 'datagovmy' or rec['kind'] != 'live_api']
    acc = rec['access']
    if rec['kind'] == 'dataset':
        acc = [a for a in acc if a['type'] == 'csv'][:1]
    elif rec['kind'] == 'dashboard':
        acc = acc[:1]
    t += [('file', a['url']) for a in acc]
    return t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workers', type=int, default=8)
    ap.add_argument('--limit', type=int, default=0, help='check only the first N records (for testing)')
    ap.add_argument('--max-age-hours', type=float, default=12, help='reuse cached results younger than this')
    a = ap.parse_args()
    reg = json.load(open(REG, encoding='utf-8'))
    recs = reg['records'][:a.limit] if a.limit else reg['records']
    urls = sorted({u for r in recs for _, u in targets(r)})
    try:
        cache = json.load(open(CACHE))
    except Exception:
        cache = {}
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%MZ')
    fresh = lambda t: (datetime.now(timezone.utc) - datetime.strptime(t, '%Y-%m-%dT%H:%MZ').replace(tzinfo=timezone.utc)).total_seconds() < a.max_age_hours * 3600
    todo = [u for u in urls if u not in cache or not fresh(cache[u][1]) or cache[u][0] == 0]
    print('checking %d of %d unique URLs (%d cached) for %d records' % (len(todo), len(urls), len(urls) - len(todo), len(recs)), file=sys.stderr)
    with ThreadPoolExecutor(a.workers) as ex:
        for u, (st, note) in zip(todo, ex.map(probe, todo)):
            cache[u] = [st, now]
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    json.dump(cache, open(CACHE, 'w'))
    res = {u: cache[u] for u in urls}
    bad = []
    for r in recs:
        checks = [{'role': role, 'url': u, 'status': res[u][0]} for role, u in targets(r)]
        pages = [c for c in checks if c['role'] == 'page']
        files = [c for c in checks if c['role'] == 'file']
        page_ok = any(200 <= c['status'] < 400 for c in pages)
        page_gone = bool(pages) and all(c['status'] in (404, 410) for c in pages)
        file_gone = [c for c in files if c['status'] in (404, 410)]
        if page_gone:
            state = 'page_missing'
        elif file_gone and len(file_gone) == len(files):
            state = 'file_missing'
        elif not page_ok and pages and all(c['status'] == 0 or c['status'] >= 500 for c in pages):
            state = 'unreachable'
        else:
            state = 'ok'
        r['verified'] = {'checked_at': now, 'state': state, 'checks': checks}
        if state != 'ok':
            bad.append((r, state, [c for c in checks if not (200 <= c['status'] < 400)]))
    json.dump(reg, open(REG, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    kinds = {}
    for r in recs:
        kinds.setdefault(r['kind'], [0, 0]); kinds[r['kind']][0] += 1; kinds[r['kind']][1] += r['verified']['state'] == 'ok'
    lines = ['# Link check report', '', 'Checked %s. A record is "ok" when its portal page answers and its file is not gone.' % now, '',
             '| Kind | Records | OK |', '|---|---|---|'] + ['| %s | %d | %d |' % (k, v[0], v[1]) for k, v in sorted(kinds.items())]
    for state, title in (('page_missing', 'Portal page not found (404/410)'), ('file_missing', 'Download not found (404/410)'), ('unreachable', 'Could not be checked (network error or 5xx)')):
        rows = [(r, f) for r, s, f in bad if s == state]
        if rows:
            lines += ['', '## %s: %d' % (title, len(rows)), '']
            for r, f in rows:
                lines.append('- `%s` (%s): %s' % (r['id'], r['kind'], ', '.join('%s %s' % (c['status'], c['url']) for c in f)))
    open(os.path.join(ROOT, 'registry', 'link_report.md'), 'w').write('\n'.join(lines) + '\n')
    print('\n'.join(lines[:12]), file=sys.stderr)


if __name__ == '__main__':
    main()
