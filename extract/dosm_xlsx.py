#!/usr/bin/env python3
"""Turn a DOSM statistical-report workbook (wide, one sheet per table) into a tidy long CSV.

    python extract/dosm_xlsx.py FILE.xlsx --source-url URL --edition 2025 --out DIR

Needs openpyxl (the harvest pipeline itself stays stdlib-only). Every output row carries its
sheet name and source row, so any figure can be traced to the cell it came from. Rows that do not
fit the expected layout are reported, never guessed. Checks run per table and are written to
checks.json; a table that fails a check is flagged, not dropped.
"""
import argparse, csv, json, os, re, sys, hashlib
import openpyxl

MEASURES = (('penerima', 'recipients_000'), ('penengah', 'median_rm'), ('median', 'median_rm'), ('purata', 'mean_rm'))
STOP = re.compile(r'^(nota|note|sumber|source|\*|\^)', re.I)


def measure_of(text):
    t = (text or '').lower()
    for k, v in MEASURES:
        if k in t:
            return v
    return None


def num(v):
    if isinstance(v, (int, float)):
        return float(v), ''
    if v is None or str(v).strip() == '':
        return None, 'blank'
    s = str(v).strip().replace(',', '')
    try:
        return float(s), ''
    except ValueError:
        return None, s[:12]  # '-', 'n.a.', '..' kept as a flag


def parse_sheet(ws):
    rows = list(ws.iter_rows(values_only=True))
    title = ' | '.join(str(r[0]).strip() for r in rows[:2] if r and r[0])
    hdr = None; ycols = []
    for i, r in enumerate(rows[:12]):
        ys = [j for j, c in enumerate(r) if j > 0 and c is not None and re.fullmatch(r'(19|20)\d\d', str(c).strip())]
        if len(ys) >= 3 and ys == list(range(ys[0], ys[-1] + 1)):  # contiguous year columns; text after them is the English label
            hdr, ycols = i, ys
            break
    if hdr is None:
        return title, None, [], ['no year header']
    cols = [(j, str(rows[hdr][j]).strip()) for j in ycols]
    en = ycols[-1] + 1
    out, issues = [], []
    sheet_measure = measure_of(ws.title)
    measure, section = sheet_measure, ''
    for i in range(hdr + 1, len(rows)):
        r = rows[i]
        label = str(r[0]).strip() if r and r[0] is not None else ''
        if not label:
            continue
        if STOP.match(label):
            break
        vals = [(y, num(r[j] if j < len(r) else None)) for j, y in cols]
        has = any(v[0] is not None for _, v in vals)
        m = measure_of(label)
        if m and not sheet_measure:
            measure = m  # a measure block opens; its own row carries the all-groups total, and the section (e.g. sex) stays
            if not has:
                continue
            label = 'Total'
        elif not has and not any(v[1] not in ('blank',) for _, v in vals):
            section = label
            continue
        for y, (v, flag) in vals:
            out.append({'measure': measure or '', 'section': section, 'label': label, 'label_en': (str(r[en]).strip() if len(r) > en and r[en] is not None else ''), 'year': y, 'value': '' if v is None else repr(v) if v != int(v) else str(int(v)), 'flag': flag if v is None and flag != 'blank' else '', 'src_row': i + 1})
    return title, [y for _, y in cols], out, issues


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('xlsx'); ap.add_argument('--source-url', required=True); ap.add_argument('--edition', required=True); ap.add_argument('--out', required=True)
    ap.add_argument('--sheets', default='', help='regex on sheet names; default all JADUAL/JAD sheets')
    a = ap.parse_args()
    wb = openpyxl.load_workbook(a.xlsx, data_only=True)
    sha = hashlib.sha256(open(a.xlsx, 'rb').read()).hexdigest()[:16]
    os.makedirs(a.out, exist_ok=True)
    rows, checks = [], []
    for ws in wb.worksheets:
        if not re.match(a.sheets or r'\s*JAD', ws.title, re.I):
            continue
        title, years, recs, issues = parse_sheet(ws)
        tid = re.match(r'\s*(?:JADUAL|JAD)\s*([A-C]\d+)', ws.title, re.I)
        tid = tid.group(1).upper() if tid else ws.title.strip()
        for r in recs:
            rows.append(dict(table=tid, sheet=ws.title.strip(), **r))
        sums = {}
        for r in recs:
            if r['measure'] == 'recipients_000' and r['value']:
                d = sums.setdefault((r['section'], r['year']), {'total': None, 'parts': 0.0, 'n': 0})
                if r['label'] == 'Total':
                    d['total'] = float(r['value'])
                else:
                    d['parts'] += float(r['value']); d['n'] += 1
        bad = [(k, d['total'], round(d['parts'], 1)) for k, d in sums.items() if d['total'] and d['n'] > 1 and abs(d['total'] - d['parts']) > max(1.0, 0.002 * d['total'])]
        n_blank = sum(1 for r in recs if r['value'] == '')
        checks.append({'table': tid, 'sheet': ws.title.strip(), 'title': title[:160], 'years': (years[0], years[-1]) if years else None, 'rows': len(recs), 'blank_cells': n_blank, 'sum_checks': len(sums), 'sum_failures': [list(map(str, b)) for b in bad[:5]], 'issues': issues})
    with open(os.path.join(a.out, 'values.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, ['table', 'sheet', 'measure', 'section', 'label', 'label_en', 'year', 'value', 'flag', 'src_row']); w.writeheader(); w.writerows(rows)
    meta = {'source_url': a.source_url, 'edition': a.edition, 'file_sha256_16': sha, 'method': 'xlsx cell read (exact, no OCR)', 'values_rows': len(rows), 'tables': checks}
    json.dump(meta, open(os.path.join(a.out, 'manifest.json'), 'w'), indent=1, ensure_ascii=False)
    print('%d rows from %d tables; %d with issues' % (len(rows), len(checks), sum(1 for c in checks if c['issues'])), file=sys.stderr)


if __name__ == '__main__':
    main()
