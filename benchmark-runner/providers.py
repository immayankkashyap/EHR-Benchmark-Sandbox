"""Host-side API transports; credentials never enter model messages or run logs."""
import json
import os
import math
import random
import sys
import time
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

import requests

PROVIDERS = {
    'openai': ('OPENAI_API_KEY', 'https://api.openai.com/v1'),
    'gemini': ('GEMINI_API_KEY', 'https://generativelanguage.googleapis.com/v1beta/openai'),
    'grok': ('XAI_API_KEY', 'https://api.x.ai/v1'),
    'anthropic': ('ANTHROPIC_API_KEY', 'https://api.anthropic.com/v1'),
    'deepseek': ('DEEPSEEK_API_KEY', 'https://api.deepseek.com/v1'),
    'mistral': ('MISTRAL_API_KEY', 'https://api.mistral.ai/v1'),
    'moonshot': ('MOONSHOT_API_KEY', 'https://api.moonshot.ai/v1'),
    'glm': ('GLM_API_KEY', 'https://api.z.ai/api/paas/v4'),
}
ALIASES = {'xai': 'grok', 'deepkseek': 'deepseek', 'zai': 'glm'}
KEY_ALIASES = {'gemini': 'GOOGLE_API_KEY', 'grok': 'GROK_API_KEY', 'glm': 'ZAI_API_KEY'}


class ProviderError(RuntimeError):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


