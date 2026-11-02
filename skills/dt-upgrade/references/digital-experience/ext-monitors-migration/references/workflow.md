# Migration Workflow: 3rd-Party Monitor Migration

This reference defines the full migration workflow the agent follows after completing the intake survey. It covers the MIGRATION_PLAN.md template, both workflow branches (tests exist vs. no tests), step-by-step execution, progress tracking, and resume behavior.

Field mapping details (endpoint URLs, field renames, fan-out logic, timestamp conversion, auth scope) live in `schema-mapping.md`. Reference that file by name during relevant steps rather than duplicating its content here.

---

## 1. MIGRATION_PLAN.md Template

Before writing any code or modifying any files, the agent writes `MIGRATION_PLAN.md` into the customer's project root.

### How to fill in the template

1. Replace `{date}` with the current date (ISO 8601, e.g. `2025-07-28`).
2. Replace `{path}` with the absolute path of the detected project root.
3. Replace `{detected language}` with the language identified during the survey (e.g. `TypeScript`, `Python`, `Java`).
4. Replace `{yes / no / partial}` with the test coverage answer from Q2 of the survey.
5. Include the Prerequisites section only if Q3 (OpenPipeline ingest source) was answered `no` or `not sure`. Omit it entirely if Q3 was `yes`.
6. For Phase 1, include either Branch A or Branch B — not both — based on Q2:
   - Q2 = `yes` or `partial` → Branch A
   - Q2 = `no` → Branch B
7. Present the filled plan to the customer in full.
8. Wait for an explicit confirmation (`yes`, `go ahead`, `looks good`, or equivalent) before proceeding. Do not write any code or modify any project files before this confirmation is received.

### Template

```markdown
# Migration Plan: 3rd-Party Monitor Migration

Generated: {date}
Project: {path}
Language: {detected language}
Tests: {yes / no / partial}

## Prerequisites
- [ ] OpenPipeline `external.tests` ingest source configured

## Phase 1 — Test migration
- [ ] Read and understand existing tests
- [ ] Write contract test for new API shape (fails red)

## Phase 2 — Code migration (do not start until Phase 1 tests are green/red as required)
- [ ] Migrate models / data classes
- [ ] Migrate HTTP client (endpoint URL, auth scope, body as array)
- [ ] Migrate payload builder (fan-out per location, UUID per run, ISO timestamp)
- [ ] Run tests → all green
- [ ] Update deployment configuration (env var rename + apps-domain URL value)

## Phase 3 — Static fixture migration
- [ ] Identify static JSON fixture files using legacy SyntheticPayload format
- [ ] Run migrate_monitors.py on fixture files
- [ ] Verify migrated fixtures match new event schema

## Phase 4 — Verification
- [ ] Run DQL smoke tests (load verification.md)
- [ ] Confirm EXT_TEST Smartscape node appears
- [ ] Confirm no legacy events still arriving
```

**Branch A Phase 1 variant** (Q2 = yes or partial):

```markdown
## Phase 1 — Test migration
- [ ] Read and understand existing tests
- [ ] Write contract test for new API shape (fails red)
```

**Branch B Phase 1 variant** (Q2 = no):

```markdown
## Phase 1 — Test migration
- [ ] Write characterization tests for legacy client
- [ ] Write contract test for new API shape (fails red)
```

**Prerequisites section** — include only when Q3 = no or not sure:

```markdown
## Prerequisites
- [ ] OpenPipeline `external.tests` ingest source configured
```

---

## 2. Branch A — Tests Exist (or Partial)

Follow this branch when Q2 was `yes` or `partial`.

### Step A1 — Read existing tests

1. Read all test files in the project.
2. Identify which components are covered: HTTP client, payload builder, model/data classes.
3. Note what each test asserts: the endpoint URL being called, the auth header sent, and the shape of the request body.
4. Note any gaps — components that have no tests — because those areas carry higher migration risk.

### Step A2 — Update tests to assert the new API shape (make them red)

Do not touch production code in this step. Tests must fail red when this step is complete.

1. Update the endpoint URL assertion to target the new path. See `schema-mapping.md` § Auth and Endpoint Reference for the new path and domain format.
2. If auth scope is asserted in tests, update the expected scope from `ExternalSyntheticIntegration` to `openpipeline.events.custom`.
3. Update the request body assertion: the new body is a JSON array of events, not a single `SyntheticPayload` object. See `schema-mapping.md` § Body is always a JSON array.
4. If response handling is tested, update the expected response code to `200` (the new endpoint returns `200` with an empty body on success).
5. Run the tests and confirm they fail red. If any tests still pass, the assertion was not changed correctly — revisit.
6. Mark the Phase 1 test migration TODO as complete in `MIGRATION_PLAN.md` (change `- [ ]` to `- [x]`).

