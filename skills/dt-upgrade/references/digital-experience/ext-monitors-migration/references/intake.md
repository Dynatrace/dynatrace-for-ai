# Intake Survey

Run this survey at the very start of every migration session, before reading any project files or writing any code. Follow the steps exactly in order.

## Step 0 — Check for an existing migration plan

You do not yet know the project path. Ask Q1 first, then immediately check for a resume condition before continuing.

## Q1 — Project location

Ask verbatim:

> "Where is the project located? Please share a file system path (e.g. `/home/user/myapp`) or describe the repository structure if you don't have a local path."

**After receiving the answer:**

1. Navigate to the project root (or the closest equivalent you can access).
2. Check whether `MIGRATION_PLAN.md` exists in that root.

**If `MIGRATION_PLAN.md` exists — resume mode:**

- Read the file.
- Find the first unchecked item (`- [ ]`).
- Tell the customer: "Found an existing migration plan — resuming from: [step name]."
- Stop the survey here. Skip Q2 and Q3. Jump directly to execution of that step.

**If `MIGRATION_PLAN.md` does not exist — continue to discovery:**

- List the project files and read the key source files (entry points, build files, test directories, any files that import from a synthetic or monitor-related module).
- Infer: language, test framework, component structure (model classes, HTTP client, builder/factory, static fixture files).
- Do NOT ask the customer to describe these — derive them from the code.
- Proceed to Q2.

## Q2 — Existing tests

Ask verbatim:

> "Does the project have existing tests that cover the monitor integration code?
>
> - **yes** — tests exist and cover the relevant components
> - **partial** — some components are tested, not all
> - **no** — no tests exist for this code"

**After receiving the answer:**

| Answer | Workflow branch |
|---|---|
| yes | Test-first: update existing tests before migrating any production code. |
| partial | Treat as yes — update tests that exist, add missing tests for untested components, then migrate production code. |
| no | No-tests branch: write characterization tests against the current (old) API first, then write a contract test for the new API, then proceed as test-first. |

Record the answer — it determines the order of steps in `MIGRATION_PLAN.md`.

Proceed to Q3.

## Q3 — OpenPipeline configuration

Ask verbatim:

> "Is the OpenPipeline `external.tests` ingest source already set up in your Dynatrace tenant?
>
> - **yes** — the ingest pipeline is configured
> - **no** — it is not yet configured
> - **not sure** — I don't know
>
> Context: the migrated code sends events to `POST /platform/ingest/custom/events/external.tests`. If this endpoint does not exist in your tenant, all events will be rejected with HTTP 404. The pipeline is created automatically when the Dynatrace 3rd-party monitors Monaco bundle is deployed."

**After receiving the answer:**

- **yes** → Proceed to the post-survey action below.

- **no** or **not sure** → Ask:

  > "Would you like guidance on deploying the Monaco bundle before we proceed with the code migration?"

  - If **yes to guidance**: explain the Monaco bundle deployment step (refer to `workflow.md` for the prerequisite instructions), confirm the customer has completed it or is ready to proceed, then continue to the post-survey action.
  - If **no to guidance**: add the following item at the top of `MIGRATION_PLAN.md` as a prerequisite before all other steps:

    ```
    - [ ] PREREQUISITE: Deploy the Dynatrace 3rd-party monitors Monaco bundle to create the OpenPipeline `external.tests` ingest source. Without this step, migrated code will receive HTTP 404 on all event submissions.
    ```

    Then continue to the post-survey action.

## Post-survey action

Execute these steps immediately after the survey is complete and any OpenPipeline prerequisite is resolved:

1. Load `schema-mapping.md` and `workflow.md`.
2. Generate `MIGRATION_PLAN.md` in the project root. The plan must:
   - List every migration step as a `- [ ]` checkbox item.
   - Follow the workflow branch determined by Q2 (test-first or no-tests).
   - Include the OpenPipeline prerequisite item at the top if applicable.
3. Present the full plan to the customer.
4. Wait for explicit approval before touching any code or fixture files.
