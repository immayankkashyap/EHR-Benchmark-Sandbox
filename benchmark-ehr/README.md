# Patient-only EHR

Run the viewer using the combined Compose files described in the root README.
It serves only validated patient snapshots from `/data`, with no connection to
FHIR or an external network. The data mount is read-only.

`prepare.py PDF` writes patient-only snapshots to `generated/` and original
question prompts with unmarked choices to `../benchmark-tasks/` (relative to
the repository root: `benchmark-tasks/`). It excludes the PDF answer sections.

The original question bank does not supply a reviewed patient-only corpus.
Charts currently contain synthetic administrative records and a placeholder
clinical note. Questions and choices are available only through the runner's
separate `read_task` tool. See ../SECURITY.md before publishing clinical notes.

The old `ingest.py` is a legacy database utility and is not part of this viewer.
