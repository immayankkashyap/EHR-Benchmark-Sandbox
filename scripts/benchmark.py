#!/usr/bin/env python3
"""One entry point for setup, model runs, smoke checks and offline scoring."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT/'.venv/bin/python'
COMPOSE = ['docker','compose','-f','docker-compose.yml']


def execute(args, check=True):
    return subprocess.run([str(a) for a in args], cwd=ROOT, check=check)


def setup():
    if not PYTHON.exists():
        execute([sys.executable,'-m','venv',ROOT/'.venv'])
    execute([PYTHON,'-m','pip','install','-r','benchmark-ehr/requirements.txt'])
    execute([PYTHON,'benchmark-ehr/prepare.py','medxpertqa_salted_500_curated.pdf'])
    execute([PYTHON,'benchmark-scoring/build_key.py','medxpertqa_salted_500_curated.pdf'])
    execute(COMPOSE+['up','-d','--build','ehr-viewer'])
    print('Ready. Run python3 scripts/benchmark.py smoke; see README for the optional browser viewer.')


def selected_cases(value):
    selected = set()
    for part in value.split(','):
        if not re.fullmatch(r'\d+(?:-\d+)?', part):
            raise ValueError('Invalid case range')
        ends = [int(x) for x in part.split('-')]
        if not 1 <= ends[0] <= ends[-1] <= 500:
            raise ValueError('Case numbers must be ordered and between 1 and 500')
        selected.update(range(ends[0], ends[-1]+1))
    return sorted(selected)


def run_batches(command, forwarded, cases, output, score_every=10, key=None):
    """Score only closed batches; the inference process never reads the key."""
    failed = False
    for start in range(0, len(cases), score_every):
        batch = cases[start:start+score_every]
        logs = output/'logs'/f'batch-{start//score_every+1:04d}'
        result = execute(command+['--logs', logs, '--cases', ','.join(map(str, batch))]+forwarded, check=False)
        if not logs.exists() or not any(logs.glob('*.jsonl')):
            # Configuration errors and --help must not launch the remaining batches.
            return result.returncode or int(failed)
        failed |= result.returncode != 0
        count = len(list((output/'logs').rglob('*.jsonl')))
        print(f'\nScore checkpoint: {count}/{len(cases)} cases attempted', flush=True)
        score_command = [PYTHON, 'benchmark-scoring/score.py', '--logs', output/'logs', '--output', output/'report.json']
        if key is not None:
            score_command += ['--key', key]
        score_result = execute(score_command, check=False)
        if score_result.returncode:
            print(f'Scoring failed; saved model logs are in {output / "logs"}. '
                  'Restore the answer key and use the score command; no model rerun is needed.', file=sys.stderr)
            return score_result.returncode
        checkpoints = output/'scores'
        checkpoints.mkdir(parents=True, exist_ok=True)
        for suffix in ('.json', '.md'):
            shutil.copyfile(output/('report'+suffix), checkpoints/(f'after-{count:04d}'+suffix))
        if result.returncode < 0:
            break
    return int(failed)


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
        raise SystemExit(execute([PYTHON,'benchmark-scoring/score.py',*rest], check=False).returncode)
    options = argparse.ArgumentParser()
    options.add_argument('--output', type=Path)
    options.add_argument('--key', type=Path, default=ROOT/'evaluation-private/answer-key.json')
    options.add_argument('--cases')
    options.add_argument('--score-every', type=int, default=10, help='Save cumulative scores after this many cases (default: 10)')
    known, forwarded = options.parse_known_args(rest)
    if '--logs' in forwarded or any(x.startswith('--logs=') for x in forwarded):
        parser.error('Use --output rather than --logs with this wrapper')
    output = known.output or Path('evaluation-private/runs')/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    if not output.is_absolute():
        output = ROOT/output
    if known.score_every < 1:
        parser.error('--score-every must be positive')
    try:
        cases = selected_cases(known.cases or ('1-3' if args.command == 'smoke' else '1-500'))
    except ValueError as exc:
        parser.error(str(exc))
    if (output/'logs').exists() and any((output/'logs').iterdir()):
        parser.error('Use a fresh output directory for each evaluation')
    key_path = known.key if known.key.is_absolute() else ROOT/known.key
    try:
        key_data = json.loads(key_path.read_text())
        if not isinstance(key_data, dict) or not isinstance(key_data.get('cases'), dict):
            raise ValueError('Expected an answer key with a cases object')
        if any(f'mxq-{n:04d}' not in key_data['cases'] for n in cases):
            raise ValueError('Answer key is missing selected cases')
    except (OSError, ValueError) as exc:
        parser.error(f'Cannot load scoring key {key_path}: {exc}. Restore the original key, '
                     'supply --key PATH, or rebuild with .venv/bin/python benchmark-scoring/build_key.py PATH_TO_SOURCE_PDF. '
                     'No model calls were made.')
    command = [PYTHON,'benchmark-runner/run.py']
    if args.command == 'smoke':
        command += ['--smoke']
    code = run_batches(command, forwarded, cases, output, known.score_every, key_path)
    if code:
        raise SystemExit(code)

if __name__ == '__main__':
    main()
