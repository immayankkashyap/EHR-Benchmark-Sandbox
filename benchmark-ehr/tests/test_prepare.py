import base64
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('prepare', ROOT/'prepare.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class ExtractionTests(unittest.TestCase):
    def fixture(self):
        return 'Question 1 (Source: Text-1 / v1)\nCanary: secret\nSalted: age 20->21\nA 21-year-old has a known diagnosis.\nAnswer Choices: (A) First (J) Last\n A. First\nJ. Last\nAnswer: A. SECRET_KEY\nwrapped SECRET_EXPLANATION\n'

    def test_removes_entire_wrapped_answer_and_metadata(self):
        q = m.extract(self.fixture(), 1)[0]
        expected = self.fixture().split('Salted: age 20->21\n')[1].split('Answer: A.')[0]
        self.assertEqual(q['question'], expected)
        b = m.bundle(q)
        note = b['entry'][-1]['resource']
        self.assertEqual(base64.b64decode(note['content'][0]['attachment']['data']).decode(), expected)
        self.assertNotIn('SECRET', str(b))
        self.assertNotIn('secret', str(b))
        self.assertEqual({e['resource']['resourceType'] for e in b['entry']}, {'Patient','Practitioner','Organization','Encounter','DocumentReference'})
        self.assertNotIn('diagnosis', b['entry'][3]['resource'])
        self.assertEqual(m.bundle(q), b)

    def test_fail_closed(self):
        for text in [self.fixture().replace('Answer: A.', 'Key: A.'), self.fixture()+self.fixture(), self.fixture().replace('J. Last', 'K. Last')]:
            with self.assertRaises(ValueError): m.extract(text, 1)

    def test_full_pdf(self):
        from pypdf import PdfReader
        text = '\n'.join(p.extract_text() for p in PdfReader(ROOT.parent/'medxpertqa_salted_500_curated.pdf').pages)
        qs=m.extract(text)
        self.assertEqual(len(qs),500)
        for q in qs:
            self.assertNotRegex(q['question'], r'(?m)^Answer:')
            self.assertNotIn('CANARY-', q['question'])
            note=m.bundle(q)['entry'][-1]['resource']
            self.assertEqual(base64.b64decode(note['content'][0]['attachment']['data']).decode(), q['question'])

if __name__ == '__main__': unittest.main()
