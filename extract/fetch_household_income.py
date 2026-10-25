#!/usr/bin/env python3
"""Download OpenDOSM's national Household Income series (mean and median monthly household income, RM, survey years 1970 to 2024).

    python extract/fetch_household_income.py data/dosm/household_income

Source: data.gov.my data catalogue dataset `hh_income` (DOSM, CC BY 4.0). One API call. Writes values.csv and manifest.json.
This is HOUSEHOLD income, not individual pay: it is the longest official income series, useful for history before the
Salaries & Wages Survey starts in 2010. Stdlib only.
"""
import csv, hashlib, json, os, sys, urllib.request
out = sys.argv[1]
url = 'https://api.data.gov.my/data-catalogue?id=hh_income&limit=400'
raw = urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'tanya-data/0.1'}), timeout=60).read()
rows = sorted(json.loads(raw), key=lambda r: r['date'])
os.makedirs(out, exist_ok=True)
with open(os.path.join(out, 'values.csv'), 'w', newline='') as f:
    w = csv.writer(f); w.writerow(['year', 'mean_household_income_rm_per_month', 'median_household_income_rm_per_month'])
    for r in rows: w.writerow([r['date'][:4], r['income_mean'], r['income_median']])
json.dump({'source_url': url, 'dataset': 'hh_income (OpenDOSM / data.gov.my data catalogue)', 'publisher': 'Department of Statistics Malaysia', 'licence': 'CC BY 4.0', 'rows': len(rows), 'years': [rows[0]['date'][:4], rows[-1]['date'][:4]],
           'response_sha256_16': hashlib.sha256(raw).hexdigest()[:16], 'note': 'Survey years only (not every year). Household income, not individual wages. Nominal ringgit.'}, open(os.path.join(out, 'manifest.json'), 'w'), indent=1)
print(len(rows), 'rows', file=sys.stderr)
