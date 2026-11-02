# SRG with Classic SLO Reference

**Gen3 replacement**: SRG with DQL objectives

**Phase 2 required**: no

## What changes

Site Reliability Guardians (SRGs) have two objective types that break in Gen3:

1. **`objectiveType: REFERENCE_SLO`** — holds a reference to a classic SLO by ID. Classic SLOs are deprecated. The SLI query must be extracted from the referenced SLO and embedded inline as a DQL objective. No dedicated SLO-to-DQL skill exists in this repo — the procedure is inline below.
2. **`objectiveType: DQL` with classic-entity patterns** — DQL queries using `dt.entity.*`, `classicEntitySelector`, or `entityName()` constructs. Load the **dt-migration** skill to migrate these; the logic is not reproduced here.

## Schema context

SRG guardians live in settings schema `app:dynatrace.site.reliability.guardian:guardians`.

**Before — REFERENCE_SLO objective:**

```json
{
  "schemaId": "app:dynatrace.site.reliability.guardian:guardians",
  "value": {
    "name": "Checkout Guardian",
    "objectives": [
      {
        "name": "Availability",
        "objectiveType": "REFERENCE_SLO",
        "sloRef": "<classic-slo-id>",
        "target": 99.9,
        "warning": 99.5
      }
    ]
  }
}
```

**After — DQL objective:**

```json
{
  "name": "Availability",
  "objectiveType": "DQL",
  "dqlQuery": "<SLI query extracted from classic SLO>",
  "target": 99.9,
  "warning": 99.5
}
```

The `target` and `warning` values carry over unchanged. Only the objective type and query change.

> **Note:** Verify exact field names on a real tenant with `dtctl get settings --schema app:dynatrace.site.reliability.guardian:guardians -o json`. The SLO reference field may be named `sloRef`, `sloId`, or similar — inspect a live REFERENCE_SLO objective before editing.

## Detection

Export all guardians and identify affected objectives in one pass:

```bash
dtctl get settings --schema app:dynatrace.site.reliability.guardian:guardians -o json > guardians-backup.json
```

In `guardians-backup.json`, identify all items where `value.objectives` contains at least one entry matching either condition:
- `objectiveType == "REFERENCE_SLO"`, or
- `objectiveType == "DQL"` and `dqlQuery` contains `dt.entity.`, `classicEntitySelector`, or `entityName`

If no such items exist, no migration is needed for this tenant.

## Migration loop

