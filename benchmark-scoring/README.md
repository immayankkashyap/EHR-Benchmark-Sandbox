# Test a model against the 500 EHR cases

The runner lets a model retrieve each question from the live EHR, records its
answer and tool trajectory, and then runs a separate offline scorer against the
answers supplied in `medxpertqa_salted_500_curated.pdf`.

The primary result is **answer accuracy**. A versioned 100-point rubric adds
observable EHR retrieval and tool-use measures. It does not grade medical reasoning
or establish clinical safety. PDF keys are treated as ground truth exactly as
supplied; they have not been independently clinically adjudicated.

## 1. Setup

Requirements: Python 3.10+, Docker with Compose, and the source PDF in the repository
root. Start Docker Desktop, then run these commands from the repository root:

```sh
python3 scripts/benchmark.py setup
```

This installs the pinned PDF/HTTP dependencies in `.venv`, prepares the 500 sanitized
FHIR cases, extracts the evaluator-only answer key and 500 task rubrics, starts the
EHR, and uploads/verifies every case. It does not reset or delete existing data.
If interrupted, rerun setup: deterministic FHIR PUTs avoid duplicate records.

View patient charts at **http://localhost:8090**.

## 2. Check the pipeline without an API key

```sh
python3 scripts/benchmark.py smoke
```

This runs three cases through the live EHR and scorer. The scripted client retrieves
the question and always chooses A; it never reads the key. Expect one tool call,
one tool turn, and two model turns per case. Its accuracy is meaningless as a model
comparison. The report labels it `smoke-always-A-NOT-A-MODEL`.

## 3. Test your model

