# Healthcare EHR Sandbox

A comprehensive benchmarking environment and sandbox for evaluating AI models and agents on clinical workflows, FHIR data structures, and complex healthcare decision-making tasks.

---

## Project Purpose

The Healthcare EHR Sandbox provides an isolated, reproducible, and secure testing environment for clinical LLM agents. It pairs a standard FHIR (Fast Healthcare Interoperability Resources) data store with clinical reference auxiliary tools, network proxy isolation, and evaluation orchestrators to safely benchmark model performance on realistic patient cases.

---

## Implementation Progress

### Completed Features and Scaffolded Architecture

#### 1. Repository Infrastructure and Design Architecture
- **Directory Structure**: Fully scaffolded workspace covering network proxies, FHIR configuration, Synthea generators, case ingestion, auxiliary microservices, evaluation orchestration, and test suites.
- **Configuration and Environment**: Set up root configuration including `.env.example`, `.gitignore`, `docker-compose.yml`, and `docker-compose.override.yml.example`.
- **Standards and Guidance**: Added module-level docstrings detailing Phase and Purpose across all Python files.

#### 2. Phase 1: Case-Spec Ingestion Interface
- **Case Specification JSON Schema (`case-ingestion/case_spec_schema.json`)**:
  - Defines the formal schema for synthetic clinical case specifications.
  - Enforces `metadata` (`task_id`, `salted_fields`, `snapshot_date`), `patient` demographics (ID, name, gender, birth date), and resource arrays for `conditions`, `observations`, `medications`, and `allergies`.
- **Mock Clinical Case (`case-ingestion/mock_cases/example_case_001.json`)**:
  - Realistic mock patient case for benchmark task `MEDMCQA-CASE-001`.
  - Includes patient demographics, active abdominal pain condition, heart rate and blood pressure panel observations, morphine medication request, and penicillin allergy.
- **Ingestion Pipeline (`case-ingestion/ingest_case.py`)**:
  - Translates case-spec JSON files into standard FHIR `transaction` Bundles (`Patient`, `Condition`, `Observation`, `MedicationRequest`, `AllergyIntolerance`).
  - **Resource Tagging**: Inserts the `task_id` into `meta.tag` for every generated FHIR resource to enable precise teardown and isolation during evaluation cycles.
  - **Idempotency and Safety**: Performs pre-ingestion checks against `GET /fhir/Patient?_tag={task_id}` to prevent duplicate resource creation.
  - **CLI and Logging**: Built with `argparse`, `requests`, error handling, and python type hinting.

#### 3. Phase 2: Auxiliary Microservices (Offline Lookup Tools)
- **Drug Interaction Checker (`auxiliary-tools/drug-interaction-checker/`)**:
  - `GET /check-interaction` endpoint querying interactions between `drug_a` and `drug_b` (order-independent).
  - Loaded static dataset `interactions_v2026-09-04.json` into memory during application startup using FastAPI lifespan events.
  - Dockerized microservice exposing port 8000.
- **Lab Reference Range Lookup (`auxiliary-tools/lab-reference-range/`)**:
  - `GET /lab-range` endpoint returning test reference ranges for `test`, `age`, and `sex`.
  - Loaded static dataset `lab_ranges_v2026-09-04.json` into memory during startup.
  - Dockerized microservice exposing port 8000.
- **Dosage Guideline Lookup (`auxiliary-tools/dosage-guideline/`)**:
  - `GET /dosage` endpoint returning dosage guidelines based on `drug`, optional `indication`, and `weight_kg`.
  - Loaded static dataset `dosage_guidelines_v2026-09-04.json` into memory during startup.
  - Dockerized microservice exposing port 8000.
- **Standardized Response and Safety Constraints**:
  - Fully offline implementation with zero external API calls.
  - Uniform response envelope returning `result`, `source_version`, and UTC `timestamp`.
  - Error handling with HTTP 404 for unknown entries and HTTP 422 for invalid/missing query parameters.

#### 4. Infrastructure and Network Isolation Setup
- **Network Egress Proxy**: Squid proxy Dockerfile and configuration in `networks/egress-proxy/` to restrict outgoing sandbox network requests.
- **FHIR Infrastructure**: HAPI FHIR JPA server backed by PostgreSQL (`fhir/docker-compose.fhir.yml`) with healthcheck scripts (`fhir/init/wait-for-healthy.sh`).
- **Automation Scripts and Baselines**: Shell scripts for environment resets (`scripts/reset_and_run.sh`), network isolation verification (`scripts/verify_isolation.sh`), Synthea bundle loading (`scripts/load_synthea_bundles.py`), and a deterministic scripted agent baseline (`scripted-model/scripted_agent.py`).