> **Read this entire file before executing any step.** The
> [Mandatory DQL rewrite rules](#mandatory-dql-rewrite-rules) section contains
> required rewrite patterns for `toSmartscapeId()` ID wrapping, process group subqueries,
> Davis Problems entity filters, and metric aggregation defaults. Applying any step
> without reading those rules first will produce incorrect migrated queries.

For each guardian returned by detection, repeat these steps.

**Step 1: Extract the guardian as a working file**

From `guardians-backup.json`, locate the item where `objectId == "<guardian-id>"` and save it as `guardian-<name>.json`.

**Step 2: Migrate each REFERENCE_SLO objective**

No standalone SLO-to-DQL skill exists in this repository. Use the following inline procedure.

Migrate the objective inline — do not re-create the SLO in the SLO app. Fetch the referenced classic SLO. Try the Settings API first:

```bash
dtctl get settings --schema builtin:slo.v2 -o json > slo-list.json
```

Find the item in `slo-list.json` where `objectId == "<slo-id>"`. The SLI query is in `value.metricExpression` (or a similarly named field — inspect the structure if the field name differs).

If the SLO is not in Settings 2.0 (older tenants), fetch it via the SLO API v2:

```
GET https://<tenant>/api/v2/slo/<slo-id>
Authorization: Api-Token <token>
```

Extract `metricExpression` (the SLI query) and `filter` from the response.

The `metricExpression` value is the SLI query. Use it as `dqlQuery` in the replacement DQL objective. Edit the working guardian file: replace the REFERENCE_SLO objective block with a DQL objective, preserving `name`, `target`, and `warning`.

**Step 3: Migrate each DQL objective with classic-entity patterns**

Load the **dt-migration** skill. It covers all three migration scenarios — mass data filtering, entity subquery filtering, pure entity list — with full field-discovery and equivalence verification. After obtaining the migrated DQL, update `dqlQuery` in the working guardian file.

**Step 4: Apply the resource file**

```bash
dtctl apply -f guardian-<name>.json
```

Keep the working file as the authoritative post-migration record for this guardian.

**Step 5: Verify**

After processing all affected guardians:

```bash
dtctl get settings --schema app:dynatrace.site.reliability.guardian:guardians -o json
```

Confirm no items in the output have objectives with `objectiveType == "REFERENCE_SLO"`. Also confirm no DQL objectives contain `dt.entity.` or `classicEntitySelector` in `dqlQuery`.

## Mandatory DQL rewrite rules

### Gain knowledge

Files in [dt-migration/references](../../../../dt-migration/references/) are a **must** read to gain insights into how to rewrite DQL statements.

### Wrap Smartscape IDs in a converter function

If DQLs have hardcoded IDs and the new Smartscape IDs are available, their usage has to be encapsulated with `toSmartscapeId("$ID")`, e.g.:

Some entity types map 1:1 — the classic ID is the same in Smartscape and only needs wrapping:

`"HOST-EDE23067108ADDF3"` → `toSmartscapeId("HOST-EDE23067108ADDF3")`

Other entity types change both type prefix and ID during the Gen2→Gen3 migration (e.g., `CLOUD_APPLICATION` becomes `K8S_DEPLOYMENT`, or `K8S_JOB`, or others starting with `K8S_`). In those cases the Smartscape ID must be looked up first:

`"CLOUD_APPLICATION-D2C2ED2773434993"` → `toSmartscapeId("K8S_DEPLOYMENT-709E1682C522EB11")`

To find the new Smartscape ID when the classic ID is known, use `id_classic` with the variadic `in()` form — this resolves one or more IDs in a single `dtctl q` call:

```dql
smartscapeNodes "*" | filter in(id_classic, {"CLOUD_APPLICATION-aaa", "CLOUD_APPLICATION-bbb"}) | fields id, id_classic, name, type
```

> Do **not** use `==` for multiple IDs. Use the `in(id_classic, {"..."})` form shown above. See [`entity-cloud-application.md`](../../../../dt-migration/references/entity-cloud-application.md) for the full lookup procedure.

If only a name is known (classic ID unavailable), fall back to a name filter:

```dql
smartscapeNodes "*" | filter name == "<entity-name>" | fields id, name, type
```

Use the returned `id` value as the argument to `toSmartscapeId()`.

### Metric aggregation defaults

Every metric aggregation function in a `timeseries` query must receive a `default: 0` argument when migrating for SRG objectives or any query where a metric gap must not produce `null`.

#### Rule

Add `default: 0` as the last named argument to `avg`, `sum`, `min`, `max`, `percentile`, and any other aggregation inside `timeseries`.

#### Before / after

```
avg(dt.host.cpu.load)                                   → avg(dt.host.cpu.load, default: 0)
sum(dt.kubernetes.container.memory_working_set)         → sum(dt.kubernetes.container.memory_working_set, default: 0)
percentile(dt.service.request.response_time, 95)        → percentile(dt.service.request.response_time, 95, default: 0)
```

#### Why this matters

Without `default: 0`, a gap in the metric time series returns `null`. SRG objectives evaluate the summarized result; a `null` produces no pass/fail signal and the objective silently fails. This applies even when the entity filter is correct.

### Process group

Process groups do not have an equivalent in Smartscape, but when a classic objective uses them in a `timeseries` query with an inner service-based filter there may be a migration path via `dt.smartscape.process`:
#### Before
```
timeseries memory_usage = avg(dt.process.memory.usage),  by:{dt.entity.process_group},
    filter:{
      dt.entity.process_group in [
        fetch dt.entity.process_group
        | expand runs[dt.entity.service], alias: services
        | filter services in [
            fetch dt.entity.service
            | filter in(id, {"SERVICE-C55BE95B0B7219CD"})
            | fields id
          ]
        | fields id
      ]
    }
```
#### After
```
timeseries memory_usage = avg(dt.process.memory.usage, default: 0), by:{dt.smartscape.process},
    filter:{
      dt.smartscape.process in [
        smartscapeNodes SERVICE
          | filter in(id, { toSmartscapeId("SERVICE-C55BE95B0B7219CD") })
          | traverse {runs_on}, {PROCESS}, direction: "forward", fieldsKeep: {id, name, type}
          | fields id
      ]
    }
```

Substitute the sample ID `"SERVICE-C55BE95B0B7219CD"` with the correct value or values.

### Davis Problems entity filter

Classic Davis event queries filter by a direct entity ID match. In Smartscape, entity affiliation is stored in `smartscape.affected_entity.ids` as a multi-value field, requiring an edge join and deduplication:

```
# before
fetch events
| filter event.kind == "DAVIS_PROBLEM"
| filter in(dt.entity.host, {"HOST-ID"})
| summarize count()

# after
fetch events
| filter event.kind == "DAVIS_PROBLEM" AND isNotNull(smartscape.affected_entity.ids)
| expand ids = smartscape.affected_entity.ids
| filter ids in [
    smartscapeEdges "*"
    | filter in(target_id, { toSmartscapeId("HOST-ID") })
    | fields source_id
  ]
| summarize c = count(), by: {event.id}
| summarize number_davis_events = sum(c)
```

The `by: {event.id}` deduplication step is mandatory: one Davis problem can affect multiple entities, so `expand` produces multiple rows per problem — without dedup the count is inflated and any downstream threshold check breaks. The `isNotNull(smartscape.affected_entity.ids)` guard drops events not yet indexed in Smartscape.

## Rollback

All per-guardian working files are slices of `guardians-backup.json`. To restore the full pre-migration state:

```bash
dtctl apply -f guardians-backup.json
```

Keep `guardians-backup.json` and all `guardian-<name>.json` files until the migration is confirmed stable in production.

## Tracking queries

### Concern 1: Guardians with REFERENCE_SLO objectives

```bash
dtctl get settings --schema app:dynatrace.site.reliability.guardian:guardians -o json
```

From the output, collect all items where `value.objectives` contains at least one entry with `objectiveType == "REFERENCE_SLO"`. For each match, record `objectId`, `value.name`, and the matching objective's `name` and `sloRef`.

### Concern 2: Guardians with classic-entity DQL in objectives

```bash
dtctl get settings --schema app:dynatrace.site.reliability.guardian:guardians -o json
```

From the output, collect all items where `value.objectives` contains at least one entry with `objectiveType == "DQL"` and `dqlQuery` containing `dt.entity.` or `classicEntitySelector`. For each match, record `objectId`, `value.name`, and the matching objective's `name` and `dqlQuery`.

### Consumer category (SRG app usage for upgrade-readiness dashboard)

```dql
timeseries usage_series = sum(dt.sfm.client.app.sessions_counter),
  by:{app.id},
  from:-30d
| filter app.id == "dynatrace.site.reliability.guardian"
| fields app.id, usage = arraySum(usage_series)
| sort usage desc
```

> If `dt.sfm.client.app.sessions_counter` does not exist, discover the right metric with:
> `fetch metric.series | filter startsWith(metric.key, "dt.sfm") AND matchesValue(metric.key, "*app*") | summarize by:{metric.key}`

## Customer actions

- Run detection to identify affected guardians (REFERENCE_SLO or classic-entity DQL).
- For each affected guardian: extract as a working file, migrate REFERENCE_SLO objectives inline and classic-entity DQL objectives via dt-migration, apply with `dtctl apply`.
- Classic SLOs will stop working in Phase 3 — all REFERENCE_SLO objectives will break.

## Documentation

- [Site Reliability Guardian](https://docs.dynatrace.com/docs/platform-modules/automations/site-reliability-guardian)
- [SRG objectives reference](https://docs.dynatrace.com/docs/platform-modules/automations/site-reliability-guardian/reference/objectives)
- [Classic SLO upgrade guide](https://docs.dynatrace.com/docs/shortlink/upgrade-guide-slos)

