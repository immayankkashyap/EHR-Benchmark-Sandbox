# Security boundary

The offline evaluation path is `scripts/benchmark.py run --model-image sha256:…`.
The host runner and offline scorer are trusted. Model code runs in a fresh container
for each turn with `--network=none`, no host mounts, no passed credentials, a
non-root UID, all capabilities dropped, no new privileges, a read-only root,
bounded temporary storage, process/memory/CPU limits, and bounded output/time.
It receives only conversation messages and two tool definitions over stdin.
The host executes validated `read_task` and `read_ehr` requests for the assigned
patient directly from immutable in-memory snapshots; the runner does not use HTTP. Model output is never executed as shell commands or Python.

Build model images in a separate, clean directory. Bake only the inference
program, dependencies and weights into the image. The adapter requires a local
immutable image ID, rejects image-declared volumes, and never pulls an image.
An image must accept one JSON object `{messages, tools}` on stdin and emit
`{"message":{"role":"assistant","content":…, "tool_calls":…}}` on stdout,
using the Chat Completions function-call shape. Put diagnostics on stderr.
Each invocation is stateless; conversation history is supplied each turn.
Default resource limits are 8 GiB RAM, four CPUs, 128 processes, 256 MiB tmpfs,
1 MiB response and the runner's `--timeout` (120 seconds by default).
GPU devices are intentionally not exposed.

The EHR serves a validated in-memory patient snapshot. It has no database or
outbound proxy connection and mounts only generated patient records read-only.
Startup rejects records that differ from the canonical patient-only schema,
including extra narrative, extension, URL, attachment or metadata fields.
There is no filesystem serving route, arbitrary FHIR search, write endpoint,
pagination proxy or history endpoint. The optional host browser viewer binds only to loopback and serves the same validated snapshot. The Docker viewer publishes no ports (including on Docker Desktop).
The build context explicitly excludes all unneeded files.

`benchmark-tasks/` contains the original prompts and unmarked choices, never
answer sections. Only the trusted runner reads these files. `evaluation-private/`
contains the key, scores and run logs; none are mounted into model containers.
Scoring runs after model execution and is not a model tool. Source PDFs, Git
history, host files and old database contents remain on the trusted host.
Do not grant a model host shell access or launch it directly in this checkout.

## Dataset limitation

The supplied source is a question bank, not a patient-only clinical dataset.
All 500 original question notes have been removed from EHR artifacts and moved
to task prompts. EHR records currently contain synthetic administrative data and
a notice that no reviewed clinical note is available. This preserves question
answering, but does **not** constitute a realistic clinical retrieval benchmark.
Publishing clinical vignettes as chart notes requires a reviewed patient-only
corpus and an explicit change to the validator; automatic answer-word filtering
cannot establish that a clinical narrative has no answer leakage.

## Deployment and verification

Run `docker compose -f docker-compose.yml -f benchmark-ehr/compose.yml up -d --build ehr-viewer`
and `bash scripts/verify_isolation.sh`. The latter fails on missing containers,
missing Docker access or failed probes; a failed command is never considered
proof of blocked traffic. Run the unit checks documented in README as well.
Stop old legacy services before evaluating; existing containers do not inherit
new configuration until recreated. Legacy FHIR tooling is behind the explicit
`legacy` profile, is outside the strict evaluation path, and must not be exposed
to model code. The historical proxy now denies all traffic.

Docker isolation does not protect against a compromised host/kernel/runtime or
answers memorized in model weights or deliberately baked into an image. For
hostile third-party images, use a dedicated disposable VM or stronger runtime
isolation on a separate machine with no evaluator secrets. A remote inference
provider cannot be verified to perform no hidden retrieval, so remote API runs
do not provide the offline isolation guarantee. Local source data and image supply
chains remain trusted inputs requiring review.

Implementation references: [Docker network isolation](https://docs.docker.com/engine/network/)
and [Compose service security controls](https://docs.docker.com/reference/compose-file/services/).

## Remote API evaluations

`run --provider PROVIDER --model MODEL_ID` explicitly selects host-side HTTPS
inference. The provider receives the conversation, assigned task and any chart
resources retrieved through the two validated tools. Credentials are read from
host environment variables and sent only in authentication headers. The adapter
does not send answer keys, scores or other host files, and provider errors are
logged without response bodies or credentials. No provider web search or code
execution tools are enabled. Tool scope validation and host-only scoring apply
to both transports. API runs are labeled `remote-api` in run metadata; they must
not be represented as offline-isolated evaluations. Custom `--base-url` endpoints
receive the selected provider credential and must be trusted.
