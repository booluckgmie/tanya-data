"""Department of Environment (DOE) adapter: the public APIMS air pollutant index endpoint.

https://eqms.doe.gov.my/api3/publicportalapims/apitablehourly returns the last 24 hours of the Air
Pollutant Index (API) for every monitoring station, as JSON, without authentication. It is the endpoint
the DOE public portal itself calls. It is not described in any published API documentation, so the
record says that. One request reads the column names and the size of the window; no values are stored.
Standard library only.
"""
import json
from net import curl

URL = 'https://eqms.doe.gov.my/api3/publicportalapims/apitablehourly'
PORTAL = 'https://eqms.doe.gov.my/'


def build_doe(ag, infer_keys, log):
    agencies, tier, basis = ag.resolve(['jas'])
    st, body = curl(URL, timeout=60)
    cols, stations, hours, rows = [], None, None, None
    if st == 200:
        try:
            rows = json.loads(body).get('api_table_hourly') or []
            cols = [c for c in (rows[0] if rows else {}) if not c.startswith('PAGE')]
            stations = len({r.get('STATION_ID') for r in rows})
            hours = len({r.get('DATETIME') for r in rows})
        except ValueError:
            pass
    if not cols:
        log('doe: could not read the APIMS endpoint (HTTP %s); record kept without columns' % st)
    columns = [{'name': c.lower(), 'title': '', 'description': ''} for c in cols]
    keys, geo_inf = infer_keys(columns)
    window = ('The endpoint returned %d rows when read: %d stations over the last %d hours. ' % (len(rows), stations, hours)) if rows else ''
    rec = {
        'kind': 'live_api', 'id': 'api:apims_hourly',
        'title': {'en': 'Hourly Air Pollutant Index by station, last 24 hours (DOE APIMS public API)',
                  'ms': 'Indeks Pencemaran Udara setiap jam mengikut stesen, 24 jam terkini (API awam APIMS JAS)'},
        'description': {'en': 'The Air Pollutant Index (API) for each air quality monitoring station in Malaysia, hour by hour for the last 24 hours, from the Department of Environment public portal. Current readings only; for history use the archive copy or the monthly air pollution dataset.',
                        'ms': 'Indeks Pencemaran Udara (IPU) bagi setiap stesen pemantauan kualiti udara di Malaysia, setiap jam bagi 24 jam terakhir, daripada portal awam Jabatan Alam Sekitar. Bacaan semasa sahaja.'},
        'category': {'en': 'Environment', 'ms': 'Alam Sekitar', 'sub': 'Live API'},
        'portals': ['doeapims'], 'agencies': agencies, 'tier': tier, 'tier_basis': basis,
        'access': [{'type': 'api', 'label': 'API: hourly index (JSON)', 'url': URL}],
        'pages': [{'portal': 'doeapims', 'url': PORTAL}],
        'licence': None, 'frequency': 'HOURLY', 'geography': [], 'geography_inferred': list(dict.fromkeys(['STATE'] + geo_inf)),
        'demography': [], 'coverage': {'begin': None, 'end': None}, 'data_as_of': None, 'last_updated': None, 'next_update': None,
        'columns': columns, 'join_keys': keys, 'methodology': '',
        'caveats': ('An undocumented endpoint: it is what the DOE public portal calls (its CORS rule allows only the portal origin). '
                    'There is no published schema, terms or rate limit, and it may change without notice. ' + window +
                    'The old APIMS address (apims.doe.gov.my) no longer resolves. Station state is given as a numeric state id.'),
        'related': ['sharecode:apims_hourly', 'air_pollution'], 'see_also': [], 'source_agencies_raw': ['JAS'],
    }
    log('doe: APIMS live API record (%s)' % ('%d stations, %d hours' % (stations, hours) if rows else 'unread'))
    return [rec]