### Step A3 — Migrate models

1. Load `schema-mapping.md` and consult the Field Mapping Table.
2. Replace legacy DTO/model classes with new event classes:
   - `ExternalTestRunEvent` — required fields: `event.kind`, `event.type`, `test.id`, `test.run.id`, `test.name`, `test.type`, `test.run.status`, `test.run.availability`, `test.run.location`, `timestamp`. Optional fields: `test.run.duration_ms`, `test.frequency_sec`, `runner.name`.
   - `ExternalTestStepEvent` — required fields: `event.kind`, `event.type`, `test.run.id`, `test.id`, `test.step.index`, `test.step.name`, `test.step.status`, `timestamp`. Optional fields: `test.step.duration_ms`, `test.step.error_code`, `test.step.error_message`.
3. If the builder is being migrated in the next step and still references legacy models, keep the old model classes in place temporarily until Step A4 is complete.
4. Update `MIGRATION_PLAN.md`: mark the models TODO complete.

### Step A4 — Migrate HTTP client

Consult `schema-mapping.md` § Auth and Endpoint Reference for all URL and header details.

1. Update the endpoint URL construction to use the new path (`/platform/ingest/custom/events/external.tests`) on the apps domain. Confirm the correct apps domain with the customer — do not assume the suffix.
2. Update the auth token scope reference in any configuration, documentation, or code comments. The token value itself does not change, but a new token with `openpipeline.events.custom` scope must be issued by the customer.
3. Update body serialization: the client must now serialize a list/array of event objects, not a single object. Even a single event must be wrapped in an array.
4. Update response code handling: `200` means accepted. Treat any non-200 as an error.
5. Update `MIGRATION_PLAN.md`: mark the HTTP client TODO complete.

### Step A4a — Update deployment configuration

The env var rename (e.g. `DT_TENANT_URL` → `DT_ENV_URL`) is a breaking change at runtime: **both the variable name and the URL value it holds must change** (classic domain → apps domain). Code changes alone are not enough — the running process will fail unless the deployment configuration is also updated.

1. Identify the old URL env var name used in the source code before migration.
2. Search the project for every place that variable is defined or exported — not just source code. Check:
   - `.env`, `.env.*`, `env.example`, `.envrc`
   - `Makefile`, `GNUmakefile`, `makefile`
   - `docker-compose.yml` / `docker-compose.*.yml`
   - Kubernetes manifests (any `*.yaml` / `*.yml` containing `env:` or `envFrom:` blocks)
   - CI/CD pipeline files (`.github/workflows/`, `Jenkinsfile`, `.gitlab-ci.yml`, `bitbucket-pipelines.yml`, etc.)
   - Shell scripts that `export` the variable
3. Update every in-project file found: rename the variable and replace the URL value with the apps domain confirmed in Step A4.
4. After updating in-project files, tell the customer explicitly:

   > "The env var has been renamed from `{old_name}` to `{new_name}`, and its value must point to the **apps domain** (`{apps_domain}`) instead of the classic environment domain.
   >
   > If this variable is managed outside the repository — for example in a Kubernetes Secret, a CI/CD variable store, AWS Secrets Manager, or any other external config system — **you must update it there before deploying**. The migrated code will fail at startup until both the name and the value are updated in every environment (dev, staging, production).
   >
   > Please confirm you have updated or noted all external config locations before we continue."

5. Wait for the customer's confirmation before marking this step complete.
6. Update `MIGRATION_PLAN.md`: mark the deployment configuration TODO complete.

### Step A5 — Migrate builder

Load `schema-mapping.md` before starting. The fan-out logic, UUID generation, and timestamp conversion are all specified there.

1. Rewrite the `build()` method (or equivalent) to implement the fan-out:
   - For each entry in `testResults[]`, for each `locationResult` in `locationResults[]`: emit one `ExternalTestRunEvent`.
   - For each step in `stepResults[]` (if present and non-empty): emit one `ExternalTestStepEvent`. See `schema-mapping.md` § Step Events Rule.
2. Generate a UUID v4 for each (test, location) pair. Use the same UUID as `test.run.id` in the run event and all corresponding step events for that pair.
3. Convert `locationResult.startTimestamp` (epoch ms) to an ISO 8601 UTC string for the run event's `timestamp`. Convert `stepResult.startTimestamp` the same way for each step event. See `schema-mapping.md` § Timestamp format conversion.
4. Map `success: true` to `test.run.status: "passed"` and `test.run.availability: 1`. Map `success: false` to `test.run.status: "failed"` and `test.run.availability: 0`.
5. Handle the `deleted: true` case: emit one final run event with `test.run.status: "decommissioned"` and no step events.
6. The method must return a flat list/array of all events (run events and step events combined). Event ordering within the array does not matter.
7. Remove any now-unreferenced legacy model classes.
8. Update `MIGRATION_PLAN.md`: mark the builder TODO complete.