---

## Project Structure

```
healthcare-ehr-sandbox/
├── docker-compose.yml                   # Root docker-compose configuration
├── docker-compose.override.yml.example  # Local development overrides example
├── .env.example                         # Environment variable definitions
├── README.md                            # Project documentation
├── .gitignore                           # Git exclusion rules
├── networks/
│   └── egress-proxy/                    # Egress proxy Dockerfile & Squid config
├── fhir/
│   ├── docker-compose.fhir.yml          # FHIR server service definitions
│   └── init/
│       └── wait-for-healthy.sh          # Healthcheck polling script
├── synthea/
│   ├── run_synthea.sh                   # Synthea data generation trigger script
│   ├── synthea.properties               # Synthea configuration properties
│   └── output/                          # Generated patient bundles target directory
├── case-ingestion/
│   ├── ingest_case.py                   # Case JSON -> FHIR Transaction Bundle ingestion
│   ├── case_spec_schema.json            # Case specification JSON schema
│   ├── mock_cases/                      # Benchmark case JSON files
│   │   └── example_case_001.json        # Example case (MEDMCQA-CASE-001)
│   └── tests/
│       └── test_ingest.py               # Unit tests for case ingestion
├── auxiliary-tools/                     # Clinical reference microservices
│   ├── drug-interaction-checker/        # Drug-drug interaction checker API & Dockerfile
│   ├── lab-reference-range/             # LOINC lab reference range lookup API & Dockerfile
│   └── dosage-guideline/                # Dosing guidance lookup API & Dockerfile
├── orchestrator/                        # Benchmark evaluation orchestrator
│   ├── Dockerfile                       # Orchestrator Docker container definition
│   └── app/
│       ├── main.py                      # Orchestrator FastAPI entrypoint
│       ├── router.py                    # Tool call routing layer
│       ├── model_loop.py                # Model evaluation execution loop
│       ├── schemas/                     # Tool schemas (FHIR & Auxiliary)
│       └── logging/                     # Trajectory logger (JSONL logger)
├── scripts/                             # Utility & reset scripts
│   ├── reset_and_run.sh                 # Environment reset automation
│   ├── load_synthea_bundles.py          # Bulk bundle loader script
│   └── verify_isolation.sh              # Network isolation test script
├── scripted-model/                      # Baseline agent execution
│   ├── scripted_agent.py                # Deterministic baseline agent
│   └── scripts/
│       └── dry_run_case_001.yaml        # Pre-scripted action steps
└── e2e-tests/                           # End-to-end integration tests
    └── test_end_to_end_dry_run.py
```

---

## Getting Started and Usage

### 1. Environment Setup
Copy the environment template:
```bash
cp .env.example .env
```

### 2. Start FHIR and Infrastructure Services
Launch the FHIR server and PostgreSQL database:
```bash
docker-compose up -d
```
Check FHIR server health:
```bash
./fhir/init/wait-for-healthy.sh
```

### 3. Ingest a Case Specification
Run the Phase 1 case-spec ingestion pipeline to convert a case JSON file into tagged FHIR resources:
```bash
python3 case-ingestion/ingest_case.py case-ingestion/mock_cases/example_case_001.json
```

### 4. Running Auxiliary Tool Services Locally
Build and run any of the microservices individually:
```bash
# Drug Interaction Checker
cd auxiliary-tools/drug-interaction-checker
docker build -t drug-interaction-checker .
docker run -p 8000:8000 drug-interaction-checker

# Lab Reference Range Service
cd auxiliary-tools/lab-reference-range
docker build -t lab-reference-range .
docker run -p 8000:8000 lab-reference-range

# Dosage Guideline Service
cd auxiliary-tools/dosage-guideline
docker build -t dosage-guideline .
docker run -p 8000:8000 dosage-guideline
```

---

## Verification and Testing
Run unit tests and dry runs:
```bash
python3 -m pytest case-ingestion/tests/
python3 -m pytest e2e-tests/
```
