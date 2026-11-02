# Post-Migration Verification

Run these checks after the customer's migrated code has sent at least one event. Work through the sections in order — stop and fix any issue before proceeding to the next section.

## Pre-run checklist

Confirm both conditions before running any queries:

- [ ] Customer has executed the migrated monitor code at least once
- [ ] At least 60 seconds have elapsed since the first execution (Grail ingestion lag)

---

## DQL Queries

Open **DQL (Notebooks or Explorer)** in the Dynatrace UI and run each query in order.

### Query 1 — Confirm run events landed

Verify that `external_test_run` events are arriving with the expected `test.id`.

```dql
fetch events, from:now()-1h
| filter event.type == "external_test_run"
| fields timestamp, test.id, test.name, test.run.status, test.run.duration_ms, test.run.location
| sort timestamp desc
| limit 20
```

Expected: rows appear. Each row has a non-null `test.id` and a `test.run.status` of `passed` or `failed`.

If no rows appear after 5 minutes, see [Common Problems](#common-problems).

### Query 2 — Confirm step events landed and are correlated

Verify that `external_test_step` events exist and carry the `result.status.category` field added by OpenPipeline.

```dql
fetch events, from:now()-1h
| filter event.type == "external_test_step"
| fields timestamp, test.id, test.step.name, test.step.status, test.step.duration_ms, result.status.category
| sort timestamp desc
| limit 20
```

Expected: rows appear. `result.status.category` is `SUCCESS`, `SKIPPED`, or `FAIL` — never null.

If `result.status.category` is null, OpenPipeline processing may still be catching up — wait 60 seconds and re-run.

### Query 3 — Look up all events for a specific run

Use this when debugging a specific execution. Replace `YOUR_RUN_ID_HERE` with an actual `test.run.id` value from Query 1.

```dql
fetch events, from:now()-1h
| filter in(event.type, {"external_test_run", "external_test_step"})
| filter test.run.id == "YOUR_RUN_ID_HERE"
| fields timestamp, event.type, test.step.name, test.run.status, test.step.status
| sort timestamp asc
```

Expected: one `external_test_run` row followed by one row per step, all sharing the same `test.run.id`.

### Query 4 — Availability summary by test

Confirm the availability metric is accumulating correctly across runs.

```dql
fetch events, from:now()-24h
| filter event.type == "external_test_run"
| summarize
    total = count(),
    passed = countIf(test.run.availability == 1),
    by: { test.id, test.name }
| fieldsAdd availability_pct = (toDouble(passed) / toDouble(total)) * 100
| sort availability_pct asc
```

Expected: each migrated `test.id` appears. `availability_pct` matches what the customer expects given their test history.

### Query 5 — Top error codes for failing tests

Run this only when some runs are failing after migration.

```dql
fetch events, from:now()-7d
| filter event.type == "external_test_run" AND test.run.status == "failed"
| summarize failure_count = count(), by: { test.id, test.run.error_code }
| sort failure_count desc
| limit 20
```

Use the results to identify whether failures are pre-existing or introduced by the migration.

### Query 6 — Confirm no legacy events are still arriving

Verify the old integration is fully stopped.

```dql
fetch events, from:now()-1h
| filter event.provider == "dynatrace.synthetic"
| filter isNotNull(syntheticEngineName)
| fields timestamp, syntheticEngineName
| limit 10
```

Expected: zero rows. If rows appear, the legacy integration is still running alongside the new one — stop it before proceeding.

---

## Smartscape Node Check

After at least one successful run event lands, an `EXT_TEST` Smartscape node should be registered for each unique `test.id`. Verify using the test name from Query 1:

```dql
smartscapeNodes "EXT_TEST"
| filter contains(name, "YOUR_TEST_NAME")
| fields id, name
```

Expected: one node per unique `test.id` that has sent events. If no nodes appear, confirm that `test.id` is stable across executions — it is the node key and must not change between runs.

---

## UI Smoke Test

Complete this checklist in the Dynatrace UI:

1. Open the **Synthetic** app and confirm the migrated monitor appears as an external test entity.
2. Check that the monitor shows recent execution history — the last run timestamp should reflect the migration test run.
3. Open a run and confirm step-level breakdown is visible (applies only if steps were included in the migration).
4. Open **Davis AI** and confirm no spurious alerts were triggered by the migration.
5. If the monitor previously had an SLO, confirm the SLO is still tracking the `external.test.availability` metric.

---

## Common Problems

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| No events in Query 1 after 5 minutes | OpenPipeline `external.tests` ingest source not configured | Deploy the Monaco bundle; see `intake.md` |
| HTTP 401 from the new endpoint | Wrong token scope | Token needs `openpipeline.events.custom` scope, not `ExternalSyntheticIntegration` |
| HTTP 404 from the new endpoint | Wrong URL or path segment | Verify the URL uses the apps domain and that `external.tests` exists in OpenPipeline |
| Events land but no Smartscape node | `test.id` changed between runs | Keep `test.id` stable across executions — it is the node key |
| Step events missing `result.status.category` | OpenPipeline processing delay | Wait 60 seconds and re-run Query 2 |
| Legacy events still arriving (Query 6 returns results) | Old integration still running | Stop the old integration; do not run both in parallel |
