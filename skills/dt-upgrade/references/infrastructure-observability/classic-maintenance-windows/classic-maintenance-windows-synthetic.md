# Maintenance Windows Affecting Synthetic Monitors

**Gen3 replacement**: `builtin:maintenance-windows`

**Phase 2 required**: no (needed for Phase 3)

## What changes

Gen3 Maintenance Windows are compatible with Grail. Classic maintenance windows will be removed in Phase 3.

**A gen3 maintenance window does not suppress anything.** It enriches matching signals with maintenance metadata — notably `maintenance.is_under_maintenance = true` — and leaves enforcement to the consumer. Problems are still detected, still created, and still alerted on during the window. See [`classic-maintenance-windows.md`](classic-maintenance-windows.md) for the full behavioural picture; everything there applies here too.

> **⚠️ Synthetic execution is NOT paused during a gen3 window.** Classic `disableSyntheticMonitorExecution: true` stopped monitors in scope from running at all. The gen3 counterpart lives under `objectScopes.syntheticMonitors`, and **it is not functional yet** — its presence in an environment's schema does not mean it works, and there is no way to test whether it does. Treat it as non-functional until this documentation says otherwise.
>
> Never tell a customer that migrating the window will keep their monitors paused. Monitors will keep executing and generating real traffic against the system under maintenance — a functional regression, not merely a reporting one. Where that traffic matters, automate monitor enable/disable around the window, or accept the executions and exclude them at query time.

## Customer actions

- Recreate all maintenance windows using the Gen3 maintenance windows feature
- Migrate 3rd-party monitor integrations with [`ext-monitors-migration.md`](../../digital-experience/ext-monitors-migration/ext-monitors-migration.md) before recreating windows that cover them (Step 2)
- Decide, per monitor, whether to automate enable/disable around the window or accept executions during maintenance while `objectScopes.syntheticMonitors` is non-functional (Step 6)
- Add `maintenance.is_under_maintenance != true` to every workflow problem trigger and alert-routing rule that should stay quiet during maintenance (Step 10)
- Disable, not delete, the classic windows once no classic problem notification depends on them (Step 11)

## Prerequisites

- Maintenance windows defined in the classic format
- **Management zones migrated to segments first.** A window scoped by `managementZones` can only be recreated once [`management-zones.md`](../../platform/management-zones/management-zones.md) has migrated the zone to a segment. Use that segment's filter in the maintenance window — do not derive one from the zone rules here. If the customer does not want to migrate management zones first, reference a segment in the window and set `filter: "*"` instead (Step 2)
- **3rd-party (external) monitors migrated first.** A window scoped to `EXTERNAL_SYNTHETIC_TEST` or `EXTERNAL_SYNTHETIC_TEST_STEP` can only be recreated once [`ext-monitors-migration.md`](../../digital-experience/ext-monitors-migration/ext-monitors-migration.md) has moved the integration to the Grail events ingest API. Until then there is no Grail data for the window's filter to match. If the customer does not want to migrate the monitors first, migrate the window with `filter: 'matchesValue(dt.smartscape.ext_test, "*")'` instead (Step 2)

### Required token scopes

| Scope | Needed for |
|---|---|
| `settings:objects:read`, `settings:objects:write` | Reading classic windows and management zones, writing gen3 windows (steps 1, 8) |
| `settings:schemas:read` | Checking whether the environment's schema accepts `objectScopes` (step 2) |
| `storage:filter-segments:read` | Looking up the segments established by the management zone migration (step 1) |
| `automation:rules:read`, `automation:rules:write` | Automation scheduling rules for `WEEKLY` / `MONTHLY` windows (step 5) |
| Grail/DQL read | Smartscape ID lookups and coverage checks (steps 1, 4, 7, 9) |
| Api-Token with `Read synthetic monitors` and `Create and update synthetic monitors` | The Synthetic API v2 `curl` requests that list monitors by tag and update their primary tags (steps 1, 3) |

## Instructions

### Step 1: List classic maintenance windows and select the synthetic ones

List all classic maintenance windows:

```bash
dtctl get settings --schema builtin:alerting.maintenance-window -o json --plain
```

**Required token scopes:** `settings:objects:read`

Mark expired entries as you go — a `ONCE` window whose end time has passed, or a recurring window whose `recurrenceRange.scheduleEndDate` has passed. Establish the current date before making that comparison rather than assuming it. Expired windows get no replacement (Step 5).

