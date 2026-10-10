#!/usr/bin/env python3
"""Illustrative salary trend projection from an extracted DOSM Salaries & Wages values.csv. Stdlib only.

    python extract/project_trend.py data/dosm/salaries_wages/2025 [--to 2030]

For each series it fits log(median RM) = a + b*year by least squares on 2010-2025 (2020 kept; the
COVID dip widens the band), then extends to the horizon. The band is +/- 1.28 residual standard
deviations (about an 80% band if errors are roughly normal). It also shows the compound growth over
the last 5 years. This is an extrapolation of past data, NOT a forecast and NOT an official
statistic. It assumes the future resembles 2010-2025.
"""
import csv, math, os, sys

d = sys.argv[1]
to = int(sys.argv[sys.argv.index('--to') + 1]) if '--to' in sys.argv else 2030
rows = list(csv.DictReader(open(os.path.join(d, 'values.csv'), encoding='utf-8')))
SERIES = [('A10', 'Professionals', 'Occupation: Professionals (MASCO 2)'), ('A10', 'Managers', 'Occupation: Managers (MASCO 1)'),
          ('A10', 'Technicians and associate professionals', 'Occupation: Technicians and associate professionals (MASCO 3)'),
          ('A13', 'Information and communication', 'Industry: Information and communication'),
          ('A13', 'Professional, scientific and technical activities', 'Industry: Professional, scientific and technical'),
          ('A3', 'Tertiary', 'Education: Tertiary (all sectors)'), ('A1', 'Total', 'All employees')]
out = []
for t, lab, name in SERIES:
    pts = {int(r['year']): float(r['value']) for r in rows if r['table'] == t and r['measure'] == 'median_rm' and r['value']
           and (r['label_en'] == lab or r['label'] == lab or (lab == 'Total' and r['label'] == 'Total'))}
    if len(pts) < 8:
        print('skip', name, len(pts), file=sys.stderr); continue
    xs = sorted(pts); n = len(xs); mx = sum(xs) / n; ly = [math.log(pts[x]) for x in xs]; my = sum(ly) / n
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ly)) / sum((x - mx) ** 2 for x in xs); a = my - b * mx
    sd = math.sqrt(sum((y - (a + b * x)) ** 2 for x, y in zip(xs, ly)) / (n - 2))
    last = xs[-1]; cagr5 = (pts[last] / pts[last - 5]) ** 0.2 - 1 if last - 5 in pts else None
    for y in range(last + 1, to + 1):
        c = a + b * y
        out.append({'series': name, 'year': y, 'median_rm_central': round(math.exp(c)), 'low_80': round(math.exp(c - 1.28 * sd)), 'high_80': round(math.exp(c + 1.28 * sd)),
                    'trend_growth_pct_per_year': round((math.exp(b) - 1) * 100, 1), 'last5y_cagr_pct': round(cagr5 * 100, 1) if cagr5 is not None else '', 'last_actual_year': last, 'last_actual_rm': int(pts[last]), 'fit_years': '%d-%d' % (xs[0], xs[-1])})
p = os.path.join(d, 'illustrative_trend.csv')
w = csv.DictWriter(open(p, 'w', newline='', encoding='utf-8'), list(out[0])); w.writeheader(); w.writerows(out)
for r in out:
    if r['year'] in (2026, to):
        print(r['series'][:52].ljust(53), r['year'], r['median_rm_central'], '(%d-%d)' % (r['low_80'], r['high_80']), 'trend %s%%/yr, last5y %s%%, last actual %d=%d' % (r['trend_growth_pct_per_year'], r['last5y_cagr_pct'], r['last_actual_year'], r['last_actual_rm']))
