#!/usr/bin/env python3
"""Put the salary sources side by side in one local file. Stdlib only.

    python extract/compare_salary_sources.py

Reads the committed DOSM and SSPA extractions (and the local-only Randstad file if present) and writes
data_local/salary_comparison.csv, one row per source and series, with the basis stated, so figures that
measure different things are never mixed up. Nothing here is a forecast. data_local/ is not committed.
"""
import csv, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rd = lambda p: list(csv.DictReader(open(os.path.join(ROOT, p), encoding='utf-8'))) if os.path.exists(os.path.join(ROOT, p)) else []
out = []
add = lambda *a: out.append(dict(zip(['source', 'series', 'year', 'low_rm', 'mid_rm', 'high_rm', 'basis', 'population', 'licence_status'], a)))

dosm = rd('data/dosm/salaries_wages/2025/values.csv')
def med(table, label, measure, year='2025'):
    v = [r['value'] for r in dosm if r['table'] == table and r['year'] == year and r['measure'] == measure and r['value'] and (r['label_en'] == label or r['label'] == label)]
    return float(v[0]) if v else ''
for t, lab, name in (('A10', 'Professionals', 'Occupation group: Professionals (MASCO 2)'), ('A13', 'Information and communication', 'Industry: Information and communication'), ('A3', 'Tertiary', 'Education: tertiary')):
    add('DOSM Salaries & Wages Survey 2025', name, 2025, '', med(t, lab, 'median_rm'), med(t, lab, 'mean_rm'), 'monthly median (mid) and mean (high column), gross, all employees', 'Malaysian citizens, paid employees', 'CC BY 4.0')
for r in rd('data/mof/sspa_pay_scales/2026/values.csv'):
    if r['service_group'] == 'PERKHIDMATAN AWAM PERSEKUTUAN' and r['code'] in ('9', '12', '13', '14', '15'):
        add('Belanjawan 2026 Lampiran A / JPA SSPA', 'Federal civil service grade ' + r['code'] + ' (management and professional)', 2026, r['min_rm'], '', r['max_rm'], 'minimum to maximum basic monthly pay of the grade', 'Public service posts only', 'Not stated; credit Ministry of Finance')
for r in rd('data_local/randstad/2026/values.csv'):
    if r['role'] in ('data scientist', 'data engineer', 'ML engineer', 'AI engineer', 'software engineer'):
        add('Randstad Malaysia 2026 (local only)', r['role'], 2026, r['min_rm_per_month'], '', r['max_rm_per_month'], "recruiter's basic monthly range, excludes bonus and equity", 'Roles Randstad recruits for, private sector', 'Not stated; kept local')
for r in rd('data/dosm/salaries_wages/2025/illustrative_trend.csv'):
    if r['series'].startswith(('Occupation: Professionals', 'Industry: Information')) and r['year'] in ('2026', '2028', '2030'):
        add('Projection from DOSM 2010-2025 trend', r['series'], int(r['year']), r['low_80'], r['median_rm_central'], r['high_80'], 'log-linear trend of the median, central value in mid_rm, approximate 80% band of the trend (not of individual pay); extrapolation, not a forecast', 'Same as the DOSM series it extends (%s%% a year)' % r['trend_growth_pct_per_year'], 'Derived by this project')
os.makedirs(os.path.join(ROOT, 'data_local'), exist_ok=True)
p = os.path.join(ROOT, 'data_local', 'salary_comparison.csv')
w = csv.DictWriter(open(p, 'w', newline='', encoding='utf-8'), list(out[0])); w.writeheader(); w.writerows(out)
for r in out:
    print('%-38s %-62s %6s %6s %6s' % (r['source'][:38], r['series'][:62], r['low_rm'], r['mid_rm'], r['high_rm']))
