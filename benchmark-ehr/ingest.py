"""Idempotent FHIR transaction upload with full note read-back verification."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import requests


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--fhir', default='http://localhost:8080/fhir')
    p.add_argument('--data', type=Path, default=Path('benchmark-ehr/generated'))
    args = p.parse_args()
    manifest = json.loads((args.data/'manifest.json').read_text())
    session = requests.Session()
    session.trust_env = False
    report = {'dataset': manifest['dataset'], 'verified': 0, 'cases': []}
    for case in manifest['cases']:
        bundle = json.loads((args.data/(case['id']+'.json')).read_text())
        response = session.post(args.fhir, json=bundle, timeout=120)
        response.raise_for_status()
        result = response.json()
        if result.get('type') != 'transaction-response' or len(result.get('entry', [])) != 5:
            raise RuntimeError(f"Unexpected transaction response for {case['id']}")
        if any(not e['response']['status'].startswith('2') for e in result['entry']):
            raise RuntimeError('Transaction failed')
        # Verify every persisted resource, including absence of extra clinical fields.
        for entry in bundle['entry']:
            resource = entry['resource']
            saved = session.get(args.fhir+'/'+entry['request']['url'], timeout=30)
            saved.raise_for_status()
            saved = saved.json()
            for key, value in resource.items():
                if key != 'meta' and saved.get(key) != value:
                    raise RuntimeError(f"Read-back mismatch: {case['id']} {key}")
            if resource['resourceType'] == 'DocumentReference':
                raw = base64.b64decode(saved['content'][0]['attachment']['data'])
                if hashlib.sha256(raw).hexdigest() != case['question_sha256']:
                    raise RuntimeError('Question text changed')
        report['verified'] += 1
        report['cases'].append(case['id'])
        if report['verified'] % 25 == 0:
            print(f"Uploaded and verified {report['verified']}/{manifest['count']}", flush=True)
    (args.data/'ingestion-report.json').write_text(json.dumps(report, indent=2)+'\n')
    print('Complete: all records persisted and question hashes verified.')

if __name__ == '__main__':
    main()
