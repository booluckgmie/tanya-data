"""Malaysian Palm Oil Board (MPOB) adapter: the public pages of bepi.mpob.gov.my (Economics and
Industry Development Division).

URL patterns found on the site (all public, no login):
  daily CPO price, HTML table   /admin2/price_local_daily_view_cpo_msia.php?more=Y&jenis={1W|1M|3M|6M|1Y}[&tahun=YYYY]
  daily CPO price, chart page   /admin2/chart_cpomsia.php?jenis={1W|1M|3M|6M|1Y}&tahun=YYYY
  daily CPO price, Excel        /admin2/price_local_daily_view_cpo_msia_excel.php?val=YYYY&excel=Y
  monthly industry performance  /stat/web_report1.php?val=<id>&val1=<MM>   (latest month only)
  annual overview report        /images/overview/Overview_of_Industry_YYYY.pdf (2016-2020), Overview{YYYY}.pdf (2021 on)
Daily is the finest granularity MPOB publishes here. Only the latest three years answer; earlier
years return an empty file. price.mpob.gov.my and the export duties page need a login and are left alone.

Which years answer is probed at harvest time, and report links are read from the live pages. Metadata
only: no prices or report figures are stored. Standard library only.
"""
import html, re
from datetime import date, datetime
from net import curl

BASE = 'https://bepi.mpob.gov.my'
PRICE = BASE + '/admin2/price_local_daily_view_cpo_msia.php?more=Y&jenis=%s'
EXCEL = BASE + '/admin2/price_local_daily_view_cpo_msia_excel.php?val=%d&excel=Y'
MONTHS = ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december']


def get_text(url, timeout=60):
    st, body = curl(url, timeout=timeout)
    return st, body.decode('utf-8', 'replace')


def text_of(page):
    b = re.sub(r'<script.*?</script>|<style.*?</style>', '', page, flags=re.S)
    t = html.unescape(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' | ', b)))
    return re.sub(r'(\| )+', '| ', t)


def year_has_data(y):
    """The Excel export answers with a spreadsheet for years MPOB still serves, and an empty body otherwise."""
    st, body = curl(EXCEL % y, timeout=60)
    return st == 200 and body[:2] == b'PK'


def parse_latest_price_date(page):
    m = re.search(r'Latest Price:\s*(\d{1,2}) ([A-Za-z]+) (\d{4})', text_of(page))
    if not m:
        return None
    try:
        return datetime.strptime('%s %s %s' % m.groups(), '%d %B %Y').date().isoformat()
    except ValueError:
        return None


def report_via_item(section):
    """Monthly-release and summary pages link to one item that embeds a stat report in an iframe."""
    st, page = get_text('%s/index.php/%s' % (BASE, section))
    items = re.findall(r'href="(/index\.php/%s/\d+-[^"#]+/\d+-[^"#]+)"' % re.escape(section), page)
    if st != 200 or not items:
        return None
    item = BASE + html.unescape(items[0])
    st, ipage = get_text(item)
    m = re.search(r'<iframe[^>]*src="([^"]*web_report[^"]+)"', ipage)
    if st != 200 or not m:
        return None
    rurl = BASE + '/stat/' + html.unescape(m.group(1)).split('/stat/')[-1]
    st, rpage = get_text(rurl)
    if st != 200:
        return None
    t = text_of(rpage)
    title = re.search(r'((?:PERFORMANCE OF|SUMMARY OF) THE MALAYSIAN PALM OIL INDUSTRY[^|]*?\d{4})', t)
    return {'item': item, 'report': rurl, 'title': title.group(1).strip() if title else None, 'text': t}


def overview_links(page):
    out = {}
    for href, inner in re.findall(r'<a[^>]*href="([^"]*[Oo]verview[^"]*\.pdf)"[^>]*>(.*?)</a>', page, re.S):
        y = re.sub(r'<[^>]+>', '', inner).strip()
        if re.fullmatch(r'20\d{2}', y):
            out[int(y)] = href if href.startswith('http') else BASE + href
    return out


