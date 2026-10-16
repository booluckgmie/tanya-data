#!/usr/bin/env python3
"""Snapshot this site's Vercel Web Analytics into app/analytics.json for the page's "Site usage" section.

    VERCEL_TOKEN=... python3 tools/fetch_analytics.py [--project prj_...] [--team team_...] [--days 30]

Reads aggregate counts only (visitors and pageviews by day, page, country, device, referrer). It stores
no visitor-level data. The token needs read access to the project and is never written anywhere.
Hobby plans keep 31 days of data, so each run overwrites the snapshot with the latest window.
Standard library only.
"""
import argparse, json, os, sys, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'app', 'analytics.json')


def get(path, params, token):
    req = urllib.request.Request('https://api.vercel.com' + path + '?' + urllib.parse.urlencode(params), headers={'Authorization': 'Bearer ' + token})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def rows(resp):
    return [{'key': str(d.get('key', '')), 'views': int(d.get('total', d.get('pageviews', 0)) or 0), 'visitors': int(d.get('devices', d.get('visitors', 0)) or 0)} for d in resp.get('data', [])]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--project', default='prj_wElyPsdh8sjJPvQMVhSwvcJX9kKw'); ap.add_argument('--team', default='team_YWXoh9J5uvtJSnOIlBq2H8Rl'); ap.add_argument('--days', type=int, default=30)
    a = ap.parse_args()
    token = os.environ.get('VERCEL_TOKEN')
    if not token:
        sys.exit('set VERCEL_TOKEN')
    now = datetime.now(timezone.utc); since = (now - timedelta(days=a.days)).strftime('%Y-%m-%dT00:00:00.000Z'); until = now.strftime('%Y-%m-%dT%H:%M:00.000Z')
    base = {'projectId': a.project, 'teamId': a.team, 'since': since, 'until': until}
    snap = {'as_of': now.strftime('%Y-%m-%d'), 'since': since[:10], 'days': a.days}
    snap['total'] = get('/v1/query/web-analytics/visits/count', base, token).get('data', {})
    for name, dim in (('daily', 'day'), ('pages', 'requestPath'), ('countries', 'country'), ('devices', 'deviceType'), ('referrers', 'referrerHostname')):
        snap[name] = rows(get('/v1/query/web-analytics/visits/aggregate', dict(base, by=dim, limit=10), token))
    json.dump(snap, open(OUT, 'w'), indent=1)
    print('wrote', OUT, snap['total'], file=sys.stderr)


if __name__ == '__main__':
    main()
