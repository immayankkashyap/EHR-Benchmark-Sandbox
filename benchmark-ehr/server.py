"""Serve an immutable patient-only snapshot; never proxy the mutable FHIR database."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
from prepare import bundle

ROOT = Path(__file__).resolve().parent


def load_charts(directory):
    charts = {}
    for path in sorted(directory.glob('mxq-*.json')):
        if path.is_symlink() or not re.fullmatch(r'mxq-\d{4}', path.stem):
            raise ValueError('Invalid chart file')
        number = int(path.stem[4:])
        if not 1 <= number <= 500:
            raise ValueError('Invalid patient number')
        data = json.loads(path.read_text())
        # Fail closed on legacy question notes, extra fields, encoded attachments,
        # extensions, URLs, narratives, answer keys and modified metadata alike.
        if data != bundle({'number': number}):
            raise ValueError('Chart is not an approved patient-only snapshot: '+path.name)
        charts[path.stem] = {e['resource']['resourceType']: e['resource'] for e in data['entry']}
    if not charts:
        raise ValueError('No patient-only charts loaded')
    return charts


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, data, kind='application/json'):
        raw = data if isinstance(data, bytes) else json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == '/':
            return self.reply(200, (ROOT/'index.html').read_bytes(), 'text/html; charset=utf-8')
        if self.path == '/api/patients':
            return self.reply(200, [v['Patient'] for v in self.server.charts.values()])
        match = re.fullmatch(r'/api/chart/(mxq-\d{4})', self.path)
        if match and match[1] in self.server.charts:
            return self.reply(200, self.server.charts[match[1]])
        self.reply(404, {'error': 'Not found'})


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--data', type=Path, default=Path('/data'))
    p.add_argument('--port', type=int, default=8090)
    p.add_argument('--host', default='127.0.0.1')
    args = p.parse_args()
    charts = load_charts(args.data)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.charts = charts
    server.serve_forever()
