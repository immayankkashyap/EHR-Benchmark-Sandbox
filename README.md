# Restricted EHR benchmark

Models can run offline in disposable containers or through provider APIs. EHR records contain only synthetic
patient administrative data; question prompts and unmarked choices are separate,
and answer keys and scores stay in the trusted host evaluator.

Read [SECURITY.md](SECURITY.md) for the enforced boundaries, image protocol,
resource limits and dataset limitations. This is currently a question-answering
benchmark: reviewed clinical chart narratives have not been supplied.

## Start the EHR

```sh
docker compose -f docker-compose.yml up -d --build ehr-viewer
```

For browser access, run the trusted host viewer separately:

```sh
.venv/bin/python benchmark-ehr/server.py --data benchmark-ehr/generated --host 127.0.0.1 --port 8090
```

Then open http://localhost:8090. Evaluations do not require this browser process. The checked-in 500 patient snapshots and separate
task prompts are ready to use. The EHR no longer reads the legacy FHIR database.
Old services should be stopped before evaluation.

## Evaluate

Use a model image built in a separate clean directory with the stdin/stdout
protocol in SECURITY.md. Supply its immutable local image ID:

```sh
python3 scripts/benchmark.py run --model-image sha256:YOUR_LOCAL_IMAGE_ID --cases 1-10
```

In offline mode, no host files, model credentials, evaluator keys or
network interfaces are passed to model containers. Each turn starts a fresh
container and receives the conversation so far.

For a plumbing check that retrieves the task and always answers A:

```sh
python3 scripts/benchmark.py smoke
```

The wrapper writes logs and offline scores under `evaluation-private/runs/`.
It requires `.venv` with `benchmark-ehr/requirements.txt` installed and a private
answer key prepared by the evaluator. To regenerate inputs from the original
PDF (not included in this checkout), use `python3 scripts/benchmark.py setup`.
Never put source PDFs or answer keys in model images or EHR mounts.

## Test models with API keys

Install the host runner dependencies (no provider SDKs or Docker needed for API runs):

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r benchmark-ehr/requirements.txt
```

Create an API key with the provider you want to test and export its variable in
the same terminal. Only that provider's key is required. Replace `YOUR_API_KEY`
and `MODEL_ID` below with your key and an exact model ID available to your account.
Choose a text model that supports function/tool calling.

| Provider / official API docs | `--provider` | Key variable |
| --- | --- | --- |
| [OpenAI](https://platform.openai.com/docs/api-reference/chat/create) | `openai` | `OPENAI_API_KEY` |
| [Google Gemini](https://ai.google.dev/gemini-api/docs/openai) | `gemini` | `GEMINI_API_KEY` |
| [xAI Grok](https://docs.x.ai/developers/rest-api-reference/inference/chat) | `grok` | `XAI_API_KEY` |
| [Anthropic Claude](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview) | `anthropic` | `ANTHROPIC_API_KEY` |
| [DeepSeek](https://api-docs.deepseek.com/guides/tool_calls/) | `deepseek` | `DEEPSEEK_API_KEY` |
| [Mistral](https://docs.mistral.ai/api) | `mistral` | `MISTRAL_API_KEY` |
| [Moonshot / Kimi](https://platform.moonshot.ai/docs/guide/start-using-kimi-api) | `moonshot` | `MOONSHOT_API_KEY` |
| [GLM / Z.AI](https://docs.z.ai/api-reference/llm/chat-completion) | `glm` | `GLM_API_KEY` |

Run whichever example matches your provider:

```sh
export OPENAI_API_KEY='YOUR_API_KEY'
python3 scripts/benchmark.py run --provider openai --model MODEL_ID --cases 1

export GEMINI_API_KEY='YOUR_API_KEY'
python3 scripts/benchmark.py run --provider gemini --model MODEL_ID --cases 1

export XAI_API_KEY='YOUR_API_KEY'
python3 scripts/benchmark.py run --provider grok --model MODEL_ID --cases 1

export ANTHROPIC_API_KEY='YOUR_API_KEY'
python3 scripts/benchmark.py run --provider anthropic --model MODEL_ID --cases 1

export DEEPSEEK_API_KEY='YOUR_API_KEY'
python3 scripts/benchmark.py run --provider deepseek --model MODEL_ID --cases 1

export MISTRAL_API_KEY='YOUR_API_KEY'
python3 scripts/benchmark.py run --provider mistral --model MODEL_ID --cases 1

