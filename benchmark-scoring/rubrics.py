"""Versioned, deterministic rubric shared by generation and scoring."""
VERSION = 'ehr-offline-v2'
CRITERIA = [
    {'id': 'answer_agreement', 'max_points': 60, 'rule': '60 for an unambiguous final selection matching the PDF key by option text; otherwise 0. No partial credit or semantic LLM judging.'},
    {'id': 'question_retrieval', 'max_points': 20, 'rule': '20 only if a successful tool response before the final answer contains the assigned read_task prompt with the exact question SHA-256 (legacy DocumentReference traces remain readable); otherwise 0.'},
    {'id': 'tool_execution', 'max_points': 10, 'rule': '10 times successful calls / all calls. A reported error, missing response or FHIR fatal/error OperationOutcome is unsuccessful. No calls gives 0.'},
    {'id': 'patient_scope', 'max_points': 5, 'rule': '5 if at least one call occurred, all call responses are present, and no blocked cross-patient request or other-patient response occurred; otherwise 0. Measures observed trace scope, not a security certification.'},
    {'id': 'retrieval_efficiency', 'max_points': 5, 'rule': '5 / total tool calls if the exact question was retrieved; otherwise 0. The one-call baseline applies only to this separate question retrieval task. Extra calls remain visible and are not presumed clinically harmful.'},
]


def task_rubric(task_id, key):
    return {'rubric_version': VERSION, 'task_id': task_id, 'max_points': 100,
            'source_task_type': key.get('task_type','unspecified'),
            'source_body_system': key.get('body_system','unspecified'),
            'task': 'Read the assigned benchmark task and select the PDF-keyed option.',
            'required_patient': 'Patient/'+task_id,
            'required_tool': 'read_task',
            'question_sha256': key['question_sha256'],
            'expected_choice_set': 'standalone', 'expected_choice': key['correct_choice'],
            'expected_answer_text': key['correct_text'],
            'minimum_sufficient_tool_calls': 1, 'criteria': CRITERIA,
            'not_assessed': ['clinical rationale quality', 'real-world clinical safety', 'full hospital workflow competence'],
            'ground_truth_policy': 'Use the PDF answer as supplied, without clinical correction.'}


def apply_rubric(row):
    calls = row['tool_calls']
    retrieved = row['question_retrieved']
    earned = {
        'answer_agreement': 60 if row['correct'] else 0,
        'question_retrieval': 20 if retrieved else 0,
        'tool_execution': 10 * (row['tool_success_rate'] or 0),
        'patient_scope': 5 if calls and not row['cross_patient_response_calls'] and not row['scope_violations'] and not row['unverifiable_calls'] else 0,
        'retrieval_efficiency': 5/calls if calls and retrieved else 0,
    }
    return {'version': VERSION, 'points': {k: round(v, 4) for k,v in earned.items()},
            'total': round(sum(earned.values()), 4), 'maximum': 100}
