#!/usr/bin/env python3
"""Monthly male-female median wage gap from an extracted formal-sector wages values.csv. Stdlib only.

    python extract/derive_formal_gap.py data/dosm/formal_wages/2026-Q1

gap_pct = (male - female) / male * 100 on DOSM's monthly median wage of Malaysian citizens in formal
employment. Derived by this project, not an official statistic; unadjusted for occupation or hours.
"""
import csv, os, sys
d = sys.argv[1]
R = list(csv.DictReader(open(os.path.join(d, 'values.csv'), encoding='utf-8')))
v = {(r['month'], r['group_en']): float(r['value']) for r in R if r['table'] == '2.1a' and r['section'] == 'Sex' and r['value']}
out = [{'month': mo, 'male_median_rm': v[(mo, 'Male')], 'female_median_rm': v[(mo, 'Female')], 'gap_pct': round((v[(mo, 'Male')] - v[(mo, 'Female')]) / v[(mo, 'Male')] * 100, 1)} for mo in sorted({k[0] for k in v})]
w = csv.DictWriter(open(os.path.join(d, 'derived_gender_gap_monthly.csv'), 'w', newline='', encoding='utf-8'), list(out[0])); w.writeheader(); w.writerows(out)
