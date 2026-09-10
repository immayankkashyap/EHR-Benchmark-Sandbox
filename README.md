# Restricted EHR benchmark

Models run offline in disposable containers. EHR records contain only synthetic
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

Remote APIs are disabled. No host files, model credentials, evaluator keys or
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
