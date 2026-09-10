import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'benchmark-runner'))
import run
from providers import APIModel, PROVIDERS, ProviderError


class Providers(unittest.TestCase):
    def response(self, data, status=200):
        return Mock(status_code=status, json=Mock(return_value=data))

    def test_all_providers_tool_roundtrip(self):
        for provider, (key, base) in PROVIDERS.items():
            with self.subTest(provider=provider), patch.dict(os.environ, {key: 'secret-test'}, clear=True), patch('providers.requests.post') as post:
                call = {'id': 'call-1', 'type': 'function', 'function': {
                    'name': 'read_task', 'arguments': '{"patient_id":"mxq-0001"}'},
                    'extra_content': {'google': {'thought_signature': 'signature'}}}
                first = {'role': 'assistant', 'content': None, 'tool_calls': [call], 'reasoning_content': 'reasoning'}
                final = '{"choice":"A","choice_set":"standalone"}'
                if provider == 'anthropic':
                    first_data = {'content': [{'type': 'tool_use', 'id': 'call-1', 'name': 'read_task', 'input': {'patient_id': 'mxq-0001'}}]}
                    last_data = {'content': [{'type': 'text', 'text': final}]}
                else:
                    first_data = {'choices': [{'message': first}]}
                    last_data = {'choices': [{'message': {'role': 'assistant', 'content': final}}]}
                post.side_effect = [self.response(first_data), self.response(last_data)]
                model = APIModel(provider, 'test-model')
                with tempfile.TemporaryDirectory() as directory:
                    result = run.run_case('mxq-0001', model, '', Path(directory), 'test-model')
                    self.assertEqual(result['status'], 'completed')
                    logs = Path(result['log']).read_text()
                    self.assertNotIn('secret-test', logs)
                    self.assertIn('question_text', logs)
                first_request, second_request = post.call_args_list
                self.assertEqual(first_request.args[0], base+('/messages' if provider == 'anthropic' else '/chat/completions'))
                self.assertFalse(first_request.kwargs['allow_redirects'])
                payload = second_request.kwargs['json']
                if provider == 'anthropic':
                    self.assertEqual(payload['messages'][-1]['content'][0]['tool_use_id'], 'call-1')
                    self.assertIn('input_schema', payload['tools'][0])
                    self.assertEqual(first_request.kwargs['headers']['x-api-key'], 'secret-test')
                else:
                    self.assertEqual(payload['messages'][-2]['tool_calls'][0]['extra_content']['google']['thought_signature'], 'signature')
                    self.assertEqual(payload['messages'][-2]['reasoning_content'], 'reasoning')
                    self.assertEqual(first_request.kwargs['headers']['Authorization'], 'Bearer secret-test')
                    self.assertIn('max_completion_tokens' if provider == 'openai' else 'max_tokens', payload)

    def test_errors_do_not_expose_provider_body(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'secret-test'}), patch('providers.requests.post') as post:
            post.return_value = self.response({'error': 'secret-test'}, 401)
            with self.assertRaises(ProviderError) as caught:
                APIModel('openai', 'test')([], 1)
            self.assertEqual(caught.exception.status_code, 401)
            self.assertNotIn('secret-test', str(caught.exception))
            post.return_value.json.assert_not_called()

    def test_missing_key_and_aliases(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, 'OPENAI_API_KEY'):
                APIModel('openai', 'test')
        with patch.dict(os.environ, {'ZAI_API_KEY': 'test'}, clear=True):
            self.assertEqual(APIModel('zai', 'test').provider, 'glm')

    def test_anthropic_parallel_tool_results_grouped(self):
        with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'test'}):
            model = APIModel('anthropic', 'test')
        messages = [{'role': 'assistant', '_anthropic_content': [{'type': 'thinking', 'thinking': 'x', 'signature': 's'}]},
                    {'role': 'tool', 'tool_call_id': 'a', 'content': '{}'},
                    {'role': 'tool', 'tool_call_id': 'b', 'content': '{}'}]
        payload = model._anthropic_payload(messages, run.TOOLS)
        self.assertEqual(len(payload['messages']), 2)
        self.assertEqual(len(payload['messages'][1]['content']), 2)
        self.assertEqual(payload['messages'][0]['content'][0]['signature'], 's')

    def test_cli_rejects_conflicting_or_incomplete_transports(self):
        for args in [[], ['--provider', 'openai'], ['--provider', 'openai', '--model', 'test', '--smoke'], ['--smoke', '--model', 'test']]:
            result = subprocess.run([sys.executable, str(ROOT/'benchmark-runner/run.py'), '--logs', '/tmp/unused-provider-test', *args], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2, result.stderr)

    def test_rejects_insecure_base_url(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test'}):
            for url in ['http://example.com', 'https://user:pass@example.com', 'https://example.com?key=secret']:
                with self.assertRaises(ValueError):
                    APIModel('openai', 'test', base_url=url)

if __name__ == '__main__':
    unittest.main()
