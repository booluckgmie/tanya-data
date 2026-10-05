"""Ministry of Health adapter: the open-data repositories under github.com/MoH-Malaysia.

Currently indexes two public repositories:
  - covid19-public     documented CSVs (epidemic, vaccination, mysejahtera, static)
  - data-darah-public  blood donation and new-donor files

One registry record per CSV. Metadata only: column names and the date span are read
from each file so the record can say what it covers; no values are stored.
The individual-level case line-lists under epidemic/linelist are not indexed.
Standard library only.
"""
import csv, os, re, subprocess

ORG = 'https://github.com/MoH-Malaysia'
RAW = 'https://raw.githubusercontent.com/MoH-Malaysia'
REPOS = ['covid19-public', 'data-darah-public']
PORTAL_PAGE = ORG
COVID_LICENCE = {
    'name': 'Open Data Implementation Circular (Pekeliling Pelaksanaan Data Terbuka Bil.1/2015), Appendix B',
    'url': 'https://www.data.gov.my/p/pekeliling-data-terbuka',
    'basis': 'LICENSE.md in the repository',
}
# Files the main README does not list. Descriptions are written from the column names.
EXTRA = {
    'epidemic/cases_age.csv': 'Weekly COVID-19 cases by age group at state level, as counts and percentages.',
    'epidemic/deaths_age.csv': 'Weekly COVID-19 deaths by age group at state level, as counts and percentages.',
    'vaccination/aefi.csv': 'Daily adverse events following immunisation (AEFI) reported, by vaccine type and severity.',
    'vaccination/aefi_serious.csv': 'Daily serious adverse events following immunisation, by vaccine type and event type.',
    'vaccination/vax_booster_combos.csv': 'Daily booster dose combinations by vaccine brand, at district level.',
    'vaccination/vax_outcomes_capita.csv': 'Cases and deaths per capita by vaccination status, by state and date.',
    'vaccination/vax_snapshot.csv': 'Latest vaccination snapshot by state, age group and dose.',
}
BLOOD = {
    'donations_facility.csv': 'Daily blood donations by hospital or blood collection facility, split by blood group, collection location, donation type, donor background and donor history.',
    'donations_state.csv': 'Daily blood donations by state, split by blood group, collection location, donation type, donor background and donor history.',
    'newdonors_facility.csv': 'Daily new blood donors by hospital or blood collection facility, by age group.',
    'newdonors_state.csv': 'Daily new blood donors by state, by age group.',
}
RELATED = {
    'covid19-public': ['dash:covid_epid', 'dash:covid_vax'],
    'data-darah-public': ['blood_donations', 'blood_donations_state', 'dash:blood_donation'],
}
DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}')


def ensure_repo(name, base):
    dest = os.path.join(base, name)
    if os.path.isdir(os.path.join(dest, '.git')):
        subprocess.run(['git', '-C', dest, 'pull', '-q', '--ff-only'], check=False)
    else:
        os.makedirs(base, exist_ok=True)
        env = dict(os.environ, GIT_LFS_SKIP_SMUDGE='1')
        subprocess.run(['git', 'clone', '-q', '--depth', '1', '%s/%s.git' % (ORG, name), dest], check=True, env=env)
    return dest


def branch_of(dest):
    return subprocess.run(['git', '-C', dest, 'rev-parse', '--abbrev-ref', 'HEAD'], capture_output=True, text=True).stdout.strip() or 'main'


def scan(path):
    """-> (columns, first date, last date, date column) read from a CSV."""
    with open(path, newline='', encoding='utf-8-sig') as f:
        rd = csv.reader(f)
        cols = [c.strip() for c in next(rd)]
        di = next((i for i, c in enumerate(cols) if c in ('date', 'week')), None)
        lo = hi = None
        if di is not None:
            for row in rd:
                v = row[di] if di < len(row) else ''
                if DATE_RE.match(v):
                    v = v[:10]
                    lo = v if lo is None or v < lo else lo
                    hi = v if hi is None or v > hi else hi
    return cols, lo, hi, (cols[di] if di is not None else None)


def readme_files(readme):
    """README bullets like: 1) [`cases_malaysia.csv`](/epidemic/cases_malaysia.csv): description"""
    out = {}
    for m in re.finditer(r"\[`([\w.-]+\.csv)`'?\]\((/[\w./-]+)\)\s*[^:\n]*:\s*(.+)", readme):
        out.setdefault(m.group(1), m.group(3).strip())
    return out


