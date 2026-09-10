"""Offline deterministic answer and tool-trajectory evaluation; no LLM judge."""
import argparse
import base64
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
from statistics import mean
from build_key import normalize
from rubrics import apply_rubric, VERSION


def answer_score(answer, key, convention='standalone'):
    """Accept exact option text or an explicit choice. Never mine a rationale for letters."""
    value = answer
    if isinstance(value, str):
        stripped = value.strip()
        try:
            value = json.loads(stripped) if stripped.startswith('{') else stripped
        except (ValueError, TypeError):
            value = stripped
    choice, text = None, None
    if isinstance(value, dict):
        convention = value.get('choice_set', convention)
        choice, text = value.get('choice'), value.get('answer_text')
    elif isinstance(value, str):
        match = re.fullmatch(r'(?:Answer:\s*)?\(?([A-J])\)?(?:[.)]\s*(.*))?', value, re.S)
        if match:
            choice, text = match[1], match[2] or None
        else:
            text = value
    else:
        return {'correct': False, 'answer_status': 'invalid_format'}
    if convention not in ('standalone', 'inline'):
        return {'correct': False, 'answer_status': 'invalid_choice_set'}
    options = key['options'] if convention == 'standalone' else key['inline_options']
    if choice is not None:
        if not isinstance(choice, str) or choice not in options:
            return {'correct': False, 'answer_status': 'unmapped_choice'}
        selected = options[choice]
        if text is not None and (not isinstance(text, str) or normalize(text) != normalize(selected)):
            return {'correct': False, 'answer_status': 'conflicting_choice_and_text'}
    elif isinstance(text, str) and normalize(text) in {normalize(t) for t in key['options'].values()}:
        selected = text
    else:
        return {'correct': False, 'answer_status': 'unrecognized_answer'}
    return {'correct': normalize(selected) == normalize(key['correct_text']), 'answer_status': 'scored'}


def response_failed(value):
    if not isinstance(value, dict):
        return False
    if 'fhir' in value and response_failed(value['fhir']):
        return True
    if value.get('error') or value.get('isError') is True:
        return True
    if value.get('resourceType') == 'OperationOutcome':
        return any(i.get('severity') in ('fatal', 'error') for i in value.get('issue', []))
    return False


def resources(value):
    if not isinstance(value, dict):
        return []
    if 'fhir' in value:
        return resources(value['fhir'])
    if value.get('resourceType') == 'Bundle':
        return [e['resource'] for e in value.get('entry', []) if 'resource' in e]
    return [value] if value.get('resourceType') else []


def tool_metrics(events, task_id, question_hash):
    calls = [e for e in events if e.get('type') == 'tool_call']
    known_turns = all(isinstance(e.get('turn'), int) and e['turn'] > 0 for e in calls)
    seen, failed, repeats, empty, verified_notes, unverified, cross_patient = set(), 0, 0, 0, 0, 0, 0
    latencies, first_retrieval = [], None
    scope_violations = 0
    for index, call in enumerate(calls, 1):
        signature = json.dumps([call.get('tool_name'), call.get('arguments')], sort_keys=True)
        repeats += signature in seen
        seen.add(signature)
        arguments = call.get('arguments') or {}
        if isinstance(arguments, dict):
            target = arguments.get('patient_id')
            search = arguments.get('search_parameters') or {}
            if isinstance(search, dict):
                target = target or search.get('patient') or search.get('subject')
            if isinstance(target, str) and target not in (task_id, 'Patient/'+task_id):
                scope_violations += 1
        raw = call.get('raw_response')
        if raw is None:
            unverified += 1
        failed += response_failed(raw)
        if isinstance(raw, dict) and raw.get('error_code') == 'patient_scope_violation':
            # Count a blocked request once, even if its arguments also show it.
            if not isinstance(arguments, dict) or arguments.get('patient_id') in (None, task_id):
                scope_violations += 1
        if isinstance(raw, dict) and raw.get('resourceType') == 'Bundle' and not raw.get('entry'):
            empty += 1
        latency = call.get('latency_ms')
        if isinstance(latency, (int,float)) and latency >= 0:
            latencies.append(latency)
        found_note = False
        wrong_patient = False
        for r in resources(raw):
            ref = r.get('subject', r.get('patient', {})).get('reference', '')
            if (ref.startswith('Patient/') and ref != 'Patient/'+task_id) or (r.get('resourceType') == 'Patient' and r.get('id') != task_id):
                wrong_patient = True
            if r.get('resourceType') == 'DocumentReference' and ref == 'Patient/'+task_id:
                for content in r.get('content', []):
                    try:
                        note = base64.b64decode(content.get('attachment', {}).get('data', ''), validate=True)
                        found_note |= hashlib.sha256(note).hexdigest() == question_hash
                    except (ValueError, TypeError):
                        pass
        cross_patient += wrong_patient
        if found_note and not response_failed(raw):
            verified_notes += 1
            if first_retrieval is None:
                first_retrieval = index
    count = len(calls)
    turns = len({e['turn'] for e in calls}) if known_turns else None
    model_events = [e for e in events if e.get('type') == 'model_turn']
    if model_events and all('tool_calls_requested' in e for e in model_events):
        turns = sum(e['tool_calls_requested'] > 0 for e in model_events)
    return {'tool_calls': count, 'tool_turns': turns,
            'model_turns': len(model_events) if model_events else None,
            'tool_failures': failed, 'unverifiable_calls': unverified,
            'tool_success_rate': (count-failed-unverified)/count if count else None,
            'repeated_calls': repeats, 'empty_fhir_results': empty,
            'cross_patient_response_calls': cross_patient, 'scope_violations': scope_violations,
            'question_retrieved': verified_notes > 0, 'verified_question_retrieval_calls': verified_notes,
            'calls_until_question_retrieved': first_retrieval,
            'tool_latency_total_ms': round(sum(latencies), 3) if latencies else None,
            'tool_latency_mean_ms': round(mean(latencies), 3) if latencies else None,
            'tool_latency_coverage': len(latencies)/count if count else None,
            'calls_by_tool': dict(Counter(e.get('tool_name', 'unknown') for e in calls))}


