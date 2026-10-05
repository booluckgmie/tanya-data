"""HTTP via curl. Python's ssl module is rejected by some official hosts (for example
api.bnm.gov.my answers curl but fails the TLS handshake from urllib), and curl already
honours the proxy and CA bundle in the environment. TLS verification stays on."""
import subprocess


def curl(url, headers=None, timeout=40, method='GET', range0=False):
    """-> (status int, body bytes). status 0 means no response."""
    cmd = ['curl', '-sS', '-L', '-m', str(timeout), '-o', '-', '-w', '\n%{http_code}']
    if method == 'HEAD':
        cmd = ['curl', '-sS', '-L', '-I', '-m', str(timeout), '-o', '/dev/null', '-w', '%{http_code}']
    if range0:
        cmd += ['-r', '0-0']
    for k, v in (headers or {}).items():
        cmd += ['-H', '%s: %s' % (k, v)]
    p = subprocess.run(cmd + [url], capture_output=True)
    out = p.stdout
    if method == 'HEAD':
        return (int(out.strip() or 0), b'')
    body, _, code = out.rpartition(b'\n')
    try:
        return int(code), body
    except ValueError:
        return 0, b''


def curl_json(url, headers=None, timeout=40):
    import json
    st, body = curl(url, headers, timeout)
    if st != 200:
        raise IOError('HTTP %s for %s' % (st, url))
    return json.loads(body)