### Step A6 — Run tests → green

1. Run the full test suite.
2. If any tests fail, fix the implementation code. Do not modify the tests unless a test assertion is factually wrong (e.g., wrong UUID format expected, not wrong UUID value).
3. Once all tests pass, update `MIGRATION_PLAN.md`: mark the "Run tests → all green" TODO complete, which completes Phase 2.

---

## 3. Branch B — No Tests

Follow this branch when Q2 was `no`.

### Step B1 — Write characterization tests for legacy code

1. Read the existing HTTP client and payload builder code in full.
2. Write tests that capture exactly what the legacy code currently does:
   - What URL it POSTs to (full path, not just the base URL).
   - What auth header it sends (token format and header name).
   - What the serialized request body looks like — specifically that it is a single JSON object matching the `SyntheticPayload` schema.
3. Run the tests and confirm they pass green against the existing unmodified code.
4. These tests act as a safety net: if anything is accidentally broken during migration, they will catch it.

### Step B2 — Write a contract test for the new API shape (red)

1. Write a test that asserts the new endpoint URL, `openpipeline.events.custom` auth scope (in documentation or config), and a request body that is a JSON array of `external_test_run` events.
2. Run this test and confirm it fails red against the current unmodified code.
3. This test defines the migration target — it is what "done" looks like for Phase 2.
4. Mark both Phase 1 TODOs complete in `MIGRATION_PLAN.md`.

### Step B3 — Continue with Branch A

Proceed from Step A3 (Migrate models). The characterization tests from B1 serve as the safety net in place of pre-existing tests.

---

## 4. Marking TODOs Complete

After every step, update `MIGRATION_PLAN.md` immediately:

1. Open `MIGRATION_PLAN.md`.
2. Change `- [ ]` to `- [x]` for the item just completed.
3. Save the file.

Do not batch updates across multiple steps. Updating after each step is what makes the migration resumable if the session is interrupted.

---

## 5. Resume Behavior

When the agent is invoked in a session where `MIGRATION_PLAN.md` already exists in the project root:

1. Read `MIGRATION_PLAN.md`.
2. Find the first line that contains `- [ ]` (the first incomplete item).
3. Announce: `Resuming migration — next step: {item text}`.
4. Load whichever references are needed for that step (`schema-mapping.md`, `verification.md`, etc.).
5. Continue execution from that step without re-running the intake survey or re-presenting the plan for confirmation.

If all items are marked complete (`- [x]`), announce that the migration is complete and ask whether verification or cleanup is needed.

---

## 6. Phase 3 — Static Fixture Migration

Static JSON fixture files (used in tests or test data directories) may encode the legacy `SyntheticPayload` format and must be migrated separately from code.

### Finding fixture candidates

1. Search the project for all `.json` files.
2. For each file, check whether it contains both `syntheticEngineName` and `testResults` as top-level keys. Files with both keys are candidates for migration. This is the same heuristic used by the `looksLikeMonitor()` function in `migrate_monitors.py`.
3. Open each candidate and confirm it is a legacy payload before migrating.

### Running the migrator

Before running, confirm the `test.type` that applies to the fixtures being migrated. The legacy format has no type field — if the customer's monitors are browser tests, HTTP checks, or mobile tests, using the wrong type produces incorrect event metadata. Ask if unsure.

Run the migration script against the identified input directory:

```
python migrator/migrate_monitors.py --type <test_type> <input-dir> [output-dir]
```

- `--type` — required; one of `browser`, `api`, `http`, `mobile`. When a directory contains monitors of mixed types, run the script once per type on the relevant files or sub-directories.
- If `output-dir` is omitted, the script migrates fixture files in-place, overwriting the originals.
- If `output-dir` is provided, migrated files are written there and originals are left unchanged.

### Verifying migrated fixtures

1. Open each migrated fixture file.
2. Confirm the output is a JSON array.
3. Confirm each element has `event.kind: "EXTERNAL_TEST_EVENT"` and either `event.type: "external_test_run"` or `event.type: "external_test_step"`.
4. Spot-check field values against `schema-mapping.md` § Complete Example to confirm the mapping was applied correctly.
5. Once satisfied, mark the Phase 3 TODOs complete in `MIGRATION_PLAN.md`.
