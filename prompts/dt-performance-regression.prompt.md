---
agent: agent
description: Analyze whether a recent deployment caused a performance regression and recommend rollback or hotfix.
---

# Performance Regression Analysis

## Rules

- **ALWAYS confirm the service name with the user before querying.** Infer it from the current workspace if not provided.
- **NEVER query without a scoped timeframe and entity.** Broad queries hit scan limits and return no results.
- **STOP at Step 2 if no regression threshold is exceeded.** Do not proceed to trace investigation unnecessarily.

## Step 1 — Establish the investigation window

Ask the user: "When did the suspected regression start? (e.g. 'about 2 hours ago', 'today at 14:30', or a date range)"
Default to the **last 24 hours** if the user has no specific time in mind.

Then use the **Data Analysis Agent** to find the latest deployment event for the service within the investigation window, filtered to the confirmed service entity.

**If a deployment event is found:**
Use the deployment timestamp as the regression boundary. Split the window into:
- **Before:** `[deploymentTime - 35min, deploymentTime - 5min]`
- **After:** `[deploymentTime + 5min, deploymentTime + 35min]`

**If no deployment event is found:**
Do not stop. Use the midpoint of the investigation window as the boundary:
- **Before:** first half of the window
- **After:** second half of the window

State clearly which boundary was used and why.

## Step 2 — Compare metrics before and after

Use the **Data Analysis Agent** to query P95 response time, error rate, and throughput for each window, scoped to the confirmed service entity.

**A regression is confirmed when any threshold is exceeded:**

| Signal | Regression threshold |
|---|---|
| P95 response time | Increased by >20% **or** absolute value >2 s (>2,000,000,000 ns) |
| Error rate | Increased by >1 percentage point |
| Throughput | Dropped by >20% (without a corresponding drop in traffic) |

---

### If NO regression threshold is met — STOP HERE

Output the following summary and do not proceed to Step 3:

```
## No Regression Detected

- Service: <service-name>
- Investigation window: <before-window> vs <after-window>
- Regression boundary: <deployment event or midpoint>
- P95 response time: <before> → <after> (<delta>%) — within threshold
- Error rate: <before> → <after> — within threshold
- Throughput: <before> → <after> — within threshold

No action required. If you suspect a regression in a different time window, re-run this prompt with a specific timeframe.
```

---

## Step 3 — Identify regressed endpoints

Use the **Data Analysis Agent** to query span P95 durations grouped by endpoint for the after window, scoped to the confirmed service entity.

Flag endpoints exceeding the P95 response time threshold or a >20% increase vs. the before window. List the top 5 sorted by absolute P95 delta (worst first).

## Step 4 — Fetch distributed traces for slow requests

For the top 1–3 regressed endpoints, use the **Data Analysis Agent** to fetch slow spans within the after window, scoped to the confirmed service entity and endpoint.

Pick the trace with the highest duration. Build a timeline sorted by start time. Identify the **first span** whose duration is the dominant contributor — this is the bottleneck span. Record its operation name, service, duration, and any error attributes.

## Step 5 — Connect slow spans to workspace code changes

Using the bottleneck span's operation name and service, search the workspace:
- Search for the endpoint path or operation name in route definitions, controllers, and handler files.
- Look for recently modified files that match the slow code path (check git log or file timestamps).
- If a match is found, show the file path and relevant lines. State explicitly which code change is the likely contributor.
- If no match is found, state that the slow span could not be correlated to a local file.

## Step 6 — Check for an active Davis Problem

Use the **Root Cause Agent** to check for any active or recently closed Davis Problem affecting this service.
If found, include: problem ID, title, root cause summary, and affected entities.

## Step 7 — Recommend: rollback or hotfix

Based on all findings, give one clear recommendation:

**Rollback** when:
- Multiple endpoints regressed simultaneously
- Error rate spiked significantly (>5 pp)
- No specific code change in the workspace can be identified as the cause
- A Davis Problem is active with no known mitigation

**Hotfix** when:
- Regression is isolated to 1–2 endpoints
- A specific code change in the workspace correlates with the slow span
- The fix is low-risk (e.g. missing index, inefficient query, removed cache)

In either case, provide:
1. The specific recommendation (rollback or hotfix) with reasoning
2. Concrete optimization steps (e.g. which query to optimize, which cache to restore, or the rollback command)
3. How to verify the fix: which metric/endpoint to watch and the target value
