"""Extract question-only notes. Never serialize the PDF's answer sections."""
import argparse
import base64
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import re
from pypdf import PdfReader

DATASET = 'patient-only-v2'
SYSTEM = 'http://healthcare-ehr-sandbox.local/tags'

def extract(text, expected=500):
    parts = re.split(r'(?m)^Question (\d+) \(Source: ([^\n]+)\)\n', text)
    if (len(parts)-1)//3 != expected:
        raise ValueError('Unexpected question count; refusing partial extraction')
    questions = []
    for offset in range(1, len(parts), 3):
        number, source, block = parts[offset:offset+3]
        # Metadata and answer key are outside the original question. A wrapped
        # answer is removed in full by ending at the start of its marker.
        start = re.search(r'(?m)^Salted:[^\n]*\n', block)
        ends = list(re.finditer(r'(?m)^Answer:', block))
        if not start or len(ends) != 1 or ends[0].start() <= start.end():
            raise ValueError(f'Question {number}: unexpected boundaries')
        question = block[start.end():ends[0].start()]
        if not question.strip() or not re.search(r'(?m)^\s*J\. ', question):
            raise ValueError(f'Question {number}: incomplete choices')
        questions.append({'number': int(number), 'question': question,
                          'sha256': hashlib.sha256(question.encode()).hexdigest()})
    if [q['number'] for q in questions] != list(range(1, expected+1)):
        raise ValueError('Missing or duplicate question numbers')
    return questions

def bundle(q, clinical_note="No reviewed clinical note is available."):
    n = q['number']
    pid = f'mxq-{n:04d}'
    visit = (date(2025, 1, 1) + timedelta(days=(n-1)%365)).isoformat()+'T09:00:00Z'
    doctor = f'{pid}-doctor'
    meta = {'tag': [{'system': SYSTEM+'/dataset', 'code': DATASET},
                    {'system': SYSTEM+'/task_id', 'code': pid},
                    {'system': SYSTEM+'/data-origin', 'code': 'synthetic-administrative-metadata'}]}
    def resource(kind, rid, **fields):
        return {'resourceType': kind, 'id': rid, 'meta': meta, **fields}
    patient = resource('Patient', pid, identifier=[{'system': SYSTEM+'/mrn', 'value': pid.upper()}],
                       name=[{'text': f'Synthetic Patient {n:04d}'}])
    practitioner = resource('Practitioner', doctor, name=[{'text': f'Dr. Alex Morgan {n:04d} (synthetic)'}])
    org = resource('Organization', pid+'-hospital', name='Benchmark General Hospital (synthetic)')
    encounter = resource('Encounter', pid+'-visit', status='in-progress',
                         **{'class': {'system': 'http://terminology.hl7.org/CodeSystem/v3-ActCode', 'code': 'VR', 'display': 'virtual'}},
                         subject={'reference': 'Patient/'+pid}, period={'start': visit},
                         participant=[{'individual': {'reference': 'Practitioner/'+doctor}}],
                         serviceProvider={'reference': 'Organization/'+pid+'-hospital'})
    note = resource('DocumentReference', pid+'-note', status='current',
                    type={'text': 'Reviewed patient note'}, subject={'reference': 'Patient/'+pid},
                    date=visit, author=[{'reference': 'Practitioner/'+doctor}],
                    context={'encounter': [{'reference': 'Encounter/'+pid+'-visit'}]},
                    content=[{'attachment': {'contentType': 'text/plain; charset=utf-8',
                              'title': 'Patient clinical note',
                              'data': base64.b64encode(clinical_note.encode()).decode()}}])
    resources = [patient, practitioner, org, encounter, note]
    return {'resourceType': 'Bundle', 'type': 'transaction', 'entry': [
        {'resource': r, 'request': {'method': 'PUT', 'url': r['resourceType']+'/'+r['id']}}
        for r in resources]}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('pdf', type=Path)
    parser.add_argument('--tasks', type=Path, default=Path('benchmark-tasks'))
    parser.add_argument('--output', type=Path, default=Path('benchmark-ehr/generated'))
    args = parser.parse_args()
    questions = extract('\n'.join(p.extract_text() for p in PdfReader(args.pdf).pages))
    args.output.mkdir(parents=True, exist_ok=True)
    args.tasks.mkdir(parents=True, exist_ok=True)
    manifest = {'dataset': DATASET,
                'count': len(questions), 'cases': []}
    for q in questions:
        pid = f"mxq-{q['number']:04d}"
        (args.tasks/(pid+'.json')).write_text(json.dumps({'patient_id': pid, 'question': q['question']})+'\n')
        (args.output/(pid+'.json')).write_text(json.dumps(bundle(q), ensure_ascii=False, indent=2)+'\n')
        manifest['cases'].append({'id': pid, 'number': q['number']})
    (args.output/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(f'Prepared {len(questions)} question-only FHIR bundles')

if __name__ == '__main__':
    main()
