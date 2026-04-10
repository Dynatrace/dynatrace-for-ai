---
agent: agent
description: Troubleshoot an existing Dynatrace problem. Starts with the Root Cause Agent to list problems, scopes log queries to the problem timeframe, classifies actionable errors, and hands off to trace investigation.
---

# Troubleshoot a Dynatrace Problem

## Rules

- **ALWAYS start with problems.** Never do broad log searches. Use root_cause_agent first, then scope all queries to problem context.
- **NEVER query logs without a problem context.** Broad log searches hit the 500GB scan limit and return 0 results.
- **NEVER suggest checking other environments.** This prompt is for production troubleshooting only. Only mention dev/staging if the user explicitly asks.

## Input

This prompt accepts two input formats:

**Format A — Pre-filled structured input:**
> "At [timestamp], service [service-name] has the following problem: [problem message]. Explain the error and suggest how to fix it."

If this format is detected, extract `timestamp`, `service-name`, and `problem message` directly. Use the **Root Cause Agent** to find and confirm the matching problem (do not present the full list to the user). Extract `problemId`, affected entity IDs, and the exact timeframe from the problem metadata, then proceed to step 3.

**Format B — Manual:**
If no structured input is provided, proceed from step 1.

## Steps

### 1. List active problems *(skip if pre-filled input was provided — use root_cause_agent silently to confirm problem context)*

Use the **Root Cause Agent** to retrieve all currently active problems on the tenant.

Present results as a table:

| # | Problem ID | Title | Severity | Status | Start Time | Affected Entities |
|---|---|---|---|---|---|---|

If there are no active problems, check for recently closed problems (last 7 days) and show those instead.

**If no problems exist at all in the last 7 days:**
1. Confirm the service name is correct
2. Confirm you are connected to the intended production tenant/environment
3. Stop here — do NOT run broad log queries
4. Tell the user: "No problems found in this environment in the last 7 days. The issue may have affected a different service, or was not raised as a Dynatrace problem (for example, logged only below ERROR level)."

### 2. Select a problem *(skip if pre-filled input was provided)*

Ask the user: *"Which problem would you like to investigate? Please enter the number or Problem ID."*

Wait for their response before proceeding.

### 3. Scope the investigation

From the selected problem's metadata (or from the pre-filled input), extract:
- `problemId` (if available)
- `startTime` and `endTime` (or "now" if the problem is still active)
- affected entity names/IDs or service name
```
queryFrom = startTime - 5 min
queryTo = endTime + 5 min  (or now + 5 min if still active)
```

### 4. Query logs for the problem

Use the **Data Analysis Agent** to run a **problem-scoped** log query for the affected entities and computed timeframe.

Do not hardcode DQL in this prompt. Build and validate query details using the platform's agent guardrails and observability best practices.

Adjust entity scope based on problem metadata (service, host, process group, etc.).

If the query is too broad (including data-scan-limit warnings), stop and narrow scope using agent guardrails before retrying. If scope cannot be narrowed with available metadata, ask the user for a tighter timeframe or a specific error pattern.


### 5. Classify errors

For each distinct error message found, classify it using the table below:

| Error Message | Count | Actionable? | Reason |
|---|---|---|---|

Use this guidance:
- Mark errors as actionable when they indicate app logic bugs, infra/platform failures, or clearly misconfigured auth/permissions.
- Mark as non-actionable when they represent expected behavior or third-party conditions outside immediate control.
- If uncertain, classify as context-dependent and state what additional context is needed.

### 6. Investigate trace (if trace ID found)

Search the returned log entries for `trace_id` or `dt.trace_id` fields. This is a required step — not optional.

If no trace IDs appear in log fields, note this explicitly and recommend the user check if trace propagation is configured for the service.

If trace IDs are found, take the most relevant one and reconstruct the request flow.

Do not hardcode DQL in this prompt. Generate and validate trace/log queries using the platform's tracing and log-analysis best practices.

Build a timeline from the spans:

| Span | Service | Operation | Duration | Status | Parent Span |
|---|---|---|---|---|---|

Highlight any span with `status == "ERROR"` or HTTP status ≥ 500. Identify the **first span where an error occurred** — that is the error origin.

For the erroring service, retrieve correlated logs for the same trace and timeframe.

Summarize the trace findings:
- **Trace flow**: Services involved in order.
- **Error location**: Service, operation, and timestamp where it failed.
- **Error message**: The exact error or exception.
- **Likely cause**: Based on the error message and call chain.

### 7. Summarize findings

Provide a concise summary:

- **Root cause hypothesis**: What Davis AI identified, and what the logs and trace support.
- **Affected services**: List with entity IDs.
- **Top actionable errors**: Up to 5, with occurrence counts.
- **Trace findings**: Error location, error message, and likely cause (from step 6).
- **Recommended next steps**: e.g. check a specific service, escalate, or roll back a deployment.