def rec(rid, kind, title_en, title_ms, desc_en, desc_ms, agencies, tier, basis, pages, access, freq, cov, asof, cav, cols=(), related=(), extra=None):
    r = {
        'kind': kind, 'id': rid, 'title': {'en': title_en, 'ms': title_ms}, 'description': {'en': desc_en, 'ms': desc_ms},
        'category': {'en': 'Agriculture', 'ms': 'Pertanian', 'sub': 'Palm oil (MPOB)'},
        'portals': ['mpob'], 'agencies': agencies, 'tier': tier, 'tier_basis': basis, 'access': access, 'pages': pages,
        'licence': None, 'frequency': freq, 'frequency_inferred': False, 'geography': ['NATIONAL'], 'geography_inferred': [], 'demography': [],
        'coverage': {'begin': cov[0], 'end': cov[1]}, 'data_as_of': asof, 'last_updated': None, 'next_update': None,
        'columns': [{'name': c, 'title': '', 'description': ''} for c in cols], 'join_keys': [], 'methodology': '', 'caveats': cav,
        'related': list(related), 'see_also': [], 'source_agencies_raw': ['MPOB'],
    }
    if kind == 'publication':
        r.update({'releases': [], 'methodology_docs': []})
    if extra:
        r.update(extra)
    return r