The model endpoint must implement non-streaming `/chat/completions` with function
tool calling. The adapter uses the message/tool-result sequence documented in the
[official function-calling guide](https://developers.openai.com/api/docs/guides/function-calling).
Responses-only endpoints and native provider protocols need an adapter; changing
`--base-url` alone does not translate those protocols.

Set your provider credential in `MODEL_API_KEY` using your shell or secret manager.
The runner reads this environment variable; it does not print or write the key.
Then run a small sample first:

```sh
python3 scripts/benchmark.py run \
  --model YOUR_MODEL_ID \
  --base-url https://api.openai.com/v1 \
  --cases 1-10 \
  --output evaluation-private/my-model-sample
```

For a local compatible server, use its base URL and served model ID:

```sh
python3 scripts/benchmark.py run \
  --model YOUR_LOCAL_MODEL_ID \
  --base-url http://localhost:8000/v1 \
  --cases 1-10 \
  --output evaluation-private/local-model-sample
```

No API key is needed for a local server that does not require authentication.
The existing demo orchestrator also uses host port 8000; choose another port for
your model server if that service is running.

Run the entire dataset after the sample works:

```sh
python3 scripts/benchmark.py run \
  --model YOUR_MODEL_ID \
  --base-url https://api.openai.com/v1 \
  --cases 1-500 \
  --max-turns 10 \
  --max-tool-calls 20 \
  --output evaluation-private/my-model-full
```

Each command prints a summary and writes `report.md`, `report.json`, and a `logs/`
directory below the chosen output directory. Use a fresh output directory for every
run; mixing repeated runs is refused. Ranges such as `--cases 1-10,25,100-110` are
supported. Omit `--output` to create a timestamped directory automatically.

Other options:

- `--viewer http://localhost:8090`: the live EHR viewer/backend.
- `--timeout 120`: per-model-request timeout in seconds.
- `--api-key-env CUSTOM_KEY_NAME`: read a different environment variable.
- `--parameters model-parameters.json`: additional model sampling/token settings.
  Allowed keys are `temperature`, `top_p`, `max_completion_tokens`, `max_tokens`,
  `seed`, and `reasoning_effort`. Supply only settings supported by your model.
  Example: `{"max_completion_tokens": 4096}`. Without this file, provider defaults
  apply; the runner still limits model turns and total executed tool calls.

The runner sends synthetic benchmark question data to the endpoint you specify.
Only the `read_ehr` function is available to the model. It is read-only, limits
access to the assigned patient, and returns the original note as decoded text
along with its FHIR resource. No shell, filesystem, search, or answer-key tool is
exposed. This local runner is separate from the original mock orchestrator and
uses direct HTTP connections; it does not run through the demo egress proxy.

## 4. The per-task rubric

`evaluation-private/task-rubrics.json` contains **500 separate rubric entries**,
keyed by `mxq-0001` through `mxq-0500`. Each binds the rubric to that task's exact
patient reference, note reference, question hash, correct standalone choice, and
expected answer text. Source task type and body system are retained only in these
evaluator files for reporting. The common rules below apply equally to all cases.

| Criterion | Points | Exact rule |
|---|---:|---|
| PDF-answer agreement | 60 | All 60 for an unambiguous choice whose option text matches the PDF key; otherwise 0. |
| Question retrieval | 20 | All 20 when a successful tool response before the final answer includes the assigned patient's note with the exact expected SHA-256; otherwise 0. |
| Tool execution | 10 | `10 × successful calls / all calls`. Explicit errors, missing responses and FHIR fatal/error outcomes fail. No calls earns 0. |
| Patient scope | 5 | All 5 when calls occurred, responses are present, and there was no observed wrong-patient request, blocked scope violation, or wrong-patient response; otherwise 0. |
| Retrieval efficiency | 5 | `5 / total tool calls` if the exact question was retrieved; otherwise 0. |

Rubric version: **ehr-question-v1**. The executable rules live in `rubrics.py`;
`build_key.py` generates task-specific bindings from the PDF. Regenerate the key
and rubrics after intentional source changes, and version any scoring rule changes.
Editing a generated rubric file alone does not change the scorer's rules.

A model that retrieves correctly but selects the wrong answer can earn at most
40/100. Its answer accuracy is still zero for that task. Compare answer accuracy
first; the composite reflects this repository's chosen weights, not a validated
clinical quality scale. A correct answer without observed note retrieval gets
answer credit but fails the retrieval criterion. `accuracy_with_verified_retrieval`
reports the stricter combination.

The one-call efficiency baseline is appropriate because every case currently stores
all clinical information in one note. This benchmark does not demand fabricated lab,
dosage, or diagnostic-tool steps. Repeated and unsuccessful calls are reported even
when a model eventually succeeds. Efficient tool usage does not prove sound clinical
reasoning, and more calls are not automatically clinically inappropriate.

### Answer format and choice ordering

The PDF often contains an inline `(A)…(J)` list and a separately ordered standalone
`A.…J.` list. The new runner explicitly instructs every model to use the **standalone
list**, without altering the original question. Required final output:

```json
{"choice": "B", "choice_set": "standalone"}
```

`B` above illustrates the format, not a general correct answer. Optional `answer_text`
must exactly agree with that selected option. The scorer accepts exact option text
(case and whitespace normalized), plain letters, or `B. option text` for imported
logs. It does not infer a selection from a long rationale, accept multiple candidates,
or let contradictory letter/text pairs pass. Numeric option text is supported.

For externally collected inline-label answers, explicitly set `choice_set` to
`inline` per answer or pass `--choice-set inline` to the scorer. Inline labels are
mapped by option text. All 500 standalone mappings were validated; 499 inline
lists parsed unambiguously. An unmapped inline selection is rejected rather than
guessed. Do not silently change the label convention between models.

### Tool metrics and turns

- **Tool calls:** number of executed function invocations, including failed calls.
- **Tool turns:** model responses that request at least one tool; several calls in
  one response count as one turn. A request rejected for exceeding the call budget
  still counts as a tool turn, but its unexecuted calls are not executed-call counts.
- **Model turns:** model requests, including the final-answer request and failed API
  requests. One retrieval response followed by one final answer is two model turns.
- **Success rate:** fraction of tool calls without an explicit reported failure;
  this is execution success, not a judgment that the tool was clinically useful.
- **Verified retrieval:** assigned patient plus exact note hash, before submission.
- **Repeated calls:** repeated tool name and identical argument JSON, including retries.
- **Empty results:** empty FHIR search Bundles, distinct from request failures.
- **Patient scope:** observed mismatched requests/responses and blocked requests.
- **Latency:** per-call and summed tool duration, model duration, and total run time.
  Calls within a model turn are executed serially in this runner.
- **Tokens:** provider-reported prompt/completion/total tokens when available.

Logs from the old orchestrator can be scored if their task IDs are in this dataset.
They lack model-turn instrumentation, so unavailable turn counts are `null`, never
estimated from call counts. Use the new runner for comparable complete metrics.

### Aggregation and failures

Reports show submitted-run accuracy, dataset coverage, average criterion points,
mean calls/turns, retrieval rate, per-source-task-type accuracy, and per-run detail.
`accuracy_over_full_dataset` treats missing cases as failures and is only emitted
when there is at most one run per case. With repeated case runs it is `null`; no
best-of-run selection occurs. Submitted-run accuracy weights every submitted run.
Use identical case sets, rubric/protocol versions, budgets, model settings and
endpoint configuration for comparisons. Pin model versions when your provider allows.

A missing/multiple final answer, exhausted budget, truncated response or model error
cannot earn answer credit. Invalid/ambiguous answers get no answer credit. Already
observed retrieval/tool behavior is still scored. Provider errors are logged by
exception type and HTTP status without response bodies or credentials. Failed runs
remain in reports and the run command exits nonzero. There are no automatic API
retries; retries would otherwise change the measured budget and latency.

## 5. Score existing trajectories

```sh
python3 scripts/benchmark.py score \
  --logs evaluation-private/my-model-full/logs \
  --output evaluation-private/rescored/report.json
```

One JSONL event per line. Every event needs `run_id` and `task_id`. New runner events:
`run_start`, `model_turn`, `tool_call`, `final_answer`, `run_end`; error/budget events
may also occur. `tool_call` includes `turn`, `tool_name`, `arguments`, `raw_response`
and `latency_ms`. A final answer uses `answer`; `run_start` identifies `model`.
No logs or unknown dataset task IDs cause an explicit error instead of a fabricated
score. Original solved demo-case logs should not be mixed into this dataset's logs.

## Ground-truth separation

`evaluation-private/answer-key.json` and `task-rubrics.json` are evaluator-only,
created with restrictive file permissions and excluded from Git. They contain the
correct answers, unlike reports and model-input notes. Neither file is copied into
an EHR image, served by the viewer, mounted into a model container, or sent in a
model request. The runner does not read either file. The separate scorer reads
trajectories after the runner finishes. The original PDF also contains answer keys;
do not expose the repository filesystem/PDF to a separately built agent.

## Verification

```sh
.venv/bin/python -m unittest discover -s benchmark-scoring/tests -v
.venv/bin/python -m unittest discover -s benchmark-ehr/tests -v
python3 scripts/benchmark.py smoke
```

The smoke test validates live EHR retrieval, logging and offline scoring without
paid API calls. It is not evidence about any real model's accuracy or reliability.
