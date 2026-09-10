import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'benchmark-ehr'))
sys.path.insert(0, str(ROOT/'benchmark-runner'))
import prepare
import server
import run
from isolated import IsolatedModel


class Boundaries(unittest.TestCase):
    def test_all_charts_are_patient_only_and_tasks_separate(self):
        charts = server.load_charts(ROOT/'benchmark-ehr/generated')
        self.assertEqual(len(charts), 500)
        for pid in charts:
            task = json.loads((ROOT/'benchmark-tasks'/(pid+'.json')).read_text())
            self.assertEqual(set(task), {'patient_id', 'question'})
            self.assertEqual(task['patient_id'], pid)
            self.assertNotRegex(task['question'], r'(?im)^\s*(answer:|canary:|source:|salted:)')

    def test_rejects_tampering_in_any_field(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'mxq-0001.json'
            for field in ['text', 'extension', 'answer', 'contained']:
                data = prepare.bundle({'number': 1})
                data['entry'][0]['resource'][field] = 'SECRET'
                path.write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    server.load_charts(Path(directory))
            path.unlink()
            path.symlink_to(ROOT/'benchmark-ehr/generated/mxq-0001.json')
            with self.assertRaises(ValueError):
                server.load_charts(Path(directory))

    def test_tools_reject_scope_and_url_injection_before_io(self):
        session = Mock()
        for pid in ['mxq-0002', '../../evaluation-private/key', 'http://example.com', None]:
            for name in ['read_task', 'read_ehr']:
                args = {'patient_id': pid}
                if name == 'read_ehr':
                    args['resource_type'] = 'Patient'
                self.assertIn('error', run.read_ehr(name, args, 'mxq-0001', 'http://localhost', session))
        for resource in ['../_history', 'http://example.com', 'Patient?_include=*', '_history']:
            self.assertIn('error', run.read_ehr('read_ehr', {'patient_id':'mxq-0001','resource_type':resource}, 'mxq-0001', 'http://localhost', session))
        session.get.assert_not_called()

    def test_task_retrieval_separate(self):
        result = run.read_ehr('read_task', {'patient_id':'mxq-0001'}, 'mxq-0001', '', Mock())
        self.assertIn('question_text', result)
        self.assertNotIn('fhir', result)

    def test_image_must_be_immutable(self):
        for image in ['latest', 'python:3', '--privileged', 'repo@sha256:abc']:
            with self.assertRaises(ValueError):
                IsolatedModel(image)

if __name__ == '__main__':
    unittest.main()
