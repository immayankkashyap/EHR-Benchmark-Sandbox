# Healthcare EHR Sandbox

A secure, isolated, and reproducible benchmarking environment designed for evaluating clinical AI models and LLM agents on electronic health record (EHR) workflows, FHIR data standards, and multi-step healthcare decision-making tasks.

---

## Project Overview & Context

Benchmarking AI models on healthcare workflows presents strict requirements around data privacy, state reproducibility, tool access, and safety isolation. The Healthcare EHR Sandbox solves this by providing a containerized ecosystem where clinical AI agents can:
1. Interact with a standardized **HAPI FHIR JPA Server** populated with case-specific clinical data.
2. Query offline **auxiliary clinical reference microservices** (Drug Interaction, Lab Reference Ranges, Dosage Guidelines).
3. Execute multi-turn reasoning loops through a centralized **Orchestrator Service**.
4. Operate under strict **network egress proxy isolation**, allowing communication only with approved LLM API provider domains (`.openai.com` and `.anthropic.com`).
5. Log structured, audit-ready **JSONL trajectories** including timestamps, tool arguments, raw responses, and latency metrics.

---

## How the Sandbox Works

### 1. Architectural Topology & Network Isolation
The sandbox utilizes a dual Docker network topology:
- **`sandbox_internal` (`internal: true`)**: A isolated bridge network with zero internet access. All core data infrastructure (PostgreSQL database, HAPI FHIR JPA server) and auxiliary reference microservices reside strictly on this network.
- **`proxy_external`**: A standard bridge network connecting the **Egress Proxy (`squid`)** to the external internet.
- **Orchestrator Gateway**: The Orchestrator container bridges both networks. All outbound internet requests from the Orchestrator are forced through the Squid egress proxy via environment variables (`HTTP_PROXY` and `HTTPS_PROXY`). Squid enforces an explicit ACL allowlist permitting traffic exclusively to `.openai.com` and `.anthropic.com`, dropping all unauthorized destination requests.

### 2. Case Ingestion & State Tagging
Clinical benchmark tasks are defined using a structured JSON case specification schema (`case-ingestion/case_spec_schema.json`). The ingestion pipeline (`case-ingestion/ingest_case.py`):
- Converts demographic and clinical data into standard FHIR `transaction` Bundles (`Patient`, `Condition`, `Observation`, `MedicationRequest`, `AllergyIntolerance`).
- Automatically tags every resource metadata header (`meta.tag`) with the unique benchmark `task_id` (`http://healthcare-ehr-sandbox.local/tags/task_id`).
- Performs pre-ingestion idempotency checks to prevent duplicate state corruption.

### 3. Unified Orchestration & Tool Execution
When a benchmark task is submitted via `POST /run-task`:
- The Orchestrator formats the prompt and exposes OpenAI-compatible tool function definitions (`query_fhir_resource`, `check_drug_interaction`, `lookup_lab_range`, `get_dosage_guideline`).
- Tool calls returned by the model are intercepted by `router.py` and dispatched over the internal network to the appropriate service.
- Standardized error handling ensures internal tool failures return structured error messages back to the agent memory for self-correction rather than crashing the evaluation loop.

### 4. Telemetry & Trajectory Logging
Every action, tool parameter, raw HTTP response, and execution latency metric is written to a JSONL log file at `/app/logs/<run_id>.jsonl`. The final clinical decision provided by the model terminates the execution loop and closes the trajectory log.

---

## Implemented Architecture & Phases

### Phase 1: Case Specification & Ingestion Interface
- JSON schema definition (`case-ingestion/case_spec_schema.json`).
- Mock patient case for `MEDMCQA-CASE-001` (`case-ingestion/mock_cases/example_case_001.json`).
- Automated FHIR Transaction Bundle converter with `task_id` resource tagging (`case-ingestion/ingest_case.py`).

### Phase 2: Offline Auxiliary Reference Microservices
- **Drug Interaction Checker** (`auxiliary-tools/drug-interaction-checker`): Fast API service providing `/check-interaction` lookups against static datasets (`interactions_v2026-09-04.json`).
- **Lab Reference Range Service** (`auxiliary-tools/lab-reference-range`): FastAPI service providing `/lab-range` lookups segmented by age, sex, and test aliases (`lab_ranges_v2026-09-04.json`).
- **Dosage Guideline Service** (`auxiliary-tools/dosage-guideline`): FastAPI service providing `/dosage` lookups by drug, indication, and weight (`dosage_guidelines_v2026-09-04.json`).
- Lifespan in-memory dataset pre-loading with standardized JSON response envelopes (`result`, `source_version`, `timestamp`).

### Phase 3: Unified Tool-Calling Orchestrator Layer
- Centralized FastAPI service in `orchestrator/`.
- OpenAI-compatible JSON function definitions in `orchestrator/app/schemas/`.
- Internal HTTP routing client (`orchestrator/app/router.py`) executing internal tool calls and recording timing metrics.
- Agent execution loop (`orchestrator/app/model_loop.py`) handling turn-by-turn prompts, tool feedback, and loop termination.

