import json
import io
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
        return Mock(status_code=status, headers={}, json=Mock(return_value=data))

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

    def test_output_limit_is_visible_and_never_runs_partial_tools(self):
        for provider, (key, _) in PROVIDERS.items():
            for content in (None, '<thought>still reasoning', '{"choice":"A"}'):
                with self.subTest(provider=provider, content=content), patch.dict(os.environ, {key: 'secret-test'}, clear=True), patch('providers.requests.post') as post:
                    partial = {'role': 'assistant', 'content': content, 'tool_calls': [
                        {'id': 'truncated', 'type': 'function', 'function': {'name': 'read_task', 'arguments': '{'}}]}
                    data = ({'stop_reason': 'max_tokens', 'content': [], 'usage': {'output_tokens': 16}}
                            if provider == 'anthropic' else
                            {'choices': [{'finish_reason': 'length', 'message': partial}], 'usage': {'completion_tokens': 16}})
                    post.return_value = self.response(data)
                    with tempfile.TemporaryDirectory() as directory, patch('sys.stderr', new_callable=io.StringIO) as stderr, patch.object(run, 'read_ehr') as read:
                        result = run.run_case('mxq-0001', APIModel(provider, 'test', max_tokens=16), '', Path(directory), 'test')
                        self.assertEqual(result['status'], 'output_token_limit')
                        self.assertIn('ERROR output_token_limit', stderr.getvalue())
                        self.assertIn('Increase --max-tokens', stderr.getvalue())
                        self.assertIn('--timeout', stderr.getvalue())
                        events = [json.loads(line) for line in Path(result['log']).read_text().splitlines()]
                        self.assertFalse(any(e['type'] == 'final_answer' for e in events))
                        self.assertEqual(next(e for e in events if e['type'] == 'run_error')['max_tokens'], 16)
                        self.assertTrue(next(e for e in events if e['type'] == 'model_turn')['usage'])
                        self.assertNotIn('secret-test', Path(result['log']).read_text()+stderr.getvalue())
                        read.assert_not_called()
                    post.return_value.close.assert_called_once()

    def test_token_limit_returns_nonzero_cli_exit(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'GEMINI_API_KEY': 'test'}), patch('providers.requests.post') as post:
            post.return_value = self.response({'choices': [{'finish_reason': 'length'}]})
            argv = ['run.py', '--provider', 'gemini', '--model', 'test', '--cases', '1', '--logs', directory]
            with patch.object(sys, 'argv', argv), patch('sys.stderr', new_callable=io.StringIO), patch('sys.stdout', new_callable=io.StringIO):
                with self.assertRaises(SystemExit) as caught:
                    run.main()
            self.assertEqual(caught.exception.code, 1)

    def test_normal_stop_at_budget_is_not_inferred_as_truncation(self):
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'test'}), patch('providers.requests.post') as post:
            post.return_value = self.response({'choices': [{'finish_reason': 'stop', 'message': {
                'role': 'assistant', 'content': '{"choice":"A"}'}}], 'usage': {'completion_tokens': 16}})
            message, usage = APIModel('gemini', 'test', max_tokens=16)([], 1)
            self.assertNotIn('_output_token_limit', message)
            self.assertEqual(usage['completion_tokens'], 16)

    def test_errors_do_not_expose_provider_body(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'secret-test'}), patch('providers.requests.post') as post:
            post.return_value = self.response({'error': 'secret-test'}, 401)
            with self.assertRaises(ProviderError) as caught:
                APIModel('openai', 'test')([], 1)
            self.assertEqual(caught.exception.status_code, 401)
            self.assertNotIn('secret-test', str(caught.exception))
            post.return_value.json.assert_not_called()

    def test_retry_backoff_and_exhaustion(self):
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'secret-test'}), patch('providers.requests.post') as post, patch('providers.time.monotonic', return_value=0), patch('providers.time.sleep') as sleep, patch('providers.random.uniform', side_effect=lambda low, high: high), patch('sys.stderr', new_callable=io.StringIO) as stderr:
            responses = [self.response({}, status) for status in (429, 503, 500, 429)]
            post.side_effect = responses
            with self.assertRaises(ProviderError) as caught:
                APIModel('gemini', 'test', max_retries=3, retry_max_delay=4)([], 1)
            self.assertEqual(caught.exception.status_code, 429)
            self.assertEqual([c.args[0] for c in sleep.call_args_list], [2, 4, 4])
            self.assertEqual(post.call_count, 4)
            for response in responses:
                response.close.assert_called_once()
                response.json.assert_not_called()
            self.assertNotIn('secret-test', stderr.getvalue())

    def test_retry_after_and_pacing_across_calls(self):
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'test'}), patch('providers.requests.post') as post, patch('providers.time.monotonic', return_value=0), patch('providers.time.sleep') as sleep, patch('sys.stderr', new_callable=io.StringIO):
            limited = self.response({}, 429)
            limited.headers = {'Retry-After': '90'}
            success = {'choices': [{'message': {'role': 'assistant', 'content': 'ok'}}]}
            post.side_effect = [limited, self.response(success), self.response(success)]
            model = APIModel('gemini', 'test', requests_per_minute=10)
            self.assertEqual(model([], 1)[0]['content'], 'ok')
            model([], 1)
            self.assertEqual([c.args[0] for c in sleep.call_args_list], [90, 6])
            limited.close.assert_called_once()

    def test_retry_after_dates_and_invalid_values(self):
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'test'}), patch('providers.time.time', return_value=0):
            model = APIModel('gemini', 'test')
            for value, expected in [('Thu, 01 Jan 1970 00:02:00 GMT', 120), ('bad', 0), ('NaN', 0), ('inf', 0), ('-5', 0)]:
                self.assertEqual(model._retry_after(Mock(headers={'Retry-After': value})), expected)

    def test_connection_retry_and_disabled_retries(self):
        import requests
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'test'}), patch('providers.requests.post') as post, patch('providers.time.sleep'), patch('sys.stderr', new_callable=io.StringIO):
            post.side_effect = [requests.Timeout('secret-test'), self.response({'choices': [{'message': {'role': 'assistant', 'content': 'ok'}}]})]
            self.assertEqual(APIModel('gemini', 'test')([], 1)[0]['content'], 'ok')
            post.reset_mock()
            post.side_effect = None
            post.return_value = self.response({}, 429)
            with self.assertRaises(ProviderError):
                APIModel('gemini', 'test', max_retries=0)([], 1)
            self.assertEqual(post.call_count, 1)

    def test_invalid_rate_retry_settings(self):
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'test'}):
            for settings in [{'requests_per_minute': -1}, {'requests_per_minute': float('nan')}, {'max_retries': -1}, {'retry_base_delay': 0}, {'retry_max_delay': 1}, {'retry_max_delay': float('inf')}]:
                with self.subTest(settings=settings), self.assertRaises(ValueError):
                    APIModel('gemini', 'test', **settings)

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