def score_run(events, key, convention):
    tasks = {e['task_id'] for e in events if 'task_id' in e}
    if len(tasks) != 1:
        raise ValueError('Each run must have exactly one task_id')
    task = tasks.pop()
    if task not in key['cases']:
        raise ValueError(f'Unknown benchmark task: {task}')
    final = [e for e in events if e.get('type') == 'final_answer']
    starts = [e for e in events if e.get('type') == 'run_start']
    ends = [e for e in events if e.get('type') == 'run_end']
    invalid_end = bool(ends and ends[-1].get('status') != 'completed')
    if len(final) != 1 or invalid_end:
        accuracy = {'correct': False, 'answer_status': 'failed_or_incomplete_run' if len(final)<2 else 'multiple_final_answers'}
    else:
        accuracy = answer_score(final[0].get('answer'), key['cases'][task], convention)
    # Ignore any calls recorded after the submitted final answer.
    before_final = events[:events.index(final[0])] if final else events
    result = {'run_id': events[0]['run_id'], 'task_id': task,
            'model': starts[0].get('model', starts[0].get('model_provider','unknown')) if starts else 'unknown',
            **accuracy, **tool_metrics(before_final, task, key['cases'][task]['question_sha256'])}
    result['task_type'] = key['cases'][task].get('task_type','unspecified')
    result['body_system'] = key['cases'][task].get('body_system','unspecified')
    result['elapsed_ms'] = ends[-1].get('elapsed_ms') if ends else None
    turns = [e for e in events if e.get('type') == 'model_turn']
    result['model_latency_total_ms'] = sum(e.get('latency_ms', 0) for e in turns) if turns else None
    result['reported_tokens'] = {name: sum(e.get('usage', {}).get(name, 0) for e in turns) for name in ('prompt_tokens','completion_tokens','total_tokens')} if any(e.get('usage') for e in turns) else None
    result['correct_with_verified_retrieval'] = result['correct'] and result['question_retrieved']
    result['rubric'] = apply_rubric(result)
    return result


