"""Read-only chart viewer. Serves only this UI and dataset-tagged FHIR records."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
from urllib.parse import urlparse
import requests
from prepare import DATASET, SYSTEM

ROOT = Path(__file__).resolve().parent

class Handler(BaseHTTPRequestHandler):
    def reply(self, status, data, kind='application/json'):
        raw = data if isinstance(data, bytes) else json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(raw)

    def fhir(self, path, params=None):
        with requests.Session() as session:
            session.trust_env = False
            result = session.get(self.server.fhir+'/'+path, params=params, timeout=30)
            result.raise_for_status()
            return result.json()

    def do_GET(self):
        path = urlparse(self.path).path
        try:
            if path == '/':
                return self.reply(200, (ROOT/'index.html').read_bytes(), 'text/html; charset=utf-8')
            if path == '/api/patients':
                patients = []
                # Explicit paging using the server's continuation URL, constrained
                # to the configured FHIR origin.
                result = self.fhir('Patient', {'_tag': SYSTEM+'/dataset|'+DATASET, '_count': 1000})
                while True:
                    patients.extend(e['resource'] for e in result.get('entry', []) if e.get('resource', {}).get('resourceType') == 'Patient')
                    nxt = next((l['url'] for l in result.get('link', []) if l['relation'] == 'next'), None)
                    if not nxt:
                        break
                    parsed = urlparse(nxt)
                    base = urlparse(self.server.fhir)
                    if parsed.netloc != base.netloc or not parsed.path.startswith(base.path+'/'):
                        raise ValueError('Unexpected pagination target')
                    result = self.fhir(parsed.path[len(base.path)+1:]+'?'+parsed.query)
                return self.reply(200, sorted(patients, key=lambda p:p['id']))
            match = re.fullmatch(r'/api/chart/(mxq-\d{4})', path)
            if match:
                pid = match[1]
                paths = ['Patient/'+pid, 'Encounter/'+pid+'-visit', 'Practitioner/'+pid+'-doctor',
                         'Organization/'+pid+'-hospital', 'DocumentReference/'+pid+'-note']
                with ThreadPoolExecutor(max_workers=5) as pool:
                    resources = list(pool.map(self.fhir, paths))
                for resource in resources:
                    if not any(t.get('system') == SYSTEM+'/dataset' and t.get('code') == DATASET for t in resource.get('meta', {}).get('tag', [])):
                        return self.reply(404, {'error':'Chart not in this dataset'})
                return self.reply(200, {r['resourceType']:r for r in resources})
            self.reply(404, {'error':'Not found'})
        except Exception:
            self.reply(502, {'error':'Unable to read chart from FHIR. Check that the EHR containers are running and cases have been ingested.'})

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--fhir', default='http://localhost:8080/fhir')
    p.add_argument('--port', type=int, default=8090)
    p.add_argument('--host', default='127.0.0.1')
    args = p.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.fhir = args.fhir.rstrip('/')
    print(f'EHR viewer: http://{args.host}:{args.port}', flush=True)
    server.serve_forever()