### Phase 4: Trajectory & Telemetry Logging
- Thread-safe JSONL trajectory logger (`orchestrator/app/logging/trajectory_logger.py`).
- Captures `tool_call` events, function parameters, raw HTTP payload responses, latency metrics (`latency_ms`), and `final_answer` completions.

### Phase 5: Network Isolation & Egress Proxy Configuration
- Squid proxy server setup (`networks/egress-proxy/squid.conf`) listening on port 3128 with domain allowlisting (`.openai.com`, `.anthropic.com`) and default deny rules.
- Master Compose configuration (`docker-compose.yml`) declaring `sandbox_internal` (`internal: true`) and `proxy_external` dual-network routing.
- Automated network topology verification script (`scripts/verify_isolation.sh`).

### Phase 6: State Teardown & Environment Reset
- Environment lifecycle script (`scripts/reset_and_run.sh`) executing `docker compose down -v`, stack rebuilds, HAPI FHIR `/fhir/metadata` health polling, and baseline case ingestion.

### Phase 7: End-to-End Deterministic Dry Run Harness
- Mock state machine agent (`scripted-model/scripted_agent.py`) simulating a 3-turn reasoning trajectory without live LLM API keys.
- Integration test harness (`e2e-tests/test_end_to_end_dry_run.py`) executing full environment resets, API execution triggers, log polling, and trajectory assertions.

---

## Project Structure

```
healthcare-ehr-sandbox/
├── docker-compose.yml                   # Master Compose file (Dual Network Topology)
├── docker-compose.override.yml.example  # Local development override examples
├── .env.example                         # Environment variable definitions
├── README.md                            # Complete project documentation
├── .gitignore                           # Git exclusion rules
├── networks/
│   └── egress-proxy/                    # Squid Egress Proxy container & config
│       ├── Dockerfile
│       ├── squid.conf
│       └── entrypoint.sh
├── fhir/                                # FHIR infrastructure configs & scripts
│   ├── docker-compose.fhir.yml
│   └── init/
│       └── wait-for-healthy.sh
├── synthea/                             # Synthea synthetic patient generator setup
│   ├── run_synthea.sh
│   ├── synthea.properties
│   └── output/
├── case-ingestion/                      # Case spec JSON schema & ingestion pipeline
│   ├── ingest_case.py
│   ├── case_spec_schema.json
│   ├── mock_cases/
│   │   └── example_case_001.json
│   └── tests/
│       └── test_ingest.py
├── auxiliary-tools/                     # Offline clinical reference microservices
│   ├── drug-interaction-checker/
│   ├── lab-reference-range/
│   └── dosage-guideline/
├── orchestrator/                        # Benchmark evaluation orchestrator
│   ├── Dockerfile
│   └── app/
│       ├── main.py                      # FastAPI entrypoint (POST /run-task)
│       ├── router.py                    # Tool call routing & timing layer
│       ├── model_loop.py                # Agent reasoning loop
│       ├── schemas/                     # OpenAI tool schemas
│       └── logging/                     # Trajectory logger
├── scripts/                             # Environment reset & verification scripts
│   ├── reset_and_run.sh                 # Environment reset & baseline ingestion
│   ├── verify_isolation.sh              # Network isolation assertion script
│   └── load_synthea_bundles.py
├── scripted-model/                      # Deterministic mock agent for keyless dry-runs
│   ├── scripted_agent.py
│   └── scripts/
│       └── dry_run_case_001.yaml
└── e2e-tests/                           # Integration & dry-run test suite
    └── test_end_to_end_dry_run.py
```

---

## Getting Started and Running the Sandbox

### 1. Environment Setup
Copy the environment template:
```bash
cp .env.example .env
```

### 2. Full Environment Reset and Startup
Run the automated environment setup script. This will tear down any existing containers and volumes, rebuild the image stack, wait for the FHIR server to report healthy, and ingest the baseline patient case (`example_case_001.json`):
```bash
./scripts/reset_and_run.sh
```

### 3. Verify Network Isolation
Run the network topology test to confirm internal services cannot access the internet, allowed LLM API domains route through the proxy, and non-allowlisted domains are blocked:
```bash
./scripts/verify_isolation.sh
```

### 4. Run the Deterministic End-to-End Dry Run
To verify the complete ingestion, orchestration, tool routing, and logging pipeline without requiring live LLM API keys:
```bash
python3 e2e-tests/test_end_to_end_dry_run.py
```

### 5. Triggering Benchmark Runs via API
Once the stack is running, send an evaluation task request to the Orchestrator:
```bash
curl -X POST http://localhost:8000/run-task \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "MEDMCQA-CASE-001",
    "model_provider": "scripted_agent",
    "patient_id": "MEDMCQA-CASE-001"
  }'
```

### 6. Manually Ingesting Custom Cases
To ingest a new case JSON file into the FHIR server with custom task tagging:
```bash
python3 case-ingestion/ingest_case.py path/to/your_case_spec.json
```

---

## Verification & Testing
To execute all test suites:
```bash
# Run case ingestion unit tests
python3 -m pytest case-ingestion/tests/

# Run end-to-end integration dry-run test
python3 -m pytest e2e-tests/
```