A window belongs in this guide when its `filters` array contains an object whose `entityType` is one of: `SYNTHETIC_TEST`, `SYNTHETIC_TEST_STEP`, `HTTP_CHECK`, `HTTP_CHECK_STEP`, `SYNTHETIC_LOCATION`, `EXTERNAL_SYNTHETIC_TEST`, or `EXTERNAL_SYNTHETIC_TEST_STEP`. The shape of each is shown in [Classic filter shapes](#classic-filter-shapes).

A window with an **empty** `filters` array covers the whole environment, synthetic monitors included. Recreate it as described in the general guide (`filter: "true"`), but handle any `disableSyntheticMonitorExecution: true` on it as described here (Step 6).

Windows without an `entityType` but with `entityTags` or `managementZones` may also cover synthetic monitors. Cross-reference them against the monitors themselves:

- **`entityTags`** — list the monitors carrying each tag with the Synthetic API v2:

  ```bash
  curl -X 'GET' \
    'https://<tenant-id>.live.dynatrace.com/api/v2/synthetic/monitors?tag=<classic-tag-name>' \
    -H 'accept: application/json; charset=utf-8' \
    -H 'Authorization: Api-Token <your-api-token>'
  ```

  Replace `<classic-tag-name>` with the tag value from the classic window filter (e.g. `BM MW`), URL-encoded if it contains spaces. The response contains a `monitors` array; each entry includes the monitor `entityId`, `name`, `type`, and `tags`. Requires an Api-Token with `Read synthetic monitors`.

  Because classic tags use **ALL** semantics, a window listing several tags covers only the monitors returned for **every** tag — intersect the lists. A non-empty result means the window covers synthetic monitors and belongs in this guide. Keep the monitor list; Step 3 needs it.

- **`managementZones`** — classic values are **settings objectIds, not names**, and an entity must belong to *every* listed zone. Resolve the zone names first:

  ```bash
  dtctl get settings --schema builtin:management-zones -o json --plain
  ```

  Then find the segment the management-zone migration established for that zone:

  ```bash
  dtctl get segments
  ```

  **Required token scopes:** **Platform Token / OAuth** — scope: `storage:filter-segments:read`

  Each segment carries a `uid`, `name`, and `includes` (the DQL filter criteria). Match the resolved zone name against the segment `name`, and run its filter through the synthetic-execution probe in the general guide's [Validation](classic-maintenance-windows.md#validation) section. Rows returned mean the zone covers synthetic monitors. If no replacement segment or primary field exists yet, the window is blocked (Step 2).

### Step 2: Check blockers before building anything

Resolve these before drafting any gen3 definition, and report every window that is blocked:

- **Management zones.** Classic management zones are replaced by **segments** in Gen3, but **the mapping is not 1:1** — a zone's rules have to be reduced to a discriminator that is actually enriched on the data, and that work is its own migration. Do not derive a filter from the zone's rules here. **Migrate the management zone to a segment first, then use that segment in the maintenance window:** until [`management-zones.md`](../../platform/management-zones/management-zones.md) has created the segment that replaces the zone, a window scoped by `managementZones` cannot be recreated. Once it exists, build the gen3 `filter` from that segment's `includes` criteria (Step 4). If the customer does not want to migrate management zones first, reference a segment for the zone in the window and set `filter: "*"`, as described in the general guide's [Management zones without a prior zone migration](classic-maintenance-windows.md#management-zones-without-a-prior-zone-migration).
- **Classic problem notifications.** Routing still handled by classic `builtin:problem.notifications` cannot carry the maintenance condition from Step 10 and must be migrated to a Workflow first — see [Prerequisite migrations](classic-maintenance-windows.md#prerequisite-migrations). Until then the classic windows stay enabled (Step 11).
- **3rd-party monitors.** Windows scoped to `EXTERNAL_SYNTHETIC_TEST` or `EXTERNAL_SYNTHETIC_TEST_STEP` cover 3rd-party monitors, which report through the deprecated `POST /api/v1/synthetic/ext/tests` API. Those integrations must be migrated to the Grail events ingest API first, following [`ext-monitors-migration.md`](../../digital-experience/ext-monitors-migration/ext-monitors-migration.md). Until then there is no Grail data for its filter to match. If the customer does not want to migrate the 3rd-party monitors first, migrate the window anyway with `filter: 'matchesValue(dt.smartscape.ext_test, "*")'`. That filter matches every external monitor once it reports through the events ingest API. Tell the customer that the window covers all external monitors, not only the ones the classic window named, and that it matches nothing until the integration is migrated. Record it as follow-up work, and narrow it to the monitor's `EXT_TEST` ID once the monitor appears in Smartscape (Step 4).
- **`objectScopes` support.** Re-dump the live schema rather than trusting the property lists in this guide, and check whether `objectScopes` is accepted in this environment (needs `settings:schemas:read`). Step 6 depends on the answer:

  ```bash
  dtctl get settings-schemas builtin:maintenance-windows -o json
  ```

  In the returned schema, look for `syntheticMonitors` and `suppressProblems` under `objectScopes`.

- **Object budget.** The environment allows **100** `builtin:maintenance-windows` objects; classic allowed 2000. Count synthetic and infrastructure windows together, and plan to consolidate windows that share a schedule. See the general guide's [schema limits](classic-maintenance-windows.md#schema-limits).

### Step 3: Add primary GRAIL tags to tag-scoped monitors

Skip this step unless a window is scoped by `entityTags`. Classic entity tags have no direct equivalent in Gen3 maintenance windows — primary tags are new Gen3-only functionality and are not derived from classic tags. Apply primary tags to the monitors found in Step 1, so Step 4 can target them.

If the customer does not want to add primary tags first, or a monitor has no primary tags, skip the update below. Migrate the window with `filter: 'matchesValue(primary_tags.<key>, "*")'`, using the classic tag key, as described in the general guide's [Tags without primary tag coverage](classic-maintenance-windows.md#tags-without-primary-tag-coverage).

Retrieve each monitor by ID to inspect its full definition, including the `primaryGrailTags` field:

```bash
curl -X 'GET' \
  'https://<tenant-id>.live.dynatrace.com/api/v2/synthetic/monitors/<MONITOR_ID>' \
  -H 'accept: application/json; charset=utf-8' \
  -H 'Authorization: Api-Token <your-api-token>'
```

Replace `<tenant-id>` with your environment ID, `<MONITOR_ID>` with the synthetic monitor ID (e.g. `SYNTHETIC_TEST-XXXXXXXXXXXXXXXX`), and `<your-api-token>` with an API token that has the `Read synthetic monitors` permission. The subsequent PUT requires the `Create and update synthetic monitors` permission.

The `primaryGrailTags` field in the response lists the primary GRAIL tags currently assigned to the monitor:

```json
"primaryGrailTags": [
  {
    "key": "tagKey",
    "value": "tagValue"
  }
]
```

If `primaryGrailTags` is absent or empty, no GRAIL tags have been assigned yet. Note the existing values before updating, as the PUT request replaces the entire field.

Add or update the `primaryGrailTags` entry in the retrieved definition, and send the whole definition back via `PUT /api/v2/synthetic/monitors/<MONITOR_ID>`.

### Step 4: Translate the scope into the top-level `filter`

Gen3 maintenance windows replace the classic `filters` array (entity type, entity ID, entity tags, management zones) with a single `filter` string holding a DQL matcher expression. Target synthetic monitors through their Smartscape fields:

| Classic scope | Gen3 top-level `filter` | Notes |
|---|---|---|
| Empty `filters` | `true` | Whole environment |
| `SYNTHETIC_TEST` (browser monitor) | `isNotNull(dt.smartscape.browser_monitor)` for all, or `matchesValue(dt.smartscape.browser_monitor, "<SMARTSCAPE-ID>")` with `entityId` | Resolve the ID first (below) |
| `HTTP_CHECK` | `isNotNull(dt.smartscape.http_monitor)` for all, or `matchesValue(dt.smartscape.http_monitor, "<SMARTSCAPE-ID>")` with `entityId` | Without `entityId`, use the non-null check — an ID comparison would silently narrow the window to one monitor |
| `HTTP_CHECK_STEP` | `matchesValue(dt.smartscape.http_monitor_step, "<SMARTSCAPE-ID>")` with `entityId`, or `isNotNull(dt.smartscape.http_monitor_step)` for all | Keeps the classic step-level scope. See [Migrating step-level windows](#migrating-step-level-windows) |
| `SYNTHETIC_TEST_STEP` | `matchesValue(dt.smartscape.browser_monitor_step, "<SMARTSCAPE-ID>")` with `entityId`, or `isNotNull(dt.smartscape.browser_monitor_step)` for all | Same as `HTTP_CHECK_STEP` |
| `SYNTHETIC_LOCATION` | `isNotNull(dt.smartscape.synthetic_location)` for any, or `matchesValue(dt.smartscape.synthetic_location, "<SMARTSCAPE-ID>")` for one | Classic suppressed alerts for every monitor running from the location; gen3 only enriches |
| `EXTERNAL_SYNTHETIC_TEST` | `isNotNull(dt.smartscape.ext_test)` for all, or `matchesValue(dt.smartscape.ext_test, "<EXT_TEST-ID>")` with `entityId` | 3rd-party monitor — migrate the integration first with [`ext-monitors-migration.md`](../../digital-experience/ext-monitors-migration/ext-monitors-migration.md), then look up its `EXT_TEST` node **by name** (`smartscapeNodes "EXT_TEST" \| filter contains(name, "<monitor name>") \| fields id, name`). The node is new, keyed on the integration's `test.id`, so the classic ID does not resolve through `id_classic`. If the customer does not want to migrate the monitors first, use `matchesValue(dt.smartscape.ext_test, "*")` (Step 2) |
| `EXTERNAL_SYNTHETIC_TEST_STEP` | Parent external monitor: `matchesValue(dt.smartscape.ext_test, "<EXT_TEST-ID>")` | There is no Smartscape node for an external step. Step events carry the parent's `dt.smartscape.ext_test`, so the window covers the whole monitor. Flag the widening of coverage. Without a migrated integration, use the same `"*"` fallback |
| `MULTIPROTOCOL_MONITOR` | `isNotNull(dt.smartscape.network_availability_monitor)` | |
| `entityTags` | `matchesValue(primary_tags.<key>, "<value>")` | Only once Step 3 has put the primary tag on the monitors. Without primary tags, use `matchesValue(primary_tags.<key>, "*")` (Step 3). Several classic tags use ALL semantics — join them with `AND`, never as a set literal, which would match any of them and widen the window |
| `managementZones` | The `includes` criteria of the segment that the management-zone migration created for the zone | Blocked until that segment exists, unless the customer opts for the segment-reference fallback with `filter: "*"` (Step 2) |

> **In the top-level `filter`, entity references belong in the Smartscape namespace (`dt.smartscape.*`), primary tags are addressed as `primary_tags.<key>`, and security context as `dt.security_context`.** The deprecated `dt.entity.*` namespace must not be used either.
>
> There is **no** `security.context`, `monitor.id`, `monitor.name` or `pg.tag` field, in either filter. Because the validator checks syntax only, a filter such as `isNotNull(security.context)` saves cleanly, reports healthy, and matches nothing — windows like this have been observed on real tenants.

**Resolving classic IDs.** For synthetic types the prefix is renamed and the opaque suffix carried through — `SYNTHETIC_TEST-` becomes `BROWSER_MONITOR-` (e.g. `SYNTHETIC_TEST-7EEF2AA5318E2F39` → `BROWSER_MONITOR-7EEF2AA5318E2F39`) and `HTTP_CHECK-` becomes `HTTP_MONITOR-` (e.g. `HTTP_CHECK-91954855562522AD` → `HTTP_MONITOR-91954855562522AD`). Confirm the mapping with a `smartscapeNodes "*" | filter in(id_classic, {"<classic-id>"}) | fields id, id_classic, name, type` lookup rather than assuming it. Step IDs resolve the same way, to `BROWSER_MONITOR_STEP-` and `HTTP_MONITOR_STEP-` — see [Migrating step-level windows](#migrating-step-level-windows). See `entity-synthetic.md` for the full prefix mapping table.

#### Migrating step-level windows

Classic windows filtered by `HTTP_CHECK_STEP` or `SYNTHETIC_TEST_STEP` covered a single step, not the whole monitor. Use the step-level Smartscape fields to keep that scope:

| Classic `entityType` | Smartscape field | Smartscape ID prefix |
|---|---|---|
| `HTTP_CHECK_STEP` | `dt.smartscape.http_monitor_step` | `HTTP_MONITOR_STEP-` |
| `SYNTHETIC_TEST_STEP` | `dt.smartscape.browser_monitor_step` | `BROWSER_MONITOR_STEP-` |

1. Resolve the classic step ID to its Smartscape ID, and check the `type` column says `HTTP_MONITOR_STEP` or `BROWSER_MONITOR_STEP`:

   ```dql
   smartscapeNodes "*" | filter in(id_classic, {"HTTP_CHECK_STEP-95D7C2B36F5C03F0"}) | fields id, id_classic, name, type
   ```

   No row means the step no longer exists. Report it and do not guess a replacement.

2. Write the top-level `filter` with the step field and the resolved ID:

   ```dql-snippet
   matchesValue(dt.smartscape.http_monitor_step, "HTTP_MONITOR_STEP-95D7C2B36F5C03F0")
   ```

   For a classic filter with `entityType` only and no `entityId`, use `isNotNull(dt.smartscape.http_monitor_step)` or `isNotNull(dt.smartscape.browser_monitor_step)`. For several steps, use a set literal such as `matchesValue(dt.smartscape.browser_monitor_step, {"BROWSER_MONITOR_STEP-A", "BROWSER_MONITOR_STEP-B"})`, and stay under the 500-character limit.

3. Check that the step field is actually present on signals. [type-mappings.md](../../platform/entity-queries/type-mappings.md) lists both step mappings as `planned`, and the validator will not catch a field that is never populated:

   ```dql
   fetch dt.davis.events, from: now()-7d | filter isNotNull(dt.smartscape.http_monitor_step) | limit 10
   ```

   ```dql
   fetch events, from: now()-7d | filter isNotNull(dt.smartscape.browser_monitor_step) | limit 10
   ```

   If both probes return nothing, the step field does not match anything yet. Scope to the **parent** monitor instead: find it through the `belongs_to` relationship (see [`entity-synthetic.md`](../../platform/entity-queries/entity-synthetic.md)) and use `matchesValue(dt.smartscape.http_monitor, "<PARENT-ID>")` or `dt.smartscape.browser_monitor`. This **widens** coverage from one step to the whole monitor, so flag it to the customer.

4. If the classic window also has `disableSyntheticMonitorExecution: true`, use the **parent monitor's** `id` in `disableSyntheticMonitorFilter`. Monitors are paused as a whole, so a step cannot be paused on its own (Step 6).

The `filter` field has a **500-character maximum** — enumerating many monitor IDs overruns it, so condense, or scope by primary tag instead. Its validator checks **syntax only**: a filter naming a nonexistent field saves successfully, reports healthy, and matches nothing. Step 7 checks coverage before anything is written.

This table applies to the **top-level `filter`** only. `objectScopes.syntheticMonitors.disableSyntheticMonitorFilter` accepts a much narrower set of fields — Step 6 translates it separately.

### Step 5: Translate the schedule

**Recreate only windows that still have a future occurrence.** Expired windows marked in Step 1 do not need a gen3 replacement — and cannot get one, because the API rejects any definition whose schedule produces no future occurrence. Do not draft a definition for them, even as an illustration; report them as decommission candidates and move on.

**Preserve the recurrence, the start time, and the end time.** `ONCE` stays `once`, `DAILY` / `WEEKLY` / `MONTHLY` stay recurring on the same days, and each occurrence starts and ends at the classic wall-clock times. Where one of the three cannot be kept, flag it to the customer instead of changing it silently.

Set the start time and the duration of every migrated window like this:

- **Start time = the classic start time.** `once.date` is the classic `onceRecurrence.startTime`; `recurring.time` is the classic `timeWindow.startTime`. Copy it verbatim, in the classic timezone.
- **`duration` = classic end time − classic start time, in minutes.** `ONCE`: `onceRecurrence.endTime - onceRecurrence.startTime`, using the full classic datetimes. Recurring: `timeWindow.endTime - timeWindow.startTime`. Add 1440 **only** when that subtraction is negative (e.g. `23:30`–`00:30`: −1380 + 1440 = 60); a positive result is the duration as it stands. Never take it from `recurrenceRange`, a default, or the 10080 cap.
- **A recurring window whose end time is later than its start time never gets 24 hours added.** A recurring `09:00`–`10:00` window is `recurring.time: "09:00:00"` and `duration: 60` — not 1500, not 1440 + 60. The same holds for `10:00`–`11:00` (60) and `02:00`–`05:00` (180).
- **Calculate `duration` from the original classic times, before any date change.** Moving a past start date forward never changes the duration — do not measure from the new `earliestStart` or `once.date` to the classic end time.
- **Check it before writing:** the gen3 duration must equal the classic window's length on the clock. A 1-hour classic window gives 60, not 1 day 1 hour.

**Keep the classic start and end time exactly** — same wall-clock times, same timezone. Copy the classic `startTime` verbatim, derive `duration` from the classic `endTime - startTime`, and carry the timezone and `recurrenceRange` dates over unchanged. **A recurring window stays recurring**: use `type: time` with `recurring.time` set to `timeWindow.startTime`, and take `duration` from `timeWindow.endTime - timeWindow.startTime` — one occurrence, adding 1440 only when the subtraction is negative. The `recurrenceRange` dates become `earliestStart` / `until` and never feed the duration. Never clamp a duration to 10080; a recurring duration of 1440 or more means the wrong fields were used. Do not convert to UTC, round, or shift the start time. The one exception: if the classic start **date** is already in the past, replace only the date with the day after today, keep the start time, duration, and timezone, and tell the customer. See the general guide's [Schedule](classic-maintenance-windows.md#schedule) section for an example.

| Property | Notes |
|---|---|
| `schedule.duration` | Length in **minutes**, not an end time. `ONCE`: `onceRecurrence.endTime - startTime`. Recurring: `timeWindow.endTime - timeWindow.startTime` — one occurrence, not the `recurrenceRange` span. Capped at 7 days (10080) — longer `ONCE` windows must be split or re-expressed as recurring |
| `schedule.trigger.type` | `once` or `time` |
| `schedule.trigger.once.date` | Start datetime, when `type` is `once`. Must be in the future |
| `schedule.trigger.recurring.time` / `.rule` | Daily start time, plus a **scheduling-rule UUID** (not an inline RRULE string) selecting which days fire. `DAILY` needs no rule; `WEEKLY` and `MONTHLY` do |
| `schedule.trigger.recurring.earliestStart` / `.until` | Maps from the classic `recurrenceRange`. At least one firing date must fall in the future within this range |
| `schedule.timezone` | Carry over from the classic window |
| `autoDelete` | **Defaults to `true`** — the configuration is deleted 30 days after its last execution. Set `false` explicitly on every migrated window that should persist |

There is no `scheduleType` on the gen3 window — a classic `WEEKLY` or `MONTHLY` window cannot be expressed on the window itself. Create an Automation scheduling rule first (Automations → Scheduling Rules, or the Automation API), then reference its UUID in `recurring.rule`. Windows sharing a day pattern share one rule. See the general guide's [Schedule](classic-maintenance-windows.md#schedule) mapping for the full conversion, including the day-of-month 29–31 edge case. `dtctl` cannot read or create scheduling rules today.

### Step 6: Decide on monitor execution

Skip to Step 7 unless the classic window has `disableSyntheticMonitorExecution: true`. Per the warning in [What changes](#what-changes), the gen3 counterpart is not functional: setting it pauses nothing today, and there is no way to verify that it will. **Tell the customer the monitors will keep running, and agree on a compensating measure** — automate monitor enable/disable around the window, or accept the executions and exclude them at query time.

You may still set the gen3 field as forward-preparation. Omit it entirely if Step 2 showed the environment's schema does not accept `objectScopes`. Classic `disableSyntheticMonitorExecution` does **not** carry over verbatim — there is no such field in gen3:

| Classic | Gen3 | Notes |
|---|---|---|
| `generalProperties.disableSyntheticMonitorExecution: true` | `objectScopes.syntheticMonitors.disableSyntheticMonitors: true` | Boolean. The classic flag's counterpart |
| — | `objectScopes.syntheticMonitors.disableSyntheticMonitorFilter` | DQL string, **optional**, only available when `disableSyntheticMonitors` is `true`. Max 500 characters. Same syntax-only `filter-validator` as the top-level `filter` — a nonexistent field is accepted and matches nothing. **Restricted field set** — see below |

```yaml
    objectScopes:
      syntheticMonitors:
        disableSyntheticMonitors: true
        # Restricted field set — bare `id`, NOT dt.smartscape.http_monitor
        disableSyntheticMonitorFilter: 'matchesValue(id, "HTTP_MONITOR-91954855562522AD")'
```

The schema does not document which monitors are paused when `disableSyntheticMonitorFilter` is omitted, and the capability cannot be tested yet. Always set it explicitly to the classic scope instead of relying on the default.

The scope is expressed **twice**: the top-level `filter` from Step 4 drives enrichment, `disableSyntheticMonitorFilter` selects which monitors to pause. In classic, one scope drove both effects.

> **⚠️ The two filters accept different fields — do not copy one into the other.** The top-level `filter` takes essentially any valid DQL matcher over Grail fields, including `dt.smartscape.*`. `disableSyntheticMonitorFilter` accepts **only**:
>
> | Field | Notes |
> |---|---|
> | `id` | The monitor's Smartscape ID — bare `id`, **not** `dt.smartscape.http_monitor` / `browser_monitor` |
> | `name` | The monitor's name |
> | `primary_tags.<key>` | Primary tags on the monitor |
> | `dt.security_context` | Security context |
>
> Anything outside that set is rejected — but `id` covers most cases, so translate as follows:
>
> | Classic scope | Top-level `filter` | `disableSyntheticMonitorFilter` |
> |---|---|---|
> | `entityId` — one monitor | `matchesValue(dt.smartscape.http_monitor, "<SMARTSCAPE-ID>")` | `matchesValue(id, "<SMARTSCAPE-ID>")` |
> | `entityType` only — all of one type | `isNotNull(dt.smartscape.http_monitor)` | `matchesValue(id, "HTTP_MONITOR-*")` — the Smartscape ID prefix encodes the type, and `matchesValue` supports wildcards. Use `BROWSER_MONITOR-*` for `SYNTHETIC_TEST`, and so on |
> | Every synthetic monitor | `isNotNull(dt.smartscape.http_monitor)` etc. | `isNotNull(id)` |
> | Tag-scoped | `matchesValue(primary_tags.<key>, "<value>")` | same expression — `primary_tags.*` is allowed in both |
> | Step-level | `matchesValue(dt.smartscape.http_monitor_step, "<STEP-ID>")` or `dt.smartscape.browser_monitor_step` | parent monitor's `id` — a step cannot be paused on its own |
> | `SYNTHETIC_LOCATION` | `matchesValue(dt.smartscape.synthetic_location, "<ID>")` | **no location field** — resolve which monitors run from that location, then match their `id`s (or the type-prefix wildcard if that is close enough). Tell the customer the pause list is a snapshot and will not follow later location changes |
>
> The type-prefix wildcard is inferred from the documented ID prefixes plus wildcard support rather than verified against a live tenant — confirm it before relying on it. If it does not hold, fall back to `isNotNull(id)` (pauses **all** synthetic monitors, broader than the classic scope — get customer agreement) or enumerate ids within the 500-character cap.

### Step 7: Assemble the definition and confirm it with the customer

The gen3 schema is flat — do not adapt a classic payload. There is **no** `generalProperties` object, **no** `filters` array, **no** `maintenanceType`, and **no** `suppression` field. Build the object from scratch, combining the `filter` from Step 4, the `schedule` from Step 5, and any `objectScopes` from Step 6:

```yaml
- schemaId: builtin:maintenance-windows
  scope: environment
  value:
    name: MW NAME
    description: Optional
    enabled: true
    autoDelete: false
    filter: 'matchesValue(dt.smartscape.http_monitor, "HTTP_MONITOR-91954855562522AD")'
    schedule:
      trigger:
        type: once
        once:
          date: "2026-08-12T16:00:00"
      duration: 60
      timezone: Europe/Warsaw
```

`maintenanceType` has no gen3 equivalent and needs none — it was a display label, not behaviour. `suppression` has no gen3 field at all: its intent moves to the workflow problem trigger in Step 10.

Run the window's `filter` through the coverage probes in the general guide's [Validation](classic-maintenance-windows.md#validation) section — the synthetic-execution probe there selects every monitor type. Empty results across the probes mean the filter matches nothing; treat that as a failed migration for the window, because nothing will flag it after the write.

Present the proposed window to the customer and get confirmation before creating anything.

### Step 8: Create the window

#### Via dtctl

Write the definition to a YAML file and apply it:

```bash
dtctl apply -f maintenance-window.yaml
```

**Required token scopes:** `settings:objects:write`

> `dtctl apply --dry-run` is a **client-side preview only** — it reports `{"action":"created"}` without contacting the API, even for a schema that does not exist. It confirms your YAML parses and nothing more. There is no server-side validation available before the real write.

If the apply is rejected because the start is in the past, move the start date (`once.date`, or `earliestStart` for a recurring window) to the day after today, keep the classic start time, `duration` and timezone unchanged, and apply again. Tell the customer the start date was moved.

Confirm what was actually stored, including the `filter`:

```bash
dtctl get settings --schema builtin:maintenance-windows -o json --plain
```

#### Via web UI

1. Go to **Settings > General > Environment management > Maintenance windows**.
2. Select **New maintenance window**.
3. Enter the basic details: **Name** and **Description**. Select **Next**.
4. Configure the schedule:
   - **One time**: enter a **Start date and time**, **Duration**, and **Timezone**. Select or clear **Automatic deletion** as needed.
   - **Recurring**: enter a **Start time**, **Duration**, and **Recurrence rule**. To add or modify rules, select **Manage rules**. Select or clear **Automatic deletion** as needed.
5. Select **Next**.
6. Enter the **Scope** filter criteria in the **Maintenance Scope** field — start entering text to get suggestions. Select **Preview** to preview the data. Under **Preview results**, review the list of event types you can enrich with metadata.
7. Select **Save** and verify the window appears in the **Maintenance windows** table as **Active**.

### Step 9: Verify the window once it has elapsed

Confirm the window took effect by querying maintenance window events from Grail:

```dql
fetch events
| filter event.kind == "MAINTENANCE_WINDOW"
| dedup { maintenance_window.instance_id }, sort: { timestamp desc }
| fields maintenance_window.title, maintenance_window.filter, start_time, end_time
| sort start_time desc
```

Alternatively, check the window in the Dynatrace UI:

```
https://<tenant-id>.live.dynatrace.com/ui/apps/dynatrace.settings/settings/maintenance-windows
```

Then confirm that events raised for the monitors in scope during the window were flagged:

```dql-template
fetch dt.davis.events, from: "<window-start>", to: "<window-end>"
| filter <top-level filter of the window>
| summarize count(), by: { maintenance.is_under_maintenance }
```

Events in scope should carry `maintenance.is_under_maintenance == true`. If they carry `false` or no value, the window did not cover them.

> **Do not verify coverage with synthetic metrics.** `maintenance.is_under_maintenance` is a field on signals such as `dt.davis.events`, not a dimension on `dt.synthetic.browser.availability` or `dt.synthetic.http.availability`. Grouping a `timeseries` by it — or by any nonexistent dimension — does not error: it renders an empty column that looks identical to a real one, so the query appears healthy while telling you nothing. `dt.maintenance_window_ids` is not a metric dimension either, and is only rarely present on pre-upgrade signals; do not use it to tell classic and gen3 coverage apart.
>
> To see which dimensions a metric actually carries, list its fields with `fieldsSnapshot` — `dtctl describe` has no `metric` resource. Each row's `field` is one dimension; `maintenance.is_under_maintenance` should not appear:
>
> ```bash
> dtctl query 'fieldsSnapshot metrics, by:{metric.key} | filter metric.key == "dt.synthetic.browser.availability"'
> ```
>
> See the `dt-dql-essentials` skill's discovery reference for related metric-metadata queries.

### Step 10: Silence notifications

**The migration is not complete after Step 9.** The recreated window only enriches signals — problems on the monitors in scope are still created and still routed. To keep a classic window's silence, add this condition to every workflow problem trigger and alert-routing rule that should stay quiet during maintenance:

```dql-snippet
maintenance.is_under_maintenance != true
```

Skipping this leaves the customer receiving alerts during windows that were previously silent. Routing still on classic `builtin:problem.notifications` must be migrated to a Workflow first (Step 2).

### Step 11: Retire the classic windows

Disable the classic entries by setting `enabled: false` — do not delete them, so rollback stays possible. In the UI they live under **Settings Classic > Maintenance windows > Monitoring, alerting and availability**. While any classic problem notification covered by these windows is still active, leave the classic entries enabled and report the remaining notifications as the blocker. Steps 10–11 of [`classic-maintenance-windows.md`](classic-maintenance-windows.md#instructions) cover both actions in full.

Before closing out, tell the customer explicitly that problems are still created during maintenance and that synthetic monitors keep executing, because `objectScopes.syntheticMonitors` is not functional yet.

## Classic filter shapes

Use these to recognise each classic scope in the Step 1 output. Step 4 gives the gen3 translation for each.

**All synthetic tests** (`SYNTHETIC_TEST`, no `entityId` — every browser monitor):

```json
"filters": [
  {
    "entityType": "SYNTHETIC_TEST",
    "entityTags": [],
    "managementZones": []
  }
]
```

**Specific monitor by ID** (`SYNTHETIC_TEST` here; `HTTP_CHECK`, `HTTP_CHECK_STEP` and the other types take the same shape with their own prefix, e.g. `HTTP_CHECK-91954855562522AD`, `HTTP_CHECK_STEP-95D7C2B36F5C03F0`):

```json
"filters": [
  {
    "entityType": "SYNTHETIC_TEST",
    "entityId": "SYNTHETIC_TEST-7EEF2AA5318E2F39",
    "entityTags": [],
    "managementZones": []
  }
]
```

**All monitors of another synthetic type** — `HTTP_CHECK`, `HTTP_CHECK_STEP`, `SYNTHETIC_TEST_STEP`, `SYNTHETIC_LOCATION`, `EXTERNAL_SYNTHETIC_TEST`, `EXTERNAL_SYNTHETIC_TEST_STEP`:

```json
"filters": [
  {
    "entityType": "HTTP_CHECK",
    "entityTags": [],
    "managementZones": []
  }
]
```

**Scoped by entity tag** (no `entityType` — every entity carrying all listed tags):

```json
"filters": [
  {
    "entityTags": [
      "BM MW"
    ],
    "managementZones": []
  }
]
```

**Scoped by management zone** (every entity in all listed zones):

```json
"filters": [
  {
    "entityTags": [],
    "managementZones": [
      "<management-zone-objectId>"
    ]
  }
]
```

## References

- [`classic-maintenance-windows.md`](classic-maintenance-windows.md) — Maintenance windows migration overview; parent reference for this guide
- [`ext-monitors-migration.md`](../../digital-experience/ext-monitors-migration/ext-monitors-migration.md) — 3rd-party monitor migration from the v1 `ext/tests` API to Grail events ingest; prerequisite for windows scoped to `EXTERNAL_SYNTHETIC_TEST` / `EXTERNAL_SYNTHETIC_TEST_STEP`
- [`entity-synthetic.md`](../../platform/entity-queries/entity-synthetic.md) — Synthetic entity ID formats and classic → Gen3 ID mappings; use when resolving classic synthetic IDs to the Smartscape IDs used in Gen3 `dt.smartscape.*` filters