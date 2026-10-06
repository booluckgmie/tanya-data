#!/usr/bin/env python3
"""Keep a permanent copy of MPOB's daily crude palm oil prices.

MPOB serves only the last three years of daily prices, and a year's file stops answering once it
rolls out of that window. This script downloads each year MPOB still serves, parses the Excel
calendar into a tidy CSV (date, price_rm_per_tonne, status) and saves it under archive/mpob/.
It never deletes: a year MPOB no longer serves is kept exactly as last saved.

A file is rewritten only when its parsed content changes, because the Excel download embeds a new
timestamp on every request.

    python3 harvest/archive_mpob.py [--out archive/mpob] [--seed-from DIR_WITH_cpo_daily_prices_YYYY.csv]

Seeding imports a year from an older scrape (columns date, price) when no archive file exists for it.
Standard library only, plus curl.
"""
import argparse, csv, hashlib, io, json, os, re, sys, zipfile
from datetime import date, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from net import curl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXCEL = 'https://bepi.mpob.gov.my/admin2/price_local_daily_view_cpo_msia_excel.php?val=%d&excel=Y'
MONTHS = ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december']
HEADER = ['date', 'price_rm_per_tonne', 'status']


def cell_text(inner):
    m = re.search(r'<t[^>]*>(.*?)</t>', inner or '', re.S) or re.search(r'<v>(.*?)</v>', inner or '', re.S)
    return re.sub(r'&amp;', '&', m.group(1)).strip() if m else ''


def parse_xlsx(body, year):
    """Excel calendar (days down column A, months across B to M) -> [(iso date, price or '', status)]."""
    sh = zipfile.ZipFile(io.BytesIO(body)).read('xl/worksheets/sheet1.xml').decode('utf-8')
    grid = {}
    for rn, rxml in re.findall(r'<row [^>]*?r="(\d+)"[^>]*>(.*?)</row>', sh, re.S):
        for col, inner in re.findall(r'<c r="([A-Z]+)\d+"[^>]*?(?:/>|>(.*?)</c>)', rxml, re.S):
            t = cell_text(inner)
            if t:
                grid[(int(rn), col)] = t
    cols = 'BCDEFGHIJKLM'
    hdr = next((r for r in range(1, 30) if [grid.get((r, c), '').lower() for c in cols] == MONTHS), None)
    if hdr is None:
        raise ValueError('month header row not found (sheet layout changed?)')
    out = []
    for r in range(hdr + 1, hdr + 40):
        day = grid.get((r, 'A'), '')
        if not re.fullmatch(r'\d{1,2}', day):
            continue
        for mi, c in enumerate(cols, 1):
            try:
                d = date(year, mi, int(day))
            except ValueError:
                continue  # a day that does not exist, such as 30 February
            v = grid.get((r, c), '')
            num = v.replace(',', '')
            if re.fullmatch(r'\d+(\.\d+)?', num):
                out.append((d.isoformat(), num, 'price'))
            elif v == 'PH':
                out.append((d.isoformat(), '', 'public_holiday'))
            elif v == 'NT':
                out.append((d.isoformat(), '', 'no_trade'))
            elif v == '**':
                out.append((d.isoformat(), '', 'pending'))
            # '-' and blanks are days not yet reached: not recorded
    return sorted(out)


def to_csv(rows):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator='\n')
    w.writerow(HEADER)
    w.writerows(rows)
    return buf.getvalue()


def seed_rows(path):
    rows = []
    with open(path, newline='', encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            d, v = r['date'].strip(), r['price'].strip()
            if re.fullmatch(r'\d+(\.\d+)?', v):
                rows.append((d, v, 'price'))
            elif v in ('PH', 'NT'):
                rows.append((d, '', {'PH': 'public_holiday', 'NT': 'no_trade'}[v]))
    return sorted(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(ROOT, 'archive', 'mpob'))
    ap.add_argument('--seed-from', help='folder holding older scrapes named cpo_daily_prices<YEAR>.csv')
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    manifest_path = os.path.join(a.out, 'manifest.json')
    manifest = json.load(open(manifest_path)) if os.path.exists(manifest_path) else {}
    changed, thisyear, got_current = [], date.today().year, False
    for y in range(thisyear, thisyear - 6, -1):
        path = os.path.join(a.out, 'cpo_daily_%d.csv' % y)
        st, body = curl(EXCEL % y, timeout=90)
        if st == 200 and body[:2] == b'PK':
            try:
                rows, source = parse_xlsx(body, y), 'MPOB Excel export'
            except Exception as e:
                print('%d: could not parse the Excel file: %s' % (y, e), file=sys.stderr)
                continue
            got_current |= (y == thisyear)
        else:
            rows, source = None, None  # MPOB no longer serves this year
        if rows is None and not os.path.exists(path) and a.seed_from:
            sp = os.path.join(a.seed_from, 'cpo_daily_prices%d.csv' % y)
            if os.path.exists(sp):
                rows, source = seed_rows(sp), 'imported from an earlier scrape of the MPOB price pages'
        if rows is None:
            print('%d: not served by MPOB%s' % (y, ', kept as saved' if os.path.exists(path) else ', nothing saved'), file=sys.stderr)
            continue
        text = to_csv(rows)
        old = open(path, encoding='utf-8').read() if os.path.exists(path) else None
        if old == text:
            print('%d: unchanged (%d rows)' % (y, len(rows)), file=sys.stderr)
            continue
        open(path, 'w', encoding='utf-8').write(text)
        priced = [r[0] for r in rows if r[2] == 'price']
        manifest[str(y)] = {'rows': len(rows), 'priced_days': len(priced), 'first_priced': priced[0] if priced else None,
                            'last_priced': priced[-1] if priced else None, 'source': source,
                            'sha256': hashlib.sha256(text.encode()).hexdigest()[:16]}
        changed.append(y)
        print('%d: saved %d rows, %d priced days, last priced %s (%s)' % (y, len(rows), len(priced), priced[-1] if priced else '-', source), file=sys.stderr)
    json.dump(dict(sorted(manifest.items())), open(manifest_path, 'w'), indent=1)
    if not got_current:
        print('ERROR: the current year (%d) could not be downloaded from MPOB' % thisyear, file=sys.stderr)
        sys.exit(1)
    print('changed years: %s' % (changed or 'none'), file=sys.stderr)


if __name__ == '__main__':
    main()
