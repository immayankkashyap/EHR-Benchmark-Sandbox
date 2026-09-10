# MedXpertQA question-only EHR

Open **http://localhost:8090** and choose a patient. Search by `MXQ-0001`
through `MXQ-0500`, or by question number. Each chart shows its patient ID,
synthetic visit date, synthetic attending doctor, original question note, and
expandable live FHIR resources. Diagnosis is shown as withheld for benchmarking.
This is a hospital-style research chart viewer, not a production hospital EHR.

## Start or resume

Run from the repository root with Docker Desktop running:

```sh
docker compose -f docker-compose.yml -f benchmark-ehr/compose.yml up -d ehr-viewer
```

This starts the existing PostgreSQL and HAPI FHIR services plus the viewer.
Existing database contents persist in `postgres_data/`. Do not run the project's
reset script for this workflow: it also loads an unrelated solved demo case.
The FHIR server stays on the internal network. The viewer publishes only localhost
port 8090 using a separate access network (needed for Docker Desktop port forwarding).
The viewer exposes only read-only dataset-specific routes, never the original PDF.

## Regenerate and ingest

```sh
python3 -m venv .venv
.venv/bin/pip install -r benchmark-ehr/requirements.txt
.venv/bin/python benchmark-ehr/prepare.py medxpertqa_salted_500_curated.pdf
docker compose -f docker-compose.yml -f benchmark-ehr/compose.yml up -d --build ehr-viewer
docker compose -f docker-compose.yml -f benchmark-ehr/compose.yml exec -T ehr-viewer python ingest.py --fhir http://hapi-fhir-jpaserver:8080/fhir --data /data
```

Wait for HAPI startup before ingestion. Upload uses deterministic PUT identifiers
and can be rerun after interruption without creating duplicate patients or visits.
The importer reads every resource back and checks every question's SHA-256.
Completion is recorded in `generated/ingestion-report.json`.

## Content policy

- Exactly one patient, encounter, practitioner, organization and DocumentReference
  per question: 500 cases, 2,500 resources.
- Question text is the exact pypdf-extracted substring following `Salted:` and
  before `Answer:`. Page layout becomes extracted text/line breaks; no clinical
  rewriting, paraphrasing, correction, or answer generation occurs.
- Both choice lists present in the PDF are preserved, even when their order differs.
  Unmarked candidate options are part of the question; the keyed answer and its
  wrapped continuation are excluded entirely.
- Source IDs, canary IDs, task/body-system classification and perturbation logs
  are excluded from EHR resources. The original PDF remains outside the viewer
  image and outside the FHIR database. It contains keys and must not be supplied
  to a benchmark agent as an input document.
- Diagnoses already written in the original question remain there to preserve its
  content. No Condition resources, Encounter diagnoses, inferred diagnoses,
  answer selections, clinical orders or generated clinical facts are added.
- Names, MRNs, doctor identities, hospital, virtual encounter and dates are
  deterministic synthetic administrative metadata. Actual age, sex and other
  provided clinical information remain in the original note; no guessed DOB or
  conflicting structured demographics are introduced.
- DocumentReference is the FHIR R4 resource for the original note; Encounter
  connects the note, patient, visit, practitioner and hospital. See the official
  [DocumentReference](https://hl7.org/fhir/R4/documentreference.html) and
  [Encounter](https://hl7.org/fhir/R4/encounter.html) specifications.

## Benchmark access

Within the sandbox network use `http://hapi-fhir-jpaserver:8080/fhir`:

```text
GET /Patient/mxq-0001
GET /Encounter/mxq-0001-visit
GET /DocumentReference?patient=mxq-0001
```

Decode `DocumentReference.content[0].attachment.data` from base64 to UTF-8 to
obtain the unchanged question and unmarked choices. Dataset tag system:
`http://healthcare-ehr-sandbox.local/tags/dataset`, code:
`medxpertqa-salted-500-curated`. Task IDs are `mxq-0001` through `mxq-0500`.

The viewer provides `GET /api/patients` and `GET /api/chart/mxq-0001` on localhost:8090.

## Tests

```sh
.venv/bin/python -m unittest discover -s benchmark-ehr/tests -v
```

Tests cover all 500 PDF extractions, exact note round-trips, wrapped answer-key
removal, exclusion of metadata, deterministic IDs, and rejection of malformed
or incomplete question boundaries. Ingestion performs additional live read-back
verification against the database.

## Evaluate a model

See [the runner, per-task rubrics, and scoring guide](../benchmark-scoring/README.md).
The answer key and task rubrics are held outside the EHR in `evaluation-private/`.
