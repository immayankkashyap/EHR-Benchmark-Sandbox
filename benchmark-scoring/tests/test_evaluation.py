import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'benchmark-scoring'))
from build_key import extract_key
from score import answer_score, score_run, summarize, tool_metrics
from rubrics import task_rubric
spec = importlib.util.spec_from_file_location('runner', ROOT/'benchmark-runner/run.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

QUESTION = 'An unchanged question with option text.\n'
HASH = hashlib.sha256(QUESTION.encode()).hexdigest()
KEY = {'correct_choice':'B', 'correct_text':'Second option',
       'options':{'A':'First option','B':'Second option'},
       'inline_options':{'A':'Second option','B':'First option'}, 'question_sha256':HASH}
NOTE = {'resourceType':'DocumentReference','subject':{'reference':'Patient/mxq-0001'},
        'content':[{'attachment':{'data':base64.b64encode(QUESTION.encode()).decode()}}]}


def event(kind, **values):
    return {'type':kind,'run_id':'test','task_id':'mxq-0001',**values}


def call(turn=1, raw=None):
    return event('tool_call',turn=turn,tool_name='read_ehr',arguments={'patient_id':'mxq-0001','resource_type':'DocumentReference'}, raw_response={'fhir':NOTE} if raw is None else raw,latency_ms=5)

class ScoringTests(unittest.TestCase):
    def test_choices_use_explicit_list(self):
        self.assertFalse(answer_score('A',KEY)['correct'])
        self.assertTrue(answer_score({'choice':'A','choice_set':'inline'},KEY)['correct'])
        self.assertTrue(answer_score('B. Second option',KEY)['correct'])
        self.assertTrue(answer_score(' second\noption ',KEY)['correct'])
        self.assertEqual(answer_score({'choice':'A','answer_text':'Second option'},KEY)['answer_status'],'conflicting_choice_and_text')
        self.assertFalse(answer_score('Maybe A or B. Second option',KEY)['correct'])
        self.assertFalse(answer_score({'choice':'Z'},KEY)['correct'])
        self.assertFalse(answer_score({'choice':'B','choice_set':'unknown'},KEY)['correct'])

    def test_multiple_calls_in_one_turn_and_retrieval(self):
        events=[call(),call(),call(2,{'error':'failed'})]
        m=tool_metrics(events,'mxq-0001',HASH)
        self.assertEqual(m['tool_calls'],3)
        self.assertEqual(m['tool_turns'],2)
        self.assertEqual(m['tool_failures'],1)
        self.assertEqual(m['repeated_calls'],2)
        self.assertTrue(m['question_retrieved'])
        self.assertAlmostEqual(m['tool_success_rate'],2/3)
        del events[0]['turn']
        self.assertIsNone(tool_metrics(events,'mxq-0001',HASH)['tool_turns'])

    def test_hash_scope_empty_and_outcome(self):
        events=[call(raw={'resourceType':'Bundle','entry':[]}),call(raw={'resourceType':'OperationOutcome','issue':[{'severity':'error'}]}),call(raw={'error':'blocked','error_code':'patient_scope_violation'})]
        events[-1]['arguments']['patient_id']='mxq-0002'
        m=tool_metrics(events,'mxq-0001','bad-hash')
        self.assertFalse(m['question_retrieved'])
        self.assertEqual(m['scope_violations'],1)
        self.assertEqual(m['empty_fhir_results'],1)
        self.assertEqual(m['tool_failures'],2)
        note=json.loads(json.dumps(NOTE));note['subject']['reference']='Patient/mxq-0002'
        m=tool_metrics([call(raw={'fhir':note})],'mxq-0001',HASH)
        self.assertFalse(m['question_retrieved'])
        self.assertEqual(m['cross_patient_response_calls'],1)

    def test_rubric_and_incomplete_runs(self):
        events=[event('run_start',model='test-model'),event('model_turn',turn=1),call(),event('model_turn',turn=2),event('final_answer',answer='B'),event('run_end',status='completed')]
        row=score_run(events,{'cases':{'mxq-0001':KEY}},'standalone')
        self.assertEqual(row['rubric']['total'],100)
        self.assertEqual(row['model_turns'],2)
        self.assertEqual(summarize([row],500)['test-model']['accuracy_over_full_dataset'],1/500)
        self.assertIsNone(summarize([row,row],500)['test-model']['accuracy_over_full_dataset'])
        events.append(event('final_answer',answer='A'))
        self.assertEqual(score_run(events,{'cases':{'mxq-0001':KEY}},'standalone')['answer_status'],'multiple_final_answers')
        self.assertFalse(score_run([call()],{'cases':{'mxq-0001':KEY}},'standalone')['correct'])

    def test_no_retrieval_after_final_credit(self):
        row=score_run([event('final_answer',answer='B'),call()],{'cases':{'mxq-0001':KEY}},'standalone')
        self.assertEqual(row['rubric']['total'],60)
        self.assertFalse(row['question_retrieved'])

    def test_full_pdf_key_and_rubrics(self):
        from pypdf import PdfReader
        text='\n'.join(p.extract_text() for p in PdfReader(ROOT/'medxpertqa_salted_500_curated.pdf').pages)
        cases=extract_key(text)
        self.assertEqual(len(cases),500)
        manifest=json.loads((ROOT/'benchmark-ehr/generated/manifest.json').read_text())
        for entry in manifest['cases']:
            self.assertEqual(cases[entry['id']]['question_sha256'],entry['question_sha256'])
        for pid,key in cases.items():
            self.assertTrue(answer_score(key['correct_text'],key)['correct'])
            self.assertEqual(sum(c['max_points'] for c in task_rubric(pid,key)['criteria']),100)
        with self.assertRaises(ValueError): extract_key(text,499)
        with self.assertRaises(ValueError): extract_key(text.replace('Answer:','Missing:',1))

class RunnerTests(unittest.TestCase):
    def test_model_adapter_tool_protocol_and_credentials(self):
        model=runner.ChatModel('http://model.test/v1','test-model','test-secret',12,{'max_completion_tokens':100})
        message={'role':'assistant','content':'{"choice":"B"}'}
        response=Mock(ok=True)
        response.json.return_value={'choices':[{'message':message,'finish_reason':'stop'}],'usage':{'total_tokens':4}}
        model.session.post=Mock(return_value=response)
        result,usage=model([{'role':'user','content':'Evaluate patient mxq-0001'}],1)
        self.assertEqual(result,message)
        self.assertEqual(usage['total_tokens'],4)
        sent=model.session.post.call_args.kwargs['json']
        self.assertEqual(sent['tools'],runner.TOOLS)
        self.assertEqual(sent['model'],'test-model')
        self.assertNotIn('test-secret',json.dumps(sent))
        self.assertNotIn('correct_choice',json.dumps(sent))
        response.json.return_value['choices'][0]['finish_reason']='length'
        with self.assertRaises(RuntimeError):model([],2)
        response.ok=False;response.status_code=401
        with self.assertRaises(runner.ModelAPIError) as error:model([],3)
        self.assertEqual(error.exception.status_code,401)
        model.session.close()

    def test_scope_is_blocked_before_network(self):
        class NoNetwork:
            def get(self,*args,**kwargs):raise AssertionError('Network must not be used')
        r=runner.read_ehr('read_ehr',{'patient_id':'mxq-0002','resource_type':'DocumentReference'},'mxq-0001','http://test',NoNetwork())
        self.assertEqual(r['error_code'],'patient_scope_violation')

    def test_complete_last_turn_and_log_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(runner,'read_ehr',return_value={'fhir':NOTE}):
                result=runner.run_case('mxq-0001',runner.smoke_model,'http://test',Path(tmp),'smoke',max_turns=2)
            events=[json.loads(s) for s in Path(result['log']).read_text().splitlines()]
        self.assertEqual(result['status'],'completed')
        self.assertEqual(len([e for e in events if e['type']=='final_answer']),1)
        row=score_run(events,{'cases':{'mxq-0001':KEY}},'standalone')
        self.assertEqual(row['tool_turns'],1)
        self.assertEqual(row['model_turns'],2)
        self.assertFalse(row['correct'])

    def test_budget_and_model_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(runner,'read_ehr',return_value={'fhir':NOTE}):
                r=runner.run_case('mxq-0001',runner.smoke_model,'http://test',Path(tmp),'smoke',max_turns=1)
            self.assertEqual(r['status'],'max_turns')
            def broken(*args): raise RuntimeError('secret-do-not-log')
            r=runner.run_case('mxq-0001',broken,'http://test',Path(tmp),'broken')
            self.assertEqual(r['status'],'model_error')
            self.assertNotIn('secret-do-not-log',Path(r['log']).read_text())

if __name__=='__main__':unittest.main()
