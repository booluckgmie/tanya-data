#!/usr/bin/env python3
"""Parse DOSM's quarterly Employee Wages Statistics (Formal Sector) workbook into a tidy long CSV.

    python extract/dosm_formal_wages.py FILE.xlsx --source-url URL --edition 2026-Q1 --out DIR

Needs openpyxl. Covers citizens in formal employment only (the workbook's own scope), monthly,
over a rolling window of about 18 months. Two sheet families:
  * month-column sheets (1.x employees, 2.x median wage, 3.1 wage-scale, 3.2 percentiles):
    rows are groups (sex, ethnic, age, activity, state, ...), columns are months
  * age x broad-sector matrices (3.3 headcount and share, 3.4 median wage), one block per month
Every row carries sheet and cell coordinates. Checks compare group sums with the Total row for
headcount sheets; failures are written to the manifest, not hidden.
"""
import argparse, csv, hashlib, json, os, re, sys
import openpyxl

MONTHS = {m: i + 1 for i, m in enumerate('january february march april may june july august september october november december'.split())}
MALAY = {'januari': 1, 'februari': 2, 'mac': 3, 'april': 4, 'mei': 5, 'jun': 6, 'julai': 7, 'ogos': 8, 'september': 9, 'oktober': 10, 'november': 11, 'disember': 12}
SUFFIX = {'a': None, 'b': 'share_pct', 'c': 'mom_pct', 'd': 'yoy_pct'}
BASE = {'1': 'employees_000', '2': 'median_wage_rm', '3.1': 'employees_000', '3.2': 'wage_rm'}
STOP = re.compile(r'^(nota|note|sumber|source)', re.I)


def clean(v):
    return re.sub(r'\s+', ' ', str(v).replace('\n', '/')).strip() if v is not None else ''


def split_bi(v):
    """'Lelaki /Male' -> ('Lelaki', 'Male')"""
    raw = str(v) if v is not None else ''
    if '/' not in raw:
        lines = [l.strip() for l in raw.split('\n') if l.strip()]
        if len(lines) >= 2 and len(lines) % 2 == 0:  # Malay lines then English lines, no slash
            h = len(lines) // 2
            return ' '.join(lines[:h]), ' '.join(lines[h:])
    s = clean(v)
    if '/' in s:
        a, _, b = s.rpartition('/')
        return a.strip(), b.strip()
    return s, s


def num(v):
    if isinstance(v, (int, float)):
        return float(v), ''
    s = clean(v)
    if s == '':
        return None, 'blank'
    try:
        return float(s.replace(',', '')), ''
    except ValueError:
        return None, s[:10]


def month_key(text, year):
    en = clean(text).rpartition('/')[2].strip().lower()
    n = MONTHS.get(en) or MALAY.get(clean(text).split('/')[0].strip().lower())
    return '%s-%02d' % (year, n) if n and year else None


def measure_for(sid):
    m = re.match(r'(\d)\.(\d)([a-d]?)$', sid)
    if not m:
        return None
    top, sub, suf = m.groups()
    key = '3.1' if (top, sub) == ('3', '1') else '3.2' if (top, sub) == ('3', '2') else top
    if suf in ('b', 'c', 'd'):
        return SUFFIX[suf]
    return BASE.get(key)


def parse_month_sheet(ws, sid, meas):
    rows = list(ws.iter_rows(values_only=True))
    isyear = lambda r: any(re.fullmatch(r'20\d\d', clean(c)) for c in r)
    h = next((i for i in range(4, 12) if i + 2 < len(rows) and isyear(rows[i + 1]) and not isyear(rows[i])), None)
    if h is None:
        return [], ['no month header']
    yr_row, mo_row = rows[h + 1], rows[h + 2]
    cols, year = [], None
    for j in range(len(mo_row)):
        if yr_row[j] is not None and re.fullmatch(r'20\d\d', clean(yr_row[j])):
            year = clean(yr_row[j])
        k = month_key(mo_row[j], year) if mo_row[j] is not None else None
        if k:
            cols.append((j, k))
    out, section = [], ''
    for i in range(h + 3, len(rows)):
        r = rows[i]
        a, b = clean(r[0]), clean(r[1]) if len(r) > 1 else ''
        if STOP.match(a):
            break
        label_raw = b if re.fullmatch(r'\d+\.?', a) and b else a  # activity rows carry a number in col A and the name in col B
        if not label_raw:
            continue
        vals = [(k, num(r[j])) for j, k in cols]
        if not any(v[0] is not None for _, v in vals):
            my, en = split_bi(label_raw)
            if not re.match(r'(number|percentage|bilangan|peratus)', en, re.I):
                section = en
            continue
        my, en = split_bi(label_raw)
        for k, (v, flag) in vals:
            out.append({'table': sid, 'measure': meas, 'section': section, 'group_my': my, 'group_en': 'Total' if en.lower() in ('total', 'jumlah', 'malaysia') else en,
                        'sector': '', 'month': k, 'value': '' if v is None else repr(v), 'flag': '' if flag in ('', 'blank') else flag, 'src': '%s!R%dC%d' % (ws.title, i + 1, [j for j, kk in cols if kk == k][0] + 1)})
    return out, []


