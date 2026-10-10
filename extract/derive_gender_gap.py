#!/usr/bin/env python3
"""Derive a gender pay gap table from an extracted DOSM Salaries & Wages values.csv. Stdlib only.

    python extract/derive_gender_gap.py data/dosm/salaries_wages/2025

gap_pct = (male - female) / male * 100, on the survey's own monthly median and mean (RM).
This is a DERIVED figure computed by this project from DOSM's published numbers, not an official
DOSM statistic. It is unadjusted: it does not control for occupation, hours, age or experience.
Only cells where both sexes have a value are written.
"""
import csv, json, os, sys

d = sys.argv[1]
rows = list(csv.DictReader(open(os.path.join(d, 'values.csv'), encoding='utf-8')))
DIM = {'A2': 'Age group', 'A4': 'Tertiary-educated, by age', 'A6': 'Certificate holders, by age', 'A7': 'Strata (urban/rural)', 'A9': 'State',
       'A11': 'Occupation (MASCO major group)', 'A12': 'Skill category', 'A14': 'Industry (MSIC section)', 'A16': 'Sector', 'B2': 'Ethnic group'}
titles = DIM


def sex(r):
    s = (r['sheet'] + ' ' + r['section']).lower()
    return 'M' if 'lelaki' in s else 'F' if ('perem' in s or 'prmpuan' in s) else None


cell = {}
for r in rows:
    s = sex(r)
    if not s or r['measure'] not in ('median_rm', 'mean_rm') or not r['value'] or r['label'] == 'Total' and False:
        continue
    key = (r['table'], r['measure'], 'Total' if r['label'] in ('Total', 'Median (RM)', 'Mean (RM)') or r['label_en'] in ('Median (RM)', 'Mean (RM)') else r['label_en'] or r['label'], r['year'])
    cell[(key, s)] = (float(r['value']), r['sheet'], r['src_row'])
out = []
for (key, s), (m, sh, sr) in sorted(cell.items()):
    if s != 'M' or (key, 'F') not in cell:
        continue
    f, fsh, fsr = cell[(key, 'F')]
    t, meas, grp, yr = key
    out.append({'table': t, 'dimension': titles.get(t, t), 'group': grp, 'measure': meas, 'year': yr,
                'male_rm': int(m) if m == int(m) else m, 'female_rm': int(f) if f == int(f) else f,
                'gap_pct': round((m - f) / m * 100, 1), 'female_to_male': round(f / m, 3),
                'male_src': '%s!row%s' % (sh, sr), 'female_src': '%s!row%s' % (fsh, fsr)})
p = os.path.join(d, 'derived_gender_gap.csv')
w = csv.DictWriter(open(p, 'w', newline='', encoding='utf-8'), list(out[0]))
w.writeheader(); w.writerows(out)
print(len(out), 'rows ->', p, file=sys.stderr)
