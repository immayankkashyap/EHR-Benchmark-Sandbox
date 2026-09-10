#!/usr/bin/env python3
"""One entry point for setup, model runs, smoke checks and offline scoring."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT/'.venv/bin/python'
COMPOSE = ['docker','compose','-f','docker-compose.yml','-f','benchmark-ehr/compose.yml']


def execute(args, check=True):
    return subprocess.run([str(a) for a in args], cwd=ROOT, check=check)


def setup():
    if not PYTHON.exists():
        execute([sys.executable,'-m','venv',ROOT/'.venv'])
    execute([PYTHON,'-m','pip','install','-r','benchmark-ehr/requirements.txt'])
    execute([PYTHON,'benchmark-ehr/prepare.py','medxpertqa_salted_500_curated.pdf'])
    execute([PYTHON,'benchmark-scoring/build_key.py','medxpertqa_salted_500_curated.pdf'])
    execute(COMPOSE+['up','-d','--build','ehr-viewer'])
    deadline = time.monotonic()+180
    while time.monotonic()<deadline:
        try:
            with urlopen('http://localhost:8090/api/patients', timeout=5) as response:
                json.load(response)
            break
        except Exception:
            time.sleep(2)
    else:
        raise SystemExit('EHR startup timed out. Inspect docker compose logs and rerun setup.')
    execute(COMPOSE+['exec','-T','ehr-viewer','python','ingest.py','--fhir','http://hapi-fhir-jpaserver:8080/fhir','--data','/data'])
    print('Ready. Open http://localhost:8090 or run: python3 scripts/benchmark.py smoke')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['setup','smoke','run','score'])
    args, rest = parser.parse_known_args()
    if args.command == 'setup':
        if rest:
            parser.error('setup takes no extra arguments')
        return setup()
    if not PYTHON.exists():
        parser.error('Run setup first')
    if args.command == 'score':
        return execute([PYTHON,'benchmark-scoring/score.py',*rest])
    options = argparse.ArgumentParser()
    options.add_argument('--output', type=Path)
    known, forwarded = options.parse_known_args(rest)
    if '--logs' in forwarded or any(x.startswith('--logs=') for x in forwarded):
        parser.error('Use --output rather than --logs with this wrapper')
    output = known.output or Path('evaluation-private/runs')/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    if not output.is_absolute():
        output = ROOT/output
    command = [PYTHON,'benchmark-runner/run.py','--logs',output/'logs']
    if args.command == 'smoke':
        command += ['--smoke']
        if not any(x == '--cases' or x.startswith('--cases=') for x in forwarded):
            command += ['--cases','1-3']
    result = execute(command+forwarded, check=False)
    if (output/'logs').exists() and any((output/'logs').glob('*.jsonl')):
        execute([PYTHON,'benchmark-scoring/score.py','--logs',output/'logs','--output',output/'report.json'])
    if result.returncode:
        raise SystemExit(result.returncode)

if __name__ == '__main__':
    main()
