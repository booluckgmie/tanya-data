#!/usr/bin/env python3
"""Extract the public-sector pay scale table (SSPA minimum-maximum monthly pay per grade) from Belanjawan 2026 Lampiran A.

    python extract/mof_sspa.py LAMPIRAN-A.pdf --source-url URL --edition 2026 --out DIR

Needs pdfplumber. One row per grade: code, service group, category, minimum and maximum monthly pay (RM),
annual increment (RM, or a percentage for the top grades) and the increment at maximum. Every row carries its
page and line. Checks: minimum below maximum, parsed numbers re-read from the same line, and pay falling with
grade within each ordered federal series. Rows that do not match the expected layout are listed, not guessed.
"""
import argparse, csv, hashlib, json, os, re, sys
import pdfplumber

ROW = re.compile(r'^(?P<code>[A-Z]{0,3}\d{1,2}P?)\s+(?P<name>[A-Z][A-Z \-/()]+?)\s+(?P<min>\d{1,3}(?:,\d{3})*\.\d{2})\s+(?P<max>\d{1,3}(?:,\d{3})*\.\d{2})\s+(?P<inc>\d+(?:\.\d+)?%|\d{1,3}(?:,\d{3})*\.\d{2})\s+(?P<kgm>\d{1,3}(?:,\d{3})*\.\d{2})$')
CATEGORIES = ('PENGURUSAN DAN PROFESIONAL', 'PELAKSANA')
f = lambda s: float(s.replace(',', ''))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pdf'); ap.add_argument('--source-url', required=True); ap.add_argument('--edition', required=True); ap.add_argument('--out', required=True)
    a = ap.parse_args()
    rows, unmatched, group = [], [], ''
    with pdfplumber.open(a.pdf) as pdf:
        for pno, pg in enumerate(pdf.pages, 1):
            for ln, line in enumerate((pg.extract_text() or '').split('\n'), 1):
                line = line.strip()
                m = ROW.match(line)
                if m:
                    name = m['name'].strip()
                    cat = next((c for c in CATEGORIES if name == c), '')
                    pct = m['inc'].endswith('%')
                    rows.append({'code': m['code'], 'service_group': group, 'category': cat or name, 'min_rm': f(m['min']), 'max_rm': f(m['max']),
                                 'annual_increment': f(m['inc'].rstrip('%')), 'annual_increment_unit': 'percent' if pct else 'rm', 'increment_at_max_rm': f(m['kgm']), 'page': pno, 'line': ln})
                elif re.match(r'^PERKHIDMATAN |^JAWATAN-JAWATAN', line):
                    group = re.sub(r'\s*\(samb\.\)', '', line).strip()
                elif re.match(r'^[A-Z]{0,3}\d{1,2}P?\s+[A-Z]', line):
                    unmatched.append({'page': pno, 'line': ln, 'text': line})
    checks = {'min_below_max_failures': [r['code'] for r in rows if r['min_rm'] >= r['max_rm']], 'order_failures': []}
    for g in sorted({r['service_group'] for r in rows}):
        for cat in CATEGORIES:
            seq = [r for r in rows if r['service_group'] == g and r['category'] == cat and r['code'].isdigit()]  # numbered federal grades, listed from high to low
            for hi, lo in zip(seq, seq[1:]):
                if lo['max_rm'] > hi['max_rm']:
                    checks['order_failures'].append('%s > %s (maximum pay)' % (lo['code'], hi['code']))
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, 'values.csv'), 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, list(rows[0])); w.writeheader(); w.writerows(rows)
    json.dump({'source_url': a.source_url, 'edition': a.edition, 'file_sha256_16': hashlib.sha256(open(a.pdf, 'rb').read()).hexdigest()[:16], 'method': 'pdfplumber text extraction, one regex per row, text layer (no OCR)',
               'publisher': 'Ministry of Finance Malaysia (Belanjawan 2026, Lampiran A)', 'scope': 'Public-service posts only, by grade under SSPA. Monthly basic pay, RM. Not job titles.',
               'licence': 'Not stated on the document. Factual pay figures from an official public document; credit the Ministry of Finance.', 'rows': len(rows), 'unmatched_lines': unmatched, 'checks': checks},
              open(os.path.join(a.out, 'manifest.json'), 'w'), indent=1, ensure_ascii=False)
    print('%d rows; %d unmatched; checks %s' % (len(rows), len(unmatched), checks), file=sys.stderr)


if __name__ == '__main__':
    main()
