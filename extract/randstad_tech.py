#!/usr/bin/env python3
"""Read the technology salary table on Randstad Malaysia's public 'Emerging Technology Jobs in Malaysia 2026' page. Stdlib only.

    python extract/randstad_tech.py --out data_local/randstad/2026 [--html FILE]

Fetches the page with curl (or reads --html), parses the single HTML table (role, basic monthly salary range in RM,
market drivers) and writes values.csv and manifest.json with the source URL, publication dates and the page's own
footnote. Figures are Randstad's, published for readers; this project keeps them LOCAL (data_local/ is not committed)
because the page states no reuse licence. Rows are never altered; a row that does not parse is reported.
"""
import argparse, csv, hashlib, html, json, os, re, subprocess, sys

URL = 'https://www.randstad.com.my/most-in-demand-jobs-malaysia-emerging-technology/'
txt = lambda s: html.unescape(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', s))).strip()


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--out', required=True); ap.add_argument('--html')
    a = ap.parse_args()
    raw = open(a.html, encoding='utf-8', errors='ignore').read() if a.html else subprocess.run(['curl', '-sSL', '-m', '60', '-A', 'Mozilla/5.0 (compatible; tanya-data-research/0.1)', URL], capture_output=True, text=True, check=True).stdout
    body = re.sub(r'<script.*?</script>|<style.*?</style>', '', raw, flags=re.S)
    rows, bad = [], []
    for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', body, flags=re.S)[1:]:
        c = [txt(x) for x in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', tr, flags=re.S)]
        m = re.fullmatch(r'([\d,]+)\s*[–-]\s*([\d,]+)', c[1]) if len(c) >= 3 else None
        if not m:
            bad.append(c); continue
        lo, hi = (int(x.replace(',', '')) for x in m.groups())
        rows.append({'role': c[0], 'min_rm_per_month': lo, 'max_rm_per_month': hi, 'market_drivers': c[2], 'basis': 'basic monthly salary, excludes bonus and equity'})
    foot = re.search(r'\*Figures represent[^.]*\.[^.]*\.', txt(body))
    pub = re.search(r'"datePublished"\s*:\s*"([^"]+)"', raw); mod = re.search(r'"dateModified"\s*:\s*"([^"]+)"', raw)
    os.makedirs(a.out, exist_ok=True)
    w = csv.DictWriter(open(os.path.join(a.out, 'values.csv'), 'w', newline='', encoding='utf-8'), list(rows[0])); w.writeheader(); w.writerows(rows)
    json.dump({'source_url': URL, 'publisher': 'Randstad Malaysia', 'document': 'Randstad Malaysia 2026 Job Market Outlook & Salary Guide (as cited on the page)', 'date_published': pub and pub[1], 'date_modified': mod and mod[1],
               'page_sha256_16': hashlib.sha256(raw.encode()).hexdigest()[:16], 'method': 'HTML table read', 'footnote': foot and foot[0], 'rows': len(rows), 'unparsed_rows': bad,
               'checks': {'min_below_max': all(r['min_rm_per_month'] < r['max_rm_per_month'] for r in rows)},
               'licence': 'Not stated. Kept local; not committed.'}, open(os.path.join(a.out, 'manifest.json'), 'w'), indent=1, ensure_ascii=False)
    print('%d rows, %d unparsed' % (len(rows), len(bad)), file=sys.stderr)


if __name__ == '__main__':
    main()