def parse_matrix_sheet(ws, sid):
    """age x broad-sector blocks. Block title rows look like 'Januari 2026' / 'January 2026'; 3.3 has headcount then share blocks."""
    rows = list(ws.iter_rows(values_only=True))
    h = next((i for i, r in enumerate(rows[:10]) if any('Aktiviti' in clean(c) for c in r)), None)
    if h is None:
        return [], ['no sector header']
    sec_cols = [(j, split_bi(c)[1]) for j, c in enumerate(rows[h + 1]) if c is not None and j > 0]
    title = clean(ws.title)
    out, month, meas, i = [], None, None, h + 2
    period = None
    if sid.startswith('3.3'):
        mm = re.search(r'(\w+) (20\d\d)', clean(ws['C2'].value))  # 'Number of formal employees by age group and economic activity, January 2026'
        period = month_key(mm.group(1), mm.group(2)) if mm else None
    while i < len(rows):
        r = rows[i]; a = clean(r[0])
        vals = [(c, label, num(r[j] if j < len(r) else None)) for j, label in [(j, l) for j, l in sec_cols] for c in [j]]
        has = any(v[0] is not None for _, _, v in vals)
        if STOP.match(a):
            break
        if not has and a:
            en = split_bi(a)[1]
            m2 = re.fullmatch(r'(\w+) (20\d\d)', en)
            if m2 and sid == '3.4':
                month = month_key(m2.group(1), m2.group(2)); meas = 'median_wage_rm'
            elif re.match(r'(number of|bilangan)', en, re.I):
                meas = 'employees_000'
            elif re.match(r'(percentage|peratus)', en, re.I):
                meas = 'share_pct'
            i += 1; continue
        if has and a:
            my, en = split_bi(a)
            for j, lab, (v, flag) in vals:
                out.append({'table': sid, 'measure': meas or 'median_wage_rm', 'section': 'Age group', 'group_my': my, 'group_en': en, 'sector': lab,
                            'month': month or period, 'value': '' if v is None else repr(v), 'flag': '' if flag in ('', 'blank') else flag, 'src': '%s!R%dC%d' % (ws.title, i + 1, j + 1)})
        i += 1
    return out, []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('xlsx'); ap.add_argument('--source-url', required=True); ap.add_argument('--edition', required=True); ap.add_argument('--out', required=True)
    a = ap.parse_args()
    wb = openpyxl.load_workbook(a.xlsx, data_only=True)
    sha = hashlib.sha256(open(a.xlsx, 'rb').read()).hexdigest()[:16]
    os.makedirs(a.out, exist_ok=True)
    rows, tables = [], []
    for ws in wb.worksheets:
        sid = ws.title.strip()
        if not re.fullmatch(r'\d\.\d[a-d]?', sid):
            continue
        title = clean(ws['C2'].value or ws['C1'].value)
        if sid.startswith(('3.3', '3.4')):
            recs, issues = parse_matrix_sheet(ws, sid)
        else:
            meas = measure_for(sid)
            recs, issues = parse_month_sheet(ws, sid, meas) if meas else ([], ['unknown measure'])
        rows += recs
        fails = []; nchk = 0
        if recs and recs[0]['measure'] == 'employees_000' and not sid.startswith('3.'):
            by = {}
            for r in recs:
                if not r['value']:
                    continue
                d = by.setdefault((r['section'], r['month']), {'t': None, 'p': 0.0, 'n': 0})
                v = float(r['value'])
                if r['group_en'] == 'Total':
                    d['t'] = v
                elif r['section'] == d.get('sec', r['section']):
                    d['p'] += v; d['n'] += 1
            tot = {r['month']: float(r['value']) for r in recs if r['group_en'] == 'Total' and r['value']}
            for (sec, mo), d in by.items():
                nchk += d['n'] > 1 and mo in tot
                if d['n'] > 1 and mo in tot and abs(tot[mo] - d['p']) > max(0.5, 0.002 * tot[mo]):
                    fails.append([sec, mo, tot[mo], round(d['p'], 1)])
        tables.append({'table': sid, 'title': title[:140], 'rows': len(recs), 'sum_failures': fails[:6], 'sum_checks': int(nchk), 'n_sum_failures': len(fails), 'issues': issues})
    cols = ['table', 'measure', 'section', 'group_my', 'group_en', 'sector', 'month', 'value', 'flag', 'src']
    with open(os.path.join(a.out, 'values.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, cols); w.writeheader(); w.writerows(rows)
    months = sorted({r['month'] for r in rows if r['month']})
    json.dump({'source_url': a.source_url, 'edition': a.edition, 'file_sha256_16': sha, 'method': 'xlsx cell read (exact, no OCR)', 'scope': 'Malaysian citizens in formal-sector employment (EPF/SOCSO/LHDN-based administrative data, per DOSM)',
               'months': [months[0], months[-1]] if months else None, 'values_rows': len(rows), 'tables': tables}, open(os.path.join(a.out, 'manifest.json'), 'w'), indent=1, ensure_ascii=False)
    print('%d rows from %d tables; %d with issues; %d with sum failures' % (len(rows), len(tables), sum(1 for t in tables if t['issues']), sum(1 for t in tables if t['n_sum_failures'])), file=sys.stderr)


if __name__ == '__main__':
    main()