class APIModel:
    def __init__(self, provider, model, timeout=120, max_tokens=4096, base_url=None,
                 requests_per_minute=0, max_retries=5, retry_base_delay=2, retry_max_delay=60):
        self.provider = ALIASES.get(provider, provider)
        if self.provider not in PROVIDERS:
            raise ValueError('Unknown API provider')
        key_name, default_url = PROVIDERS[self.provider]
        self.api_key = (os.environ.get(key_name) or os.environ.get(KEY_ALIASES.get(self.provider, '')) or '').strip()
        if not self.api_key:
            raise ValueError(f'Set {key_name} before running {self.provider}')
        if not model or not model.strip():
            raise ValueError('--model is required with --provider')
        if timeout <= 0 or max_tokens < 1:
            raise ValueError('Timeout and max tokens must be positive')
        self.base_url = (base_url or default_url).rstrip('/')
        parsed = urlsplit(self.base_url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('--base-url must be an HTTPS API base URL without credentials, query or fragment')
        if not all(math.isfinite(v) for v in (requests_per_minute, retry_base_delay, retry_max_delay)):
            raise ValueError('Rate and retry delays must be finite')
        if requests_per_minute < 0 or max_retries < 0 or int(max_retries) != max_retries:
            raise ValueError('Request rate and retry count must be nonnegative')
        if retry_base_delay <= 0 or retry_max_delay < retry_base_delay:
            raise ValueError('Retry delays must be positive and max delay must be >= base delay')
        self.requests_per_minute = requests_per_minute
        self.max_retries = max_retries
        self.retry_base_delay, self.retry_max_delay = retry_base_delay, retry_max_delay
        self._next_request_at = 0.0
        self.model, self.timeout, self.max_tokens = model, timeout, max_tokens

    def _retry_after(self, response):
        value = response.headers.get('Retry-After')
        if not isinstance(value, str):
            return 0.0
        try:
            seconds = float(value)
        except ValueError:
            try:
                seconds = parsedate_to_datetime(value).timestamp() - time.time()
            except (ValueError, TypeError, OverflowError):
                return 0.0
        return max(0.0, seconds) if math.isfinite(seconds) else 0.0

    def _request(self, endpoint, headers, payload):
        backoff = self.retry_base_delay
        for attempt in range(self.max_retries + 1):
            wait = self._next_request_at - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            # Pace every attempt, including retries and requests for later cases.
            self._next_request_at = time.monotonic() + (60 / self.requests_per_minute
                                                       if self.requests_per_minute else 0)
            retry_after = 0.0
            try:
                response = requests.post(self.base_url+endpoint, headers=headers, json=payload,
                                         timeout=self.timeout, allow_redirects=False)
            except (requests.ConnectionError, requests.Timeout):
                error = ProviderError('Provider request failed (connection or timeout)')
            except requests.RequestException:
                raise ProviderError('Provider request failed') from None
            else:
                if response.status_code not in (429, 500, 502, 503, 504):
                    return response
                error = ProviderError(f'{self.provider} API returned HTTP {response.status_code}', response.status_code)
                try:
                    retry_after = self._retry_after(response)
                finally:
                    response.close()
            delay = max(retry_after, random.uniform(backoff / 2, backoff))
            self._next_request_at = max(self._next_request_at, time.monotonic() + delay)
            if attempt == self.max_retries:
                raise error from None
            print(f'{self.provider}: {error}; retry {attempt + 1}/{self.max_retries} '
                  f'in {max(0, self._next_request_at - time.monotonic()):.1f}s', file=sys.stderr, flush=True)
            backoff = min(self.retry_max_delay, backoff * 2)

    def __call__(self, messages, turn):
        from run import TOOLS
        headers = {'Content-Type': 'application/json'}
        if self.provider == 'anthropic':
            headers.update({'x-api-key': self.api_key, 'anthropic-version': '2023-06-01'})
            payload = self._anthropic_payload(messages, TOOLS)
            endpoint = '/messages'
        else:
            headers['Authorization'] = 'Bearer '+self.api_key
            token_key = 'max_completion_tokens' if self.provider == 'openai' else 'max_tokens'
            payload = {'model': self.model, 'messages': list(messages), 'tools': TOOLS,
                       token_key: self.max_tokens}
            endpoint = '/chat/completions'
        # No redirects: never forward credentials to a redirected endpoint.
        response = self._request(endpoint, headers, payload)
        try:
            if not 200 <= response.status_code < 300:
                raise ProviderError(f'{self.provider} API returned HTTP {response.status_code}', response.status_code)
            try:
                data = response.json()
                usage = {k: v for k, v in (data.get('usage') or {}).items() if isinstance(v, (int, float))}
                finish_reason = (data.get('stop_reason') if self.provider == 'anthropic'
                                 else data['choices'][0].get('finish_reason'))
                if finish_reason in ('length', 'max_tokens'):
                    # Never execute truncated tool arguments or score partial output.
                    return {'role': 'assistant', 'content': None,
                            '_output_token_limit': self.max_tokens,
                            '_finish_reason': finish_reason}, usage
                if self.provider == 'anthropic':
                    blocks = data['content']
                    message = {'role': 'assistant', 'content': ''.join(b['text'] for b in blocks if b['type'] == 'text'),
                               '_anthropic_content': blocks}
                    message['tool_calls'] = [{'id': b['id'], 'type': 'function', 'function': {
                        'name': b['name'], 'arguments': json.dumps(b['input'])}}
                        for b in blocks if b['type'] == 'tool_use']
                else:
                    raw = data['choices'][0]['message']
                    # Preserve reasoning and tool signature fields needed on subsequent turns.
                    message = {k: v for k, v in raw.items() if k in {'role', 'content', 'tool_calls', 'reasoning_content'}}
                if message.get('role') != 'assistant':
                    raise ValueError('Expected assistant role')
                return message, usage
            except (AttributeError, KeyError, IndexError, TypeError, ValueError):
                raise ProviderError('Invalid provider response') from None
        finally:
            response.close()

    def _anthropic_payload(self, messages, tools):
        converted = []
        for message in messages:
            role = message['role']
            if role == 'system':
                continue
            if role == 'tool':
                block = {'type': 'tool_result', 'tool_use_id': message['tool_call_id'], 'content': message['content']}
                if converted and converted[-1]['role'] == 'user':
                    converted[-1]['content'].append(block)
                else:
                    converted.append({'role': 'user', 'content': [block]})
            else:
                blocks = message.get('_anthropic_content')
                if blocks is None:
                    blocks = [{'type': 'text', 'text': message['content']}] if message.get('content') else []
                    for call in message.get('tool_calls') or []:
                        blocks.append({'type': 'tool_use', 'id': call['id'], 'name': call['function']['name'],
                                       'input': json.loads(call['function']['arguments'])})
                converted.append({'role': role, 'content': blocks})
        return {'model': self.model, 'max_tokens': self.max_tokens,
                'system': '\n\n'.join(m['content'] for m in messages if m['role'] == 'system'),
                'messages': converted, 'tools': [{'name': t['function']['name'],
                    'description': t['function']['description'], 'input_schema': t['function']['parameters']} for t in tools]}
