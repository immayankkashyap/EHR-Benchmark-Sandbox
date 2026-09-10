# Restricted EHR benchmark

Models can run offline in disposable containers or through provider APIs. EHR records contain only synthetic
patient administrative data; question prompts and unmarked choices are separate,
and answer keys and scores stay in the trusted host evaluator.

Read [SECURITY.md](SECURITY.md) for the enforced boundaries, image protocol,
resource limits and dataset limitations. This is currently a question-answering
benchmark: reviewed clinical chart narratives have not been supplied.

## Start the EHR

```sh
docker compose -f docker-compose.yml -f benchmark-ehr/compose.yml up -d --build ehr-viewer
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

The old FHIR stack and demonstration orchestrator are available only through the
`legacy` Compose profile. They are not part of the supported secure runner.