BLOOD_TITLES = {
    'donations_facility.csv': 'Daily blood donations by facility',
    'donations_state.csv': 'Daily blood donations by state',
    'newdonors_facility.csv': 'Daily new blood donors by facility and age group',
    'newdonors_state.csv': 'Daily new blood donors by state and age group',
}


def title_from(desc, fname):
    """First clause of the description, keeping its 'at country/state/district level' scope."""
    if fname in BLOOD_TITLES:
        return BLOOD_TITLES[fname]
    t = re.sub(r'\s*\([^)]*\)', '', desc)  # drop parentheticals, keep the scope words after them
    t = re.split(r'\s*[:,]|\.\s|\.$', t)[0].strip(' .')
    if len(t) > 90:
        t = t[:90].rsplit(' ', 1)[0]
    return t[0].upper() + t[1:] if t else fname


def build_moh(ag, infer_keys, base, log):
    agencies, tier, basis = ag.resolve(['moh'])
    out = []
    for repo in REPOS:
        dest = ensure_repo(repo, base)
        branch = branch_of(dest)
        licence = COVID_LICENCE if os.path.exists(os.path.join(dest, 'LICENSE.md')) else None
        files = {}  # relative path -> (description, description basis)
        if repo == 'covid19-public':
            desc = readme_files(open(os.path.join(dest, 'README.md'), encoding='utf-8').read())
            for name, d in desc.items():
                for folder in ('epidemic', 'vaccination', 'mysejahtera', 'static'):
                    if os.path.exists(os.path.join(dest, folder, name)):
                        files[folder + '/' + name] = (d, 'repository README')
                        break
            for rel, d in EXTRA.items():
                if os.path.exists(os.path.join(dest, rel)):
                    files[rel] = (d, 'written from the column names')
        else:
            for name, d in BLOOD.items():
                if os.path.exists(os.path.join(dest, name)):
                    files[name] = (d, 'written from the column names; the repository has no README')
        for rel, (d, dbasis) in sorted(files.items()):
            cols, lo, hi, dcol = scan(os.path.join(dest, rel))
            columns = [{'name': c, 'title': '', 'description': ''} for c in cols]
            keys, geo_inf = infer_keys(columns)
            name = os.path.basename(rel)
            if '_malaysia' in name or name in ('population.csv',):
                geo = ['NATIONAL']
            else:
                geo = []
            freq = 'WEEKLY' if dcol == 'week' else 'DAILY' if dcol == 'date' else 'UNKNOWN'
            pretty = title_from(d, name)
            out.append({
                'kind': 'dataset', 'id': 'moh:%s:%s' % (repo, name[:-4]),
                'title': {'en': pretty, 'ms': pretty},
                'description': {'en': d, 'ms': ''},
                'category': {'en': 'Healthcare', 'ms': 'Kesihatan', 'sub': 'MOH open data (GitHub)'},
                'portals': ['mohgithub'], 'agencies': agencies, 'tier': tier, 'tier_basis': basis,
                'access': [{'type': 'csv', 'url': '%s/%s/%s/%s' % (RAW, repo, branch, rel)}],
                'pages': [{'portal': 'mohgithub', 'url': '%s/%s/blob/%s/%s' % (ORG, repo, branch, rel)}],
                'licence': licence, 'frequency': freq, 'frequency_inferred': True,
                'geography': geo, 'geography_inferred': [g for g in geo_inf if g not in geo],
                'demography': [], 'coverage': {'begin': int(lo[:4]) if lo else None, 'end': int(hi[:4]) if hi else None},
                'data_as_of': hi, 'last_updated': None, 'next_update': None,
                'columns': columns, 'join_keys': keys, 'methodology': '',
                'caveats': ('Description %s. ' % dbasis) +
                           ('This repository is a published snapshot; check the date range before relying on it as current.' if repo == 'covid19-public' else 'Check the date range and the repository for updates.'),
                'related': RELATED[repo], 'see_also': [], 'source_agencies_raw': ['MOH'],
            })
        log('MOH %s: %d files' % (repo, len(files)))
    return out