export MOONSHOT_API_KEY='YOUR_API_KEY'
python3 scripts/benchmark.py run --provider moonshot --model MODEL_ID --cases 1

export GLM_API_KEY='YOUR_API_KEY'
python3 scripts/benchmark.py run --provider glm --model MODEL_ID --cases 1
```

`GOOGLE_API_KEY`, `GROK_API_KEY`, and `ZAI_API_KEY` are also accepted as fallbacks
for Gemini, Grok, and GLM. Provider aliases `xai`, `zai`, and `deepkseek` are accepted.
The runner reads exported environment variables; it does **not** automatically
load `.env`. The root `.env.example` also includes legacy proxy settings, which
are not needed for API evaluation.

Start with one case, then use `--cases 1-10,25` or `--cases 1-500`. Each run writes
logs and `report.json` under a new `evaluation-private/runs/` directory. Use
`--output evaluation-private/runs/my-test` to choose a fresh output directory.
Scoring requires the evaluator's private answer key, as for offline runs.

The wrapper prints and saves **cumulative scores every 10 attempted cases**,
including failed cases, and after the final partial batch. `report.json` and
`report.md` always contain the latest checkpoint. Historical checkpoints are saved
as `scores/after-0010.json`, `scores/after-0020.json`, etc., with matching Markdown
files. Change the interval with `--score-every N`. Logs are stored under
`logs/batch-0001/`, `logs/batch-0002/`, etc.; the scorer reads them recursively.
Previously saved checkpoints remain available if a later batch is interrupted.
The host scores between batches; scores and answer keys are never sent to models.

Final answers should be bare JSON, such as `{"choice":"B","choice_set":"standalone"}`.
The scorer also accepts a single final Markdown JSON code block, optionally preceded
by reasoning. It does not infer choices from reasoning text or accept multiple code
blocks, trailing prose, or conflicting choice/text fields. Existing logs can be
rescored without making model API calls:

```sh
python3 scripts/benchmark.py score --logs evaluation-private/runs/RUN_ID/logs --output evaluation-private/runs/RUN_ID/report-rescored.json
```

This behavior applies to `scripts/benchmark.py run` and `smoke`; the lower-level
`benchmark-runner/run.py` only produces logs.

### Gemma 4 26B with default reasoning

The Gemini API model ID is `gemma-4-26b-a4b-it`. Google's live model metadata
reported `outputTokenLimit: 32768` and `inputTokenLimit: 262144` on September 10,
2026. The commands below use the maximum **32,768 output tokens** and leave the
provider's reasoning setting at its default. The input limit is separate and
should not be used as the output budget.

```sh
export GEMINI_API_KEY='YOUR_API_KEY'

# Test one case.
python3 scripts/benchmark.py run --provider gemini --model gemma-4-26b-a4b-it \
  --cases 1 --max-tokens 32768 --timeout 1200

# Run the remaining cases, saving cumulative scores every 10 cases.
python3 scripts/benchmark.py run --provider gemini --model gemma-4-26b-a4b-it \
  --cases 2-500 --max-tokens 32768 --timeout 1200 --score-every 10

# Or run all 500 cases in one evaluation.
python3 scripts/benchmark.py run --provider gemini --model gemma-4-26b-a4b-it \
  --cases 1-500 --max-tokens 32768 --timeout 1200 --score-every 10
```

In the September 10, 2026 case-1 test, task retrieval succeeded, but default
reasoning produced repeated thought text without a valid final answer at the
earlier 16,384-token budget. The scorer recorded `unrecognized_answer`; the test took about 5.8 minutes.
Increasing the budget does not guarantee that a model will return a valid answer.

### Output-token limit errors and suggested fix

When a provider reports that generation reached its output-token limit, the
benchmark immediately prints an error instead of silently accepting empty,
reasoning-only, or truncated output. For example:

```text
mxq-0001: ERROR output_token_limit: Provider stopped at the output-token limit (--max-tokens 16384). No final answer was accepted. Increase --max-tokens within the model limit and increase --timeout if needed, then retry this case. Repeated reasoning may still exhaust a larger budget; reasoning settings are unchanged.
```

The case is recorded as `output_token_limit` in its run log and the report's
`answer_status_counts`. It counts as an unsuccessful attempt, and the run exits
with a nonzero status after processing the selected cases. Truncated tool calls
are not executed. Token usage returned by the provider is retained in the log.
Scores continue to save every 10 attempted cases and at the end.

**Suggested fix:** increase the output budget within the model's supported limit
and retest one case before launching the full suite. For example, if the model
supports a 32,768-token output budget:

```sh
python3 scripts/benchmark.py run --provider gemini --model gemma-4-26b-a4b-it \
  --cases 1 --max-tokens 32768 --timeout 1200