def summarize(rows, total_cases):
    groups = defaultdict(list)
    for row in rows:
        groups[row['model']].append(row)
    output = {}
    for model, runs in groups.items():
        counts = Counter(r['task_id'] for r in runs)
        calls = sum(r['tool_calls'] for r in runs)
        turns = [r['tool_turns'] for r in runs if r['tool_turns'] is not None]
        successful = [r for r in runs if r['correct']]
        by_type = {}
        for kind in sorted({r['task_type'] for r in runs}):
            subset = [r for r in runs if r['task_type'] == kind]
            by_type[kind] = {'runs':len(subset), 'accuracy':mean(r['correct'] for r in subset)}
        output[model] = {'accuracy_by_source_task_type': by_type, 'rubric_score_mean': mean(r['rubric']['total'] for r in runs),
            'rubric_criteria_mean': {c:mean(r['rubric']['points'][c] for r in runs) for c in runs[0]['rubric']['points']},
            'runs': len(runs), 'unique_cases': len(counts), 'dataset_cases': total_cases,
            'coverage': len(counts)/total_cases, 'duplicate_case_runs': sum(n-1 for n in counts.values()),
            'accuracy_with_verified_retrieval': mean(r['correct_with_verified_retrieval'] for r in runs),
            'correct_runs': len(successful), 'accuracy_over_submitted_runs': len(successful)/len(runs),
            'accuracy_over_full_dataset': len(successful)/total_cases if max(counts.values()) == 1 else None,
            'answer_status_counts': dict(Counter(r['answer_status'] for r in runs)),
            'tool_calls_total': calls, 'tool_calls_mean': mean(r['tool_calls'] for r in runs),
            'tool_turns_mean': mean(turns) if turns else None,
            'runs_with_known_tool_turns': len(turns),
            'tool_turns_min': min(turns) if turns else None,
            'tool_turns_max': max(turns) if turns else None,
            'model_turns_mean': mean(r['model_turns'] for r in runs if r['model_turns'] is not None) if any(r['model_turns'] is not None for r in runs) else None,
            'elapsed_ms_mean': mean(r['elapsed_ms'] for r in runs if r['elapsed_ms'] is not None) if any(r['elapsed_ms'] is not None for r in runs) else None,
            'question_retrieval_rate': mean(r['question_retrieved'] for r in runs),
            'tool_success_rate': (calls-sum(r['tool_failures']+r['unverifiable_calls'] for r in runs))/calls if calls else None,
            'repeated_calls': sum(r['repeated_calls'] for r in runs),
            'empty_fhir_results': sum(r['empty_fhir_results'] for r in runs),
            'scope_violations': sum(r['scope_violations'] for r in runs),
            'cross_patient_response_calls': sum(r['cross_patient_response_calls'] for r in runs),
            'tool_calls_mean_on_correct_runs': mean(r['tool_calls'] for r in successful) if successful else None}
    return output


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--key', type=Path, default=Path('evaluation-private/answer-key.json'))
    p.add_argument('--logs', type=Path, required=True)
    p.add_argument('--output', type=Path, default=Path('evaluation-private/report.json'))
    p.add_argument('--choice-set', choices=['standalone','inline'], default='standalone')
    args = p.parse_args()
    key = json.loads(args.key.read_text())
    files = sorted(args.logs.glob('*.jsonl')) if args.logs.is_dir() else [args.logs]
    grouped = defaultdict(list)
    for path in files:
        for line_number, line in enumerate(path.read_text().splitlines(), 1):
            if not line.strip():
                continue
            event = json.loads(line)
            if not event.get('run_id'):
                raise ValueError(f'Missing run_id at {path}:{line_number}')
            grouped[event['run_id']].append(event)
    if not grouped:
        raise ValueError('No trajectories found; no model results to score')
    rows = [score_run(events, key, args.choice_set) for events in grouped.values()]
    report = {'schema_version': 1, 'rubric_version': VERSION, 'ground_truth': 'PDF supplied answers (not independently clinically adjudicated)',
              'source_sha256': key['source_sha256'], 'default_choice_set': args.choice_set,
              'models': summarize(rows, len(key['cases'])), 'runs': rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    markdown = ['# Benchmark evaluation', '', 'Scores measure agreement with the supplied PDF key. Tool metrics describe observed retrieval behavior.', '', '| Model | Cases | Answer accuracy | Rubric / 100 | Mean calls | Mean tool turns | Question retrieval |', '|---|---:|---:|---:|---:|---:|---:|']
    for model, summary in report['models'].items():
        turns = summary['tool_turns_mean']
        safe_model = model.replace('|', '/').replace('\n', ' ')
        markdown.append(f"| {safe_model} | {summary['unique_cases']}/{summary['dataset_cases']} | {summary['accuracy_over_submitted_runs']:.1%} | {summary['rubric_score_mean']:.2f} | {summary['tool_calls_mean']:.2f} | {f'{turns:.2f}' if turns is not None else 'unknown'} | {summary['question_retrieval_rate']:.1%} |")
    markdown.extend(['', 'Full per-task points, call failures, repetitions, patient-scope violations, tokens and latency are in the adjacent JSON report.', 'Smoke runs are pipeline checks, not model benchmark results.', ''])
    args.output.with_suffix('.md').write_text('\n'.join(markdown))
    print(json.dumps(report['models'], indent=2))
    print(f'Report: {args.output}')

if __name__ == '__main__':
    main()