def build_mpob(ag, log):
    agencies, tier, basis = ag.resolve(['mpob'])
    out, notes = [], []
    # --- daily CPO price
    st, page = get_text(PRICE % '1W')
    thisyear = date.today().year
    years = [y for y in range(thisyear, thisyear - 8, -1) if year_has_data(y)]
    if st == 200 and years:
        asof = parse_latest_price_date(page)
        access = [{'type': 'excel', 'label': 'Excel: %d (daily prices, calendar layout)' % y, 'url': EXCEL % y} for y in years]
        access += [{'type': 'web', 'label': 'Table: %s' % lbl, 'url': PRICE % code} for lbl, code in (('last week', '1W'), ('last month', '1M'), ('last 3 months', '3M'), ('last 6 months', '6M'))]
        out.append(rec('mpob:cpo_daily_price', 'dataset',
            'Crude palm oil (CPO) daily price, Malaysia, local delivered (MPOB)', 'Harga harian minyak sawit mentah (CPO), Malaysia, hantaran tempatan (MPOB)',
            'Daily Malaysian price of crude palm oil, local delivered, in RM per tonne, published by the Malaysian Palm Oil Board. The site gives a table or chart for the last week, month, 3 months, 6 months or a whole year, and an Excel file per year. Daily is the finest granularity published; there is no regional or grade breakdown on these pages.',
            'Harga harian minyak sawit mentah Malaysia, hantaran tempatan, dalam RM setiap tan, diterbitkan oleh Lembaga Minyak Sawit Malaysia.',
            agencies, tier, basis, [{'portal': 'mpob', 'url': PRICE % '1W'}], access, 'DAILY', (min(years), max(years)), asof,
            'Only the last %d years answer (%s); earlier years return an empty file, so history before %d is not available from MPOB here. The Excel file is a calendar layout (days down, months across). PH marks a public holiday and NT a day with no trading. URL pattern: ?more=Y&jenis={1W|1M|3M|6M|1Y}&tahun=YYYY for tables, and price_local_daily_view_cpo_msia_excel.php?val=YYYY&excel=Y for Excel.' % (len(years), ', '.join(str(y) for y in sorted(years)), min(years)),
            ['day'] + MONTHS, related=['sharecode:mpob_cpo_daily']))
        notes.append('daily price: years %s, latest %s' % (sorted(years), asof))
    else:
        notes.append('daily price page not readable (HTTP %s)' % st)
    # --- monthly performance and summary reports
    for section, rid, en, ms, desc, freq in (
        ('monthly-release', 'mpob:monthly_performance', 'Performance of the Malaysian palm oil industry: monthly release (MPOB)', 'Prestasi industri minyak sawit Malaysia: keluaran bulanan (MPOB)',
         'MPOB monthly release on the palm oil industry: crude palm oil production by Peninsular Malaysia, Sabah and Sarawak, palm kernel products, stocks, exports and imports, with the change from the previous month.', 'MONTHLY'),
        ('summary-2', 'mpob:industry_summary', 'Summary of the Malaysian palm oil industry (MPOB, current year)', 'Ringkasan industri minyak sawit Malaysia (MPOB, tahun semasa)',
         'MPOB summary of the Malaysian palm oil industry for the current year, as a web report.', 'YEARLY')):
        rep = report_via_item(section)
        if not rep:
            notes.append('%s: report not found' % section)
            continue
        ym = re.search(r'(\d{4})', rep['title'] or '')
        mon = next((i + 1 for i, m in enumerate(MONTHS) if rep['title'] and m.upper() in rep['title'].upper()), None)
        y = int(ym.group(1)) if ym else None
        asof = ('%d-%02d-28' % (y, mon)) if (y and mon) else None
        if asof:
            nxt = date(y + (mon == 12), mon % 12 + 1, 1)
            asof = date.fromordinal(nxt.toordinal() - 1).isoformat()
        out.append(rec(rid, 'dataset', en, ms, desc, desc, agencies, tier, basis, [{'portal': 'mpob', 'url': '%s/index.php/%s' % (BASE, section)}],
            [{'type': 'web', 'label': 'Latest report: %s' % (rep['title'] or section), 'url': rep['report']}], freq, (y, y), asof,
            'Only the latest %s is published on this site; earlier ones return "under construction", so there is no public archive here. The report URL (stat/web_report1.php?val=<id>&val1=<MM>) changes with each release and cannot be derived for other months.' % ('month' if freq == 'MONTHLY' else 'edition'),
            related=['mpob:cpo_daily_price']))
        notes.append('%s: %s' % (section, rep['title']))
    # --- annual overview of the industry
    st, page = get_text(BASE + '/index.php/monthly-release')
    links = overview_links(page) if st == 200 else {}
    live = {}
    for y, u in sorted(links.items()):
        s2, _ = curl(u, timeout=60, method='HEAD')
        if s2 == 200:
            live[y] = u
    if live:
        hist = [{'date': None, 'title': 'Overview of the Malaysian Oil Palm Industry %d' % y, 'url': live[y]} for y in sorted(live, reverse=True)]
        out.append(rec('mpob:overview_of_industry', 'publication', 'Overview of the Malaysian Oil Palm Industry (MPOB annual report)', 'Tinjauan industri sawit Malaysia (laporan tahunan MPOB)',
            'MPOB annual report reviewing the Malaysian oil palm industry for the year: production, trade, prices and developments. One PDF per year, %d to %d.' % (min(live), max(live)),
            'Laporan tahunan MPOB mengenai industri sawit Malaysia. Satu PDF setiap tahun.',
            agencies, tier, basis, [{'portal': 'mpob', 'url': BASE + '/index.php/monthly-release'}],
            [{'type': 'pdf', 'label': 'Overview %d' % y, 'url': live[y]} for y in sorted(live, reverse=True)], 'YEARLY', (min(live), max(live)), None,
            'The year in each title is the report year. Release dates are not shown on the site. File names changed in 2021 (Overview_of_Industry_YYYY.pdf before, OverviewYYYY.pdf after), so the links are read from the site menu.',
            related=['mpob:cpo_daily_price'], extra={'history': hist, 'archive_url': BASE + '/index.php/monthly-release'}))
        notes.append('overview: %d PDFs %d-%d' % (len(live), min(live), max(live)))
    else:
        notes.append('overview PDFs not found')
    log('mpob: ' + '; '.join(notes))
    return out