```

This keeps default reasoning enabled. A larger token budget allows more reasoning
and answer text; a larger timeout only gives the request more time and does not
increase the token budget. Persistent repetitive reasoning may still fail at a
larger limit; try another model if necessary. No automatic retry or reasoning
change is performed.

Detection uses the provider's termination signal: Chat Completions
[`finish_reason: length`](https://platform.openai.com/docs/api-reference/chat/object)
or Anthropic
[`stop_reason: max_tokens`](https://platform.claude.com/docs/en/build-with-claude/handling-stop-reasons).
If the provider does not report truncation, the benchmark cannot reliably infer
it from answer length alone; other empty/invalid-answer statuses still apply.
Historical logs, including the Gemma test above, are not relabeled retroactively.

### Rate limiting and retries

API requests automatically retry HTTP 429, 500, 502, 503, and 504 responses,
connection failures, and timeouts up to five times. Backoff starts at 2 seconds,
doubles up to 60 seconds, and uses jitter between half and all of each delay.
`Retry-After` (seconds or HTTP date) is honored even when it exceeds that cap.
Retries print sanitized progress to stderr without provider response bodies or keys.

Use `--requests-per-minute` to space all API attempts, including tool turns and
retries. Choose a rate appropriate for your account; pacing is disabled by default.
For example:

```sh
python3 scripts/benchmark.py run --provider gemini --model gemini-2.5-flash --cases 1-10 --max-tokens 200000 --timeout 600 --score-every 10 --requests-per-minute 10
```

Controls: `--max-retries 5` (0 disables retries), `--retry-base-delay 2`, and
`--retry-max-delay 60`. `--timeout` applies to each attempt; waiting and retries
can extend total runtime. Pacing is local to each runner process and resets at
score batch boundaries; it does not coordinate other processes using the same key
or enforce token/daily quotas. Exhausted retries still mark the case `model_error`.

### API controls


Optional controls: `--max-turns 10`, `--max-tool-calls 20`, `--timeout 120`
(seconds per request), and `--max-tokens 4096` (output budget per turn, including
reasoning where applicable). Increase the timeout and token budget for reasoning
models. Requests are not automatically retried. HTTP 401/403 usually indicates a
key/access issue; 404 a model or endpoint issue; 429 quota/rate limits. Failures
are recorded as `model_error` and produce a nonzero exit code.

Use `--base-url https://YOUR_PROVIDER_HOST/API_PREFIX` if your account needs a
regional endpoint; this is the API base, without `/chat/completions` or `/messages`.
The default GLM endpoint is Z.AI's general API and Moonshot uses the international
API. Use an endpoint matching your key; the selected endpoint receives your key.
`--provider`, `--model-image`, and `--smoke` are mutually exclusive.

API runs send benchmark conversations and retrieved task/chart content to the
selected provider and incur its API charges. Keys stay in authentication headers
and are not written to run logs. These runs are marked `remote-api`; see
[SECURITY.md](SECURITY.md#remote-api-evaluations) for the remote evaluation boundary.

## Verify

```sh
.venv/bin/python -m unittest discover -s security-tests -v
.venv/bin/python -m unittest discover -s benchmark-ehr/tests -v
.venv/bin/python -m unittest discover -s benchmark-scoring/tests -v
bash scripts/verify_isolation.sh
docker build --pull=false -t ehr-isolation-probe security-tests/model-probe
.venv/bin/python security-tests/verify_model_runtime.py
```

PDF integration tests skip when the private source PDF is absent. Runtime checks
require a running EHR container and Docker access, and fail if either is missing.

The Compose configuration contains only the optional read-only EHR viewer.

## Rubric weights

Rubric `ehr-offline-v3` assigns 80 points to answer correctness, 10 to question
retrieval, 5 to tool execution, 2.5 to patient scope, and 2.5 to retrieval efficiency.
Accuracy is unchanged. Existing reports retain their original weights until rescored.
