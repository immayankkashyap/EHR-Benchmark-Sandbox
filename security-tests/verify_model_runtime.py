"""Run the answer-free hostile fixture through the production model transport."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'benchmark-runner'))
from isolated import IsolatedModel

image = subprocess.check_output(['docker','image','inspect','ehr-isolation-probe','--format','{{.Id}}'],text=True).strip()
model = IsolatedModel(image, timeout=15)
messages = [{'role':'user','content':'Evaluate patient mxq-0001'}]
first, _ = model(messages, 1)
assert first['tool_calls'][0]['function']['name'] == 'read_task'
messages += [first, {'role':'tool','tool_call_id':'probe','content':'Unmarked test question'}]
second, _ = model(messages, 2)
assert json.loads(second['content']) == {'choice':'A','choice_set':'standalone'}
print('PASS: production model transport; fresh offline non-root containers; no host files, EHR connection or writable root')
