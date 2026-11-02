# Classic Maintenance Windows

**Gen3 replacement**: `builtin:maintenance-windows`

**Phase 2 required**: no (needed for Phase 3)

## What changes

Classic maintenance windows (`builtin:alerting.maintenance-window`) use structured entity-based filters and are not compatible with Grail. Gen3 maintenance windows (`builtin:maintenance-windows`) replace them with DQL-based filters and a redesigned schedule model. There is no automatic migration — each window must be recreated manually.

### The behavioural change that drives everything else

**A gen3 maintenance window does not suppress anything.** This is the single most important difference and it changes what "migrating a window" means.

Classic windows could stop problem detection or stop alerting. Gen3 windows do neither. During a gen3 window, Dynatrace still creates alerts and still groups them into problems. What the window does is:

1. **Enrich** telemetry, problems, and events with maintenance metadata — notably `maintenance.is_under_maintenance = true`

The gen3 top-level schema has no suppression field; its property set is `name`, `description`, `enabled`, `filter`, `autoDelete`, `schedule`, and `objectScopes`.

Two enforcement capabilities (`objectScopes.suppressProblems` and `objectScopes.syntheticMonitors`) exist in the schema in some environments, but **neither is functional yet** — see [The `objectScopes` capabilities are not functional yet](#the-objectscopes-capabilities-are-not-functional-yet). Do not plan a migration around either one.

Consequence: **recreating the window is only half the migration.** To stop notifications firing during maintenance, the customer must also add a maintenance filter to every workflow problem trigger and alert-routing rule that should stay quiet:

```
maintenance.is_under_maintenance != true
```

A migration that recreates windows but skips this step will leave the customer receiving notifications they previously did not get. Always call this out.

> **Scope**: This guide covers maintenance windows filtered to general infrastructure entities (hosts, process groups, services, etc.). For windows scoped to synthetic entity types (`SYNTHETIC_TEST`, `SYNTHETIC_TEST_STEP`, `HTTP_CHECK`, `HTTP_CHECK_STEP`, `SYNTHETIC_LOCATION`, `EXTERNAL_SYNTHETIC_TEST`, `EXTERNAL_SYNTHETIC_TEST_STEP`), follow [`classic-maintenance-windows-synthetic.md`](classic-maintenance-windows-synthetic.md) instead.

### Which windows are migratable

Only future-relevant windows need migration:
- `ONCE` windows whose end time is in the future
- Recurring windows (`DAILY`, `WEEKLY`, `MONTHLY`) whose recurrence range end date is in the future or unset

Expired past windows can be ignored — and in fact **cannot** be migrated: the gen3 API rejects any definition whose schedule produces no future occurrence. A `once` window needs a future `once.date`; a recurring window needs at least one future firing date within its `earliestStart` / `until` range.

**Do not draft a gen3 definition for an expired window.** Report it as a decommission candidate and stop — producing a YAML or JSON definition anyway, even labeled as illustrative, is not migration work.

## Prerequisites

### Permissions

| Scope | Needed for |
|---|---|
| `settings:objects:read`, `settings:objects:write` | Reading classic windows and writing gen3 ones (steps 1, 4, 8, 11) |
| `settings:schemas:read` | The capability check below |
| `storage:filter-segments:read` | Looking up the segments established by the management zone migration (step 4) |
| `automation:rules:read`, `automation:rules:write` | Automation scheduling rules for `WEEKLY` / `MONTHLY` windows (step 5) |
| Grail/DQL read | The coverage probes in [Validation](#validation) |

### The `objectScopes` capabilities are not functional yet

> **⚠️ Schema presence is not a functionality signal.** Two enforcement capabilities live under `objectScopes` — `suppressProblems` and `syntheticMonitors`. Either may appear in a given environment's schema, and setting it will be accepted. **Neither is functional at the time of writing, and there is no way to test whether it works.** Presence in the schema tells you the field exists, nothing more.
>
> Treat both as non-functional until **this document explicitly says otherwise**. Do not infer availability from a schema dump or a successful write.

Check which fields the environment accepts, so you know what you are permitted to set:

```bash
dtctl get settings-schemas builtin:maintenance-windows -o json
```

In the returned schema, look for `syntheticMonitors` and `suppressProblems` under `objectScopes`.

| Capability | Present in schema | Absent from schema |
|---|---|---|
| `objectScopes.suppressProblems` | Set it if you want the definition ready for when it works — but it suppresses nothing today | Cannot be set at all |
| `objectScopes.syntheticMonitors` | Set it if you want the definition ready for when it works — but monitors keep executing today | Cannot be set at all |

**In both cases the practical outcome is identical**: the behaviour classic enforced does not happen, and the compensating measure is required now.

| Classic behaviour | Compensating measure required now |
|---|---|
| Problem/alert suppression | `maintenance.is_under_maintenance != true` on every workflow problem trigger that should stay quiet (see [Suppression](#suppression)) |
| Synthetic execution pause | Automate monitor enable/disable around the window, or accept the executions and exclude them at query time |

Populating these fields is therefore **forward-preparation, not a solution**. Whichever choice is made, the customer must be told explicitly that during maintenance windows problems will still be created and alerted on, and synthetic monitors will still execute against systems under maintenance — the latter generating real traffic, which is a functional regression rather than only a reporting one.

### Prerequisite migrations

Four other migrations gate this one. Each can block windows regardless of how straightforward the schedule conversion looks, so check them during triage (step 3) rather than discovering them window by window.

| Migration | What it blocks here | Reference |
|---|---|---|
| Management zones → segments | Windows filtered by `managementZones`. The zone name is not usable in a gen3 filter; you need the segment or primary field that migration established. | [`management-zones.md`](../../platform/management-zones/management-zones.md) |
| Classic tags → primary tags | Windows filtered by `entityTags`. Classic tags are not primary tags, and the ones still visible on pre-upgrade data disappear at upgrade — see [Filters](#filters). | [`autotagging.md`](../../platform/autotagging/autotagging.md) |
| Problem notifications → workflows | Disabling the classic windows at all — see below. | [`alerting-and-problem-notifications.md`](../../platform/alerting-and-problem-notifications/alerting-and-problem-notifications.md) |
| 3rd-party (external) monitors → Grail events ingest | Windows scoped to `EXTERNAL_SYNTHETIC_TEST` / `EXTERNAL_SYNTHETIC_TEST_STEP`. Until the integration has moved off the v1 `ext/tests` API there is no Grail data for the filter to match. If the customer does not want to migrate the monitors first, see the `matchesValue(dt.smartscape.ext_test, "*")` fallback in [`classic-maintenance-windows-synthetic.md`](classic-maintenance-windows-synthetic.md#step-2-check-blockers-before-building-anything). | [`ext-monitors-migration.md`](../../digital-experience/ext-monitors-migration/ext-monitors-migration.md) |

> **Migrate management zones to segments first, then use the segments in maintenance windows.** A window filtered by `managementZones` cannot be recreated until [`management-zones.md`](../../platform/management-zones/management-zones.md) has turned each zone into a segment; the gen3 window then filters on that segment's criteria. If the customer does not want to migrate management zones first, see [Management zones without a prior zone migration](#management-zones-without-a-prior-zone-migration). The same order applies to 3rd-party monitors: migrate them with [`ext-monitors-migration.md`](../../digital-experience/ext-monitors-migration/ext-monitors-migration.md) first, then recreate the windows that cover them.

> **Problem notification migration must be complete before step 11.**
> Suppression during a gen3 window only happens because the consumer of the problem filters on `maintenance.is_under_maintenance`. A Workflow problem trigger can do that. A classic `builtin:problem.notifications` entry cannot — neither it nor the `builtin:alerting.profile` it references accepts a DQL predicate, so there is nowhere to put the condition.
>
> While any classic problem notification is still active, the classic maintenance windows it depends on **cannot be disabled** — doing so produces maintenance-time notifications with no way to silence them. If that migration is incomplete, recreate the gen3 windows but leave the classic entries enabled, and report the remaining notifications as the blocker.

## Instructions

1. Read all classic maintenance windows:
   ```bash
   dtctl get settings --schema builtin:alerting.maintenance-window -o json --plain
   ```
2. Filter to future-relevant entries — expired windows are not migratable (see [Which windows are migratable](#which-windows-are-migratable)). **Do not produce a gen3 definition for an expired entry; report it separately and move on.**

   **Establish the current date first** — do not assume it. Every comparison below depends on it, and a window that looks future-dated against a stale assumption will be translated into a definition the API rejects.
    - For `ONCE` windows: keep entries where `schedule.onceRecurrence.endTime` is after today
    - For recurring windows: keep entries where the branch-specific range end is after today or not set — e.g., `schedule.weeklyRecurrence.recurrenceRange.scheduleEndDate` for WEEKLY; use `dailyRecurrence` or `monthlyRecurrence` accordingly
3. **Triage before translating anything.** Group the future-relevant windows along three axes and report the counts to the customer. Each axis can turn a window into prerequisite work rather than a straight recreation:

    - **Suppression mode** — anything other than `DETECT_PROBLEMS_AND_ALERT` needs workflow-level handling, and `DONT_DETECT_PROBLEMS` is lossy in gen3 regardless of what the schema offers. Needs an explicit customer decision. See [Suppression](#suppression).
    - **Filter scope** — windows filtered by `entityTags` or `managementZones` have no mechanical translation and may be blocked on primary tag or segment work. See [Filters](#filters).
    - **Schedule type** — `WEEKLY` and `MONTHLY` windows are blocked until an Automation scheduling rule exists. See [Schedule](#schedule).

   Expect a substantial fraction of a real estate to be blocked on prerequisites. Say so up front rather than discovering it window by window.

4. Resolve the indirect references the classic payload contains.

   **Management zones** — `managementZones` entries are **settings objectIds, not names**. Resolve them by reading `builtin:management-zones` and joining on objectId:
   ```bash
   dtctl get settings --schema builtin:management-zones -o json --plain
   ```
   The zone name is not usable in a gen3 filter either. **Migrate the management zone to a segment first, then use that segment in the maintenance window.** Management zone migration is covered by [`management-zones.md`](../../platform/management-zones/management-zones.md). Once it is done, find the segment that replaced each zone:
   ```bash
   dtctl get segments
   ```
   Match the resolved zone name against the segment `name`, and build the gen3 window `filter` from that segment's `includes` criteria (see the [management zone example](#weekly-recurring-window-with-management-zone-filter)). If no segment exists for the zone yet, the window is blocked: stop, run the management zone migration, then come back. If the customer does not want to migrate management zones first, use the segment-reference fallback in [Management zones without a prior zone migration](#management-zones-without-a-prior-zone-migration) instead. Deriving an ad-hoc filter from the zone rules here will diverge from the segment the customer ends up with.

   **Entity IDs** — a classic `entityId` may or may not equal its Smartscape ID, and you cannot tell by inspection. Always resolve it before using it in a gen3 filter. See [Resolving classic entity IDs](#resolving-classic-entity-ids).

5. Create any Automation scheduling rules needed by `WEEKLY` / `MONTHLY` windows (see [Schedule](#schedule)). Windows sharing a day-of-week or day-of-month share a single rule — collect the distinct recurrence patterns first so you create the minimum number of rules.
6. Convert each entry to the gen3 schema using the migration mapping below. **Preserve the recurrence, the start time, and the end time** of every window — `ONCE` stays `once`, `DAILY` / `WEEKLY` / `MONTHLY` stay recurring on the same days, and each occurrence starts and ends at the classic wall-clock times (see [Schedule](#schedule)). Where one of the three cannot be kept, flag it to the customer instead of changing it silently.
7. Present the proposed gen3 windows to the customer and ask for confirmation before creating them. Include the blocked ones and what unblocks each.
8. Once confirmed, write each window to a YAML file and apply:
   ```bash
   dtctl apply -f maintenance-window.yaml
   ```
   > `dtctl apply --dry-run` is a **client-side preview only** — it reports `{"action":"created"}` without contacting the API, even for a schema that does not exist. It confirms your YAML parses and nothing more. There is no server-side validation step available before the real write.

   If the apply is rejected because the start is in the past, move the start date to the day after today, keep the classic start time, duration and timezone, and apply again (see [Schedule](#schedule)). Tell the customer the start date was moved.
9. Verify the windows were created *and that their filters actually match something* — see [Validation](#validation). A window that matches nothing applies cleanly and looks healthy.
10. Update workflow problem triggers to respect maintenance, adding `maintenance.is_under_maintenance != true` wherever notifications should be suppressed. **The migration is not complete without this** — see [The behavioural change that drives everything else](#the-behavioural-change-that-drives-everything-else). Any routing still handled by classic `builtin:problem.notifications` cannot be updated this way; it must be migrated to a Workflow first (see Prerequisites).
11. Disable classic entries by setting `enabled: false` and applying — do not delete them to preserve rollback capability. If any classic problem notification covered by these windows is still active, skip this step: leave the classic entries enabled until those notifications have been migrated to Workflows (see [Prerequisite migrations](#prerequisite-migrations)).

> **Before disabling anything, check for windows already migrated and for externally managed config.** A tenant part-way through migration will have gen3 windows overlapping classic ones; re-running this procedure naively creates duplicates. Windows whose description marks them as managed by Monaco, Terraform, or similar must be changed at the source — disabling them by hand will be reverted on the next deployment.

## Migration mapping

### Schedule

A migrated window keeps three things from the classic one: its **recurrence** (type and days), its **start time**, and its **end time**. Every rule below serves that goal; the only permitted change is moving a past start date forward (see the exception below).

Set the start time and the duration of every migrated window like this:

- **Start time = the classic start time.** `once.date` is the classic `onceRecurrence.startTime`; `recurring.time` is the classic `timeWindow.startTime`. Copy it verbatim, in the classic timezone.
- **`duration` = classic end time − classic start time, in minutes.** `ONCE`: `onceRecurrence.endTime - onceRecurrence.startTime`, using the full classic datetimes. Recurring: `timeWindow.endTime - timeWindow.startTime`. Add 1440 **only** when that subtraction is negative (e.g. `23:30`–`00:30`: −1380 + 1440 = 60); a positive result is the duration as it stands. Never take it from `recurrenceRange`, a default, or the 10080 cap.
- **A recurring window whose end time is later than its start time never gets 24 hours added.** A recurring `09:00`–`10:00` window is `recurring.time: "09:00:00"` and `duration: 60` — not 1500, not 1440 + 60. The same holds for `10:00`–`11:00` (60) and `02:00`–`05:00` (180).
- **Calculate `duration` from the original classic times, before any date change.** Moving a past start date forward (see the exception below) never changes the duration — do not measure from the new `earliestStart` or `once.date` to the classic end time.
- **Check it before writing:** the gen3 duration must equal the classic window's length on the clock. A 1-hour classic window gives 60, not 1 day 1 hour.

| Classic (`builtin:alerting.maintenance-window`) | Gen3 (`builtin:maintenance-windows`) |
|---|---|
| `schedule.scheduleType: ONCE` + `onceRecurrence.startTime` | `schedule.trigger.type: once` + `once.date: <startTime>` |
| `schedule.scheduleType: DAILY` + `timeWindow.startTime` | `schedule.trigger.type: time` + `recurring.time: <startTime>` (no `rule` needed — fires every day) |
| `schedule.scheduleType: WEEKLY` + `weeklyRecurrence.dayOfWeek` + `timeWindow.startTime` | `schedule.trigger.type: time` + `recurring.time: <startTime>` + `recurring.rule: <scheduling-rule-uuid>` |
| `schedule.scheduleType: MONTHLY` + `monthlyRecurrence.dayOfMonth` + `timeWindow.startTime` | `schedule.trigger.type: time` + `recurring.time: <startTime>` + `recurring.rule: <scheduling-rule-uuid>` |
| `ONCE` duration: `onceRecurrence.endTime - onceRecurrence.startTime` in minutes | `schedule.duration: <minutes>` |
| Recurring duration: `<type>Recurrence.timeWindow.endTime - timeWindow.startTime` in minutes — one occurrence, never more than 1440 | `schedule.duration: <minutes>` |
| `schedule.<type>Recurrence.recurrenceRange.scheduleStartDate` / `scheduleEndDate` | `schedule.trigger.recurring.earliestStart` / `until` — the range the window recurs in, **not** its duration |
| `schedule.timeZone` | `schedule.timezone` |

> **Keep the classic start and end time exactly.** The gen3 window must start and end at the same wall-clock times, in the same timezone, as the classic one. Copy `startTime` verbatim into `once.date` / `recurring.time`, carry `timeZone` over unchanged, and compute `duration` from the classic `endTime - startTime` so the gen3 end time lands where the classic one did. Do not convert times to UTC, round them, shift them to "now", or adjust the duration. The same applies to `scheduleStartDate` / `scheduleEndDate` → `earliestStart` / `until`.
>
> **Recurring windows stay recurring.** A classic `DAILY`, `WEEKLY` or `MONTHLY` window becomes a gen3 `type: time` window that fires at `timeWindow.startTime` and ends at `timeWindow.endTime` on every occurrence. Never collapse it into one `once` window spanning the recurrence range, and never derive `duration` from `scheduleStartDate` / `scheduleEndDate` — that produces a duration over the 7-day cap, and clamping it to 10080 turns a nightly 3-hour window into week-long maintenance. A classic `02:00:00`–`05:00:00` window gives `recurring.time: "02:00:00"` and `duration: 180`. Only where `endTime` is earlier than `startTime` does the window cross midnight: add 1440 (e.g. `22:00:00`–`02:00:00` is `duration: 240`). In every other case, add nothing. A recurring duration of 1440 or more means the wrong fields were used.
>
> **Exception — start date in the past.** The API rejects a past `once.date`, and a past `earliestStart` is not needed. Where the classic start date has already passed (a `ONCE` window already in progress, or a recurring window whose `scheduleStartDate` is behind us), replace only the **date** with the day after today and keep the classic start **time**, duration, and timezone. For example, a classic `startTime: "2026-09-06T22:00:00"` migrated on 2026-10-21 becomes `once.date: "2026-10-22T22:00:00"`. Tell the customer the start date was moved.
>
> **If the API rejects the window because its start is in the past**, apply the same fix and retry: move the start date (`once.date`, or `earliestStart` for a recurring window) to the day after today, keeping the classic start time, `duration`, and timezone unchanged.

**WEEKLY and MONTHLY scheduling rules**: The `recurring.rule` field takes a UUID referencing an Automation scheduling rule — not an inline iCal RRULE string. Create the rule first in the Dynatrace UI (**Automations → Scheduling Rules**) or via the Automation API (`POST /platform/automation/v1/scheduling-rules`) using the appropriate RRULE expression (`FREQ=WEEKLY;BYDAY=SU`, `FREQ=MONTHLY;BYMONTHDAY=15`, etc.), then use the resulting rule UUID here.

> **⚠️ MONTHLY edge case**: Classic `monthlyRecurrence.dayOfMonth` values of 29, 30, or 31 run on the last day of the month when that day is absent. The scheduling rule API uses iCal RRULE semantics, which skip absent dates instead (e.g., `BYMONTHDAY=31` produces no February occurrence). Flag day-of-month values of 29–31 for manual review before migrating.

> **⚠️ "Mute forever" windows**: Classic estates commonly express indefinite suppression as a `ONCE` window with a far-future `endTime`, which converts to a duration far beyond the 7-day gen3 cap — a real example produced `duration: 35392818` (≈67 years). Do not migrate these mechanically. They express "mute this permanently", which is a different intent: recreate as a recurring window, or handle the entity outside maintenance windows entirely. Flag any converted duration longer than a few days.

> **Future occurrence required**: The API rejects any definition whose schedule yields no future firing date. A `once` window needs a future `once.date`; a recurring window needs at least one future occurrence within its `earliestStart` / `until` range.

### Gen3 schema

Dump the live schema before generating definitions rather than working from property lists in this document:

```bash
dtctl get settings-schemas builtin:maintenance-windows -o json
```

Two things the dump will not tell you:

- The schema is **flat**. There is no `generalProperties` object, `filters` array, `maintenanceType`, or `suppression` field. Build the gen3 object from scratch — do not adapt a classic payload.
- `objectScopes` may expose `suppressProblems` and `syntheticMonitors`, but **neither is functional yet** — see [The `objectScopes` capabilities are not functional yet](#the-objectscopes-capabilities-are-not-functional-yet).

### Schema limits

| Limit | Value | Consequence |
|---|---|---|
| `filter` length | 500 characters | Long mechanical translations are rejected — condense them |
| Objects per environment | 100 `builtin:maintenance-windows` objects | Classic allowed 2000. An estate with more classic windows than this cannot be migrated one-for-one; consolidate windows sharing a schedule |
| `schedule.duration` | 7 days (10080 minutes) | Classic allowed windows of any length. Anything longer must be split or re-expressed as a recurring window; far-future `ONCE` conversions overflow this. A migrated recurring window never hits this cap — its duration is one `timeWindow` occurrence (see [Schedule](#schedule)). Never clamp an overlong duration to 10080 |

If the customer will exceed either the object count or the duration cap, plan consolidation before migration starts.

### Filters

**There is no field-level mapping from classic filters to gen3.** Classic filters select *entities* via structured selectors. The gen3 `filter` is a DQL matcher expression evaluated against *signals* (events, problems, telemetry) using primary Grail fields and primary tags. The two models do not share a vocabulary, so most windows need a targeting decision rather than a translation.

> **⚠️ The filter field is not validated against real field names.** The schema attaches a `filter-validator`, but it checks syntax only. `matchesValue(totally_made_up_field_xyz, "x")` is accepted and saved without complaint — it simply never matches anything. A filter that references a field which does not exist produces a window that silently covers nothing. Never assume a filter is correct because `dtctl apply` succeeded; verify coverage per the Validation section below.

#### Classic filter semantics

Get these right or the translated scope will be wrong in ways nothing will flag:

* **Across filter objects: OR.** An entity matching any filter object is in scope.
* **Within one filter object: AND.** An entity must satisfy every condition in that object.
* **Empty `filters` array: matches the entire environment.** Easy to misread as unscoped or inactive.
* **`entityTags` and `managementZones` use ALL semantics** — the entity must carry *every* listed tag and belong to *every* listed zone, not any of them. Translating these as OR silently widens the window.
* **Entity tags are case-sensitive.**
* **Parent and group relationships are followed** — a window on a parent covered its immediate children, and a window on a group covered its immediate members. Gen3 infers nothing, so every entity intended to be in scope must be matched by the filter directly; a mechanical translation that ignores this produces silent under-coverage.

#### What you can filter on

The maintenance window scope offers suggestions for **[primary Grail fields](https://docs.dynatrace.com/docs/shortlink/semantic-dictionary-primary-grail-fields)** and **[primary tags](https://docs.dynatrace.com/docs/shortlink/primary-tags#tags)**. Prefer these — they are enriched onto every signal, which is what the filter is evaluated against.

| Category | Fields |
|---|---|
| AWS | `aws.account.id`, `aws.region` |
| Azure | `azure.location`, `azure.resource.group`, `azure.subscription` |
| GCP | `gcp.project.id`, `gcp.region` |
| Kubernetes | `k8s.cluster.name`, `k8s.namespace.name` |
| Dynatrace | `dt.host_group.id` |
| Primary tags | `primary_tags.<key>` — e.g. `primary_tags.team`, `primary_tags.stage` |

Syntax, all forms observed in working windows:

```
true                                                     # whole environment
matchesValue(k8s.cluster.name, "*dtp-prod20-*")          # wildcards supported
matchesValue(primary_tags.stage, "prod")                 # single tag value
matchesValue(primary_tags.stage, {"prod", "staging"})    # set literal matches any of
matchesValue(aws.region, "us-east-1") AND matchesValue(k8s.namespace.name, "prod")
matchesValue(dt.smartscape.service, "SERVICE-0000000000000000")   # a single entity
isNotNull(dt.smartscape.host)                            # every entity of a type
isNotNull(dt.security_context)
```

Fields outside the primary set (`dt.smartscape.*`, `event.type`, `dt.security_context`) do work in practice, but they are not suggested in the UI and are not guaranteed present on every signal. Use them deliberately, and verify coverage.

There is **no** `monitor.id`, `monitor.name`, `pg.tag` or `security.context` field — do not use them. Synthetic monitors are targeted through `dt.smartscape.http_monitor`, `dt.smartscape.browser_monitor` and the other Smartscape fields in the [type mapping table](#classic-entity-type--smartscape-field); primary tags through `primary_tags.<key>`; security context through `dt.security_context`.

> **Use `dt.smartscape.*`, never `dt.entity.*`.** The `dt.entity.*` fields are deprecated classic syntax. Entity references belong in the Smartscape namespace — `dt.smartscape.host`, `dt.smartscape.service`, `dt.smartscape.browser_monitor`, and so on.

#### Translating classic filters

| Classic filter field | What to do in gen3 |
|---|---|
| No filter / empty `filters` (whole environment) | `filter: "true"` — the only fully mechanical case |
| `entityType` only | `isNotNull(dt.smartscape.<entity>)` — **every** entity of that type. See the [type mapping table](#classic-entity-type--smartscape-field) |
| `entityType` + `entityId` | `matchesValue(dt.smartscape.<entity>, "<SMARTSCAPE-ID>")` — that one entity. Resolve the ID first |
| `entityId` only | `matchesValue(dt.smartscape.<entity>, "<SMARTSCAPE-ID>")`, using the type implied by the resolved ID |
| `managementZones: [...]` | **No equivalent.** Management zones are replaced by **segments**, and the mapping is not 1:1 — you must find the zone rule's *discriminator* and check it is enriched on the data. This is its own migration, covered by [`management-zones.md`](../../platform/management-zones/management-zones.md), which must be completed before this one. Migrate the zone to a segment first, then build the window filter from that segment's `includes` criteria rather than re-deriving it. |
| `entityTags: [...]` | **No mechanical equivalent.** Classic tags are Smartscape-node-local; the filter needs primary tags. See below. |

#### Management zones without a prior zone migration

If the customer does not want to migrate management zones first, migrate the window anyway and let a segment do the scoping:

1. Create a segment for the zone, or reuse one that already covers it. Its `includes` criteria select what the zone selected.
2. In the gen3 window, reference that segment in the schema's segment property, and set `filter: "*"`. The segment narrows the window. The filter adds no further restriction. Take the property name and format from the schema dump (see [Gen3 schema](#gen3-schema)). Do not guess it.
3. Tell the customer that this window's scope now depends on that segment, and that the segment must be kept in line with the zone until the management zone migration happens.

Verify coverage as for any other window (see [Validation](#validation)). An empty or wrong segment produces a window that applies cleanly and covers nothing.

> **⚠️ Do not translate an `entityType`-only filter to an ID comparison.** `entityType: HOST` with no `entityId` means *every host in the environment*. Writing `matchesValue(dt.smartscape.host, "HOST-...")` silently narrows a whole-fleet window down to a single host — a window that applies cleanly, reports healthy, and covers almost nothing.

#### Resolving classic entity IDs

A classic `entityId` and the corresponding Smartscape ID are **sometimes** the same string, but often they are not — and you cannot tell which case you are in by looking at the ID. Where they differ, feeding the classic ID into `matchesValue()` produces a filter that matches nothing, and the syntax-only validator will not catch it.

So never assume the IDs are interchangeable. **Always resolve** — it is cheap, and it is the only way to be certain:

```dql
smartscapeNodes "*" | filter in(id_classic, {"HOST-abc1234"}) | fields id, id_classic, name, type
```

Batch multiple IDs into one lookup:

```dql
smartscapeNodes "*" | filter in(id_classic, {"HOST-aaa", "HOST-bbb", "SERVICE-ccc"}) | fields id, id_classic, name, type
```

The `id` column is the Smartscape ID to use in the filter — e.g. `matchesValue(dt.smartscape.host, "HOST-xyz9999")`. If it comes back equal to `id_classic`, fine: that is one of the cases where the two coincide, and you have confirmed it rather than guessed it.

Read the `type` column too: where the Smartscape field depends on the resolved type rather than the classic prefix — notably `CLOUD_APPLICATION`, which maps to one of several `k8s_*` workload kinds — `type` tells you which field to filter on.

If a classic ID returns no row, the entity no longer exists in Smartscape. Report it rather than guessing a substitute.

#### Classic entity type → Smartscape field

Derived from [type-mappings.md](../../platform/entity-queries/type-mappings.md).

| Classic `entityType` | Smartscape field | `entityType`-only filter |
|---|---|---|
| `HOST` | `dt.smartscape.host` | `isNotNull(dt.smartscape.host)` |
| `DISK` | `dt.smartscape.disk` | `isNotNull(dt.smartscape.disk)` |
| `SERVICE` | `dt.smartscape.service` | `isNotNull(dt.smartscape.service)` |
| `SERVICE_INSTANCE` | `dt.smartscape.service_deployment` | `isNotNull(dt.smartscape.service_deployment)` |
| `PROCESS_GROUP_INSTANCE` | `dt.smartscape.process` | `isNotNull(dt.smartscape.process)` |
| `APPLICATION` / `CUSTOM_APPLICATION` | `dt.smartscape.frontend` | `isNotNull(dt.smartscape.frontend)` |
| `CONTAINER_GROUP_INSTANCE` | `dt.smartscape.container` | `isNotNull(dt.smartscape.container)` |
| `KUBERNETES_CLUSTER` | `dt.smartscape.k8s_cluster` | `isNotNull(dt.smartscape.k8s_cluster)` |
| `KUBERNETES_NODE` | `dt.smartscape.k8s_node` | `isNotNull(dt.smartscape.k8s_node)` |
| `KUBERNETES_SERVICE` | `dt.smartscape.k8s_service` | `isNotNull(dt.smartscape.k8s_service)` |
| `CLOUD_APPLICATION_INSTANCE` | `dt.smartscape.k8s_pod` | `isNotNull(dt.smartscape.k8s_pod)` |
| `CLOUD_APPLICATION_NAMESPACE` | `dt.smartscape.k8s_namespace` | `isNotNull(dt.smartscape.k8s_namespace)` |
| `CLOUD_APPLICATION` | one of `dt.smartscape.k8s_deployment`, `k8s_daemonset`, `k8s_statefulset`, `k8s_replicaset`, `k8s_replicationcontroller`, `k8s_job`, `k8s_deploymentconfig` | `OR` the non-null checks for the workload kinds in scope |
| `NETWORK_INTERFACE` | `dt.smartscape.network_interface` | `isNotNull(dt.smartscape.network_interface)` |
| `EC2_INSTANCE` | `dt.smartscape.aws_ec2_instance` | `isNotNull(dt.smartscape.aws_ec2_instance)` |
| `EBS_VOLUME` | `dt.smartscape.aws_ec2_volume` | `isNotNull(dt.smartscape.aws_ec2_volume)` |
| `AZURE_VM` | `dt.smartscape.azure_microsoft_compute_virtualmachines` | `isNotNull(dt.smartscape.azure_microsoft_compute_virtualmachines)` |
| `RELATIONAL_DATABASE_SERVICE` | `dt.smartscape.aws_rds_dbinstance` | `isNotNull(dt.smartscape.aws_rds_dbinstance)` |
| `AWS_LAMBDA_FUNCTION` | `dt.smartscape.aws.lambda_function` | `isNotNull(dt.smartscape.aws.lambda_function)` |
| `HTTP_CHECK` | `dt.smartscape.http_monitor` | `isNotNull(dt.smartscape.http_monitor)` |
| `HTTP_CHECK_STEP` | `dt.smartscape.http_monitor_step` | `isNotNull(dt.smartscape.http_monitor_step)` |
| `SYNTHETIC_TEST` | `dt.smartscape.browser_monitor` | `isNotNull(dt.smartscape.browser_monitor)` |
| `SYNTHETIC_TEST_STEP` | `dt.smartscape.browser_monitor_step` | `isNotNull(dt.smartscape.browser_monitor_step)` |
| `SYNTHETIC_LOCATION` | `dt.smartscape.synthetic_location` | `isNotNull(dt.smartscape.synthetic_location)` |
| `MULTIPROTOCOL_MONITOR` | `dt.smartscape.network_availability_monitor` | `isNotNull(dt.smartscape.network_availability_monitor)` |
| `OS:SERVICE` | `dt.smartscape.os_service` | `isNotNull(dt.smartscape.os_service)` |

Where [type-mappings.md](../../platform/entity-queries/type-mappings.md) marks a mapping `planned` rather than `available`, confirm the field is actually populated in the target environment before relying on it.

Several classic types have **no Smartscape entity at all** and need a different discriminator:

| Classic `entityType` | Translate instead as |
|---|---|
| `HOST_GROUP` | `isNotNull(dt.host_group.id)` for any host group, or `matchesValue(dt.host_group.id, "<name>")` for a specific one — it is a field on `HOST`, not an entity |
| `PROCESS_GROUP` | `matchesValue(dt.process_group.id, "<id>")` — a field on `PROCESS`, not an entity |
| `CONTAINER_GROUP` | No equivalent; scope to `dt.smartscape.container` instead |
| `CUSTOM_DEVICE`, `CUSTOM_DEVICE_GROUP` | No Smartscape replacement; scope by the extension's own fields, for example `device` |
| `ENVIRONMENT` | No equivalent; an environment-wide window is `filter: "true"` |

Extension and cloud types (`sql:postgres_database`, `cloud:aws:aurora`) have no documented gen3 filter representation — flag these for manual scoping.

#### On `entityTags`

Three traps here:

- **The data shape is not what the schema docs imply.** In practice `entityTags` is a flat array of strings already in `key:value` form, not an array of `{context, key, value}` objects: `["AZURE_POSTGRES", "Dtp_Capability:grail", "Dtp_Name:[Azure]dtp-prod102-grail"]`. Values may carry bracketed context prefixes (`[AWS]`, `[Azure]`) and escaped colons (`[AWS]ACE\:CREATED-BY:...`). Read the real values before assuming a format.
- **Classic tags are not primary tags.** Primary tags are derived from OneAgent configuration, Kubernetes labels, cloud provider tags, OpenTelemetry resource attributes, host/process metadata, and OpenPipeline rules — *not* from classic manual or auto-tags. A classic tag will not appear as `primary_tags.<key>` just because it exists.
- **Classic tags visible in Grail today will not survive the upgrade.** Before the upgrade is triggered, classic tags are still present on signals as `entity_tags` (an array, on events) and on Smartscape nodes as `tags` (a record). They are tempting to filter on, because they carry the classic `key:value` strings verbatim. Do not. They are an artifact of the pre-upgrade state, not enrichment you can rely on. Identical queries over a 7-day window, one tenant in each phase:

  | Signal | Phase 1 (pre-upgrade) | Phase 3 (post-upgrade) |
    |---|---|---|
  | `dt.davis.events` | 16,228,269 / 21,886,327 (74%) | **0 / 30,987** |
  | `events` | — | 84,088 / 12,003,898 (0.7%) |
  | `logs` | — | 0 / 741,117,209 |
  | `metrics` | — | 0 / 100,000 |

  A filter built on `entity_tags` therefore matches millions of events while you are developing it and **silently stops matching once the customer completes the upgrade** — the failure lands after migration, when nobody is still watching. This is the silent-no-match failure described above, on a delay, and the syntax-only validator will not catch it.

  On Smartscape nodes the field is `tags`, not `entity_tags`, and it is a record rather than an array. It is not an alternative to properly setting up primary tags.

So for every tag-scoped window, check whether a primary tag or primary field already identifies the same entities. Often a cloud tag or Kubernetes label the classic tag was itself derived from is available directly. Where nothing equivalent exists, establishing primary tag coverage is **prerequisite work the customer must complete before the window can be recreated** — surface it as its own task, not a migration detail. If the customer does not want to do that first, see [Tags without primary tag coverage](#tags-without-primary-tag-coverage).

That work is the tagging migration itself, not something to solve inside this one: see [`autotagging.md`](../../platform/autotagging/autotagging.md) for classic auto-tags → static tagging at source, and the OpenPipeline enrichment path in [`management-zones.md`](../../platform/management-zones/management-zones.md) for tags that have to be applied in the pipeline. Push the customer toward real primary tag coverage rather than improvising a filter from the classic tags still visible on their data pre-upgrade.

#### Tags without primary tag coverage

If the customer does not want to migrate classic tags to primary tags first, or the entities (for example, synthetic monitors) have no primary tags yet, migrate the window anyway with the classic tag key and a wildcard value:

```
matchesValue(primary_tags.<key>, "*")
```

1. Take `<key>` from the classic tag (`env:prod` → `primary_tags.env`). Several classic tags use ALL semantics, so join one `matchesValue(...)` per key with `AND`.
2. Tell the customer what the window will do. It matches every signal that carries that primary tag key, whatever the value, so it is wider than the classic `key:value` tag. It matches nothing until that primary tag key exists on the data.
3. Record the window as follow-up work. Once primary tags are in place, replace `"*"` with the real value.

Verify coverage as for any other window (see [Validation](#validation)).

#### Filter length limit

`filter` has a **500-character maximum**. Mechanically expanding a multi-entity-type classic filter into per-type AND/OR branches overruns this routinely. If a filter exceeds 500 characters, condense it — hoist the shared discriminator out of the OR branches rather than repeating it per branch, and drop redundant type guards where the tag or field is already unique.

### General properties

| Classic field | Gen3 field |
|---|---|
| `generalProperties.name` | `name` |
| `generalProperties.description` | `description` |
| `enabled` | `enabled` |
| `generalProperties.disableSyntheticMonitorExecution: true` | `objectScopes.syntheticMonitors.disableSyntheticMonitors: true` + `objectScopes.syntheticMonitors.disableSyntheticMonitorFilter` — property rules in [`classic-maintenance-windows-synthetic.md`, Step 6](classic-maintenance-windows-synthetic.md#step-6-decide-on-monitor-execution); **not functional yet**; monitors keep executing. Automate enable/disable around the window in the meantime |

Note that `disableSyntheticMonitorFilter` is a **second, independent filter**. The top-level `filter` drives enrichment; `disableSyntheticMonitorFilter` selects which monitors to pause. In classic, one scope drove both effects — so the same scope usually has to be expressed twice.

> **⚠️ The two filters do not accept the same fields.** The top-level `filter` takes essentially any valid DQL matcher over Grail fields. `disableSyntheticMonitorFilter` accepts **only this subset**:
>
> | Field | Notes |
> |---|---|
> | `id` | The monitor's Smartscape ID — bare `id`, **not** `dt.smartscape.http_monitor` |
> | `name` | The monitor's name |
> | `primary_tags.<key>` | Primary tags on the monitor |
> | `dt.security_context` | Security context |
>
> Nothing else is permitted — no `dt.smartscape.*`, no cloud or Kubernetes primary fields, no `entity_tags`. So the "express the same scope twice" advice above is a simplification: the second expression has to be **rewritten** into these fields rather than copied.
>
> The restriction is narrower but not crippling, because `id` covers the common cases:
>
> | Intent | Top-level `filter` | `disableSyntheticMonitorFilter` |
> |---|---|---|
> | One specific monitor | `matchesValue(dt.smartscape.http_monitor, "HTTP_MONITOR-abc")` | `matchesValue(id, "HTTP_MONITOR-abc")` |
> | Every synthetic monitor | `isNotNull(dt.smartscape.http_monitor)` | `isNotNull(id)` |
> | All monitors of one type | `isNotNull(dt.smartscape.http_monitor)` | `matchesValue(id, "HTTP_MONITOR-*")` — the Smartscape ID prefix encodes the monitor type, and `matchesValue` supports wildcards |
> | Tagged monitors | `matchesValue(primary_tags.team, "x")` | same expression — `primary_tags.*` is allowed in both |
>
> The type-prefix wildcard in the last-but-one row is inferred from the documented ID prefixes plus wildcard support; confirm it against the target environment before relying on it. If it does not hold, fall back to `isNotNull(id)` (pauses **all** synthetic monitors — broader than the classic scope, so get customer agreement) or enumerate by `id` / `name` within the 500-character cap.

### Suppression

There is no functional gen3 field for suppression. `objectScopes.suppressProblems` may exist in the schema but does not work yet (see [The `objectScopes` capabilities are not functional yet](#the-objectscopes-capabilities-are-not-functional-yet)), so **every** classic mode maps onto "gen3 window + a corresponding change outside the window":

| Classic `suppression` | Gen3 equivalent |
|---|---|
| `DETECT_PROBLEMS_AND_ALERT` | Gen3 default. Recreate the window; leave workflows untouched. Alerts continue to route, now carrying maintenance metadata. |
| `DETECT_PROBLEMS_DONT_ALERT` | Closest fit to how gen3 actually works. Recreate the window, then add `maintenance.is_under_maintenance != true` to the problem trigger of every workflow and alert-routing rule that should stay silent. |
| `DONT_DETECT_PROBLEMS` | **No equivalent.** Gen3 always detects problems and always creates them. `objectScopes.suppressProblems` does not change this today even where the schema accepts it. The nearest approximation is the `DETECT_PROBLEMS_DONT_ALERT` treatment above: problems still appear in the Problems app, flagged `maintenance.is_under_maintenance = true`, and can be filtered out of views. Confirm with the customer that visible-but-flagged problems are acceptable. |

Caveats where suppression is handled in the workflow layer: the condition must be set on **every** workflow that should stay quiet (consolidating notifications into fewer workflows, which the alerting reference recommends anyway, reduces this); it covers workflow-driven notifications only; and problems are still **created**, so problem counts, dashboards, and SLO error budgets still see them. A customer coming from `DONT_DETECT_PROBLEMS` will see problem volume increase — flag this before cutover.

> **`maintenanceType` needs no gen3 equivalent — it is a label, not behaviour.** `PLANNED` vs `UNPLANNED` is a display string. It appears exactly once in the classic schema, as its own enum on `generalProperties`, and no other property is gated on it. What a window actually does is set entirely by `suppression`, which is independent of the type.
>
> So an `UNPLANNED` window is not a special case. Map it by its `suppression` value like any other window using the table above, and drop the type. Do not leave it enabled on the grounds that gen3 "cannot represent" it.
>
> What gen3 genuinely cannot do is apply a window **retroactively**. Classic `UNPLANNED` windows were often declared after an incident; a gen3 window created after the fact enriches nothing, because enrichment happens at ingest and Grail data is not back-filled.

> **New in gen3**: `autoDelete` — **defaults to `true`**, so the window is automatically removed 30 days after its last execution unless set otherwise. Set it to `false` explicitly to retain the window after it completes.

## Examples

### One-time future window with tag filter

Classic (`builtin:alerting.maintenance-window`):

```json
{
  "enabled": true,
  "generalProperties": {
    "name": "Weekend DB maintenance",
    "description": "Planned DB upgrade",
    "maintenanceType": "PLANNED",
    "suppression": "DONT_DETECT_PROBLEMS",
    "disableSyntheticMonitorExecution": false
  },
  "schedule": {
    "scheduleType": "ONCE",
    "onceRecurrence": {
      "startTime": "2026-09-06T22:00:00",
      "endTime": "2026-09-07T06:00:00",
      "timeZone": "Europe/Warsaw"
    }
  },
  "filters": [
    { "entityTags": ["env:prod"] }
  ]
}
```

The tag `env:prod` is a classic tag, so it is not usable in a gen3 filter. Before this window can be recreated, establish what identifies the same entities in Grail. Here the customer confirmed the hosts carry the primary tag `primary_tags.stage`, so the filter targets that:

Gen3 equivalent (`dtctl apply` YAML):

```yaml
- schemaId: builtin:maintenance-windows
  scope: environment
  value:
    name: Weekend DB maintenance
    description: Planned DB upgrade
    enabled: true
    autoDelete: false
    filter: 'matchesValue(primary_tags.stage, "prod")'
    schedule:
      trigger:
        type: once
        once:
          date: "2026-09-06T22:00:00"
      duration: 480
      timezone: Europe/Warsaw
```

`DONT_DETECT_PROBLEMS` has no top-level gen3 equivalent. Where `objectScopes.suppressProblems` is unavailable, the intent moves to the workflow trigger — see [Suppression](#suppression).

### Weekly recurring window with management zone filter

Classic:

```json
{
  "enabled": true,
  "generalProperties": {
    "name": "Weekly patching",
    "maintenanceType": "PLANNED",
    "suppression": "DONT_DETECT_PROBLEMS",
    "disableSyntheticMonitorExecution": false
  },
  "schedule": {
    "scheduleType": "WEEKLY",
    "weeklyRecurrence": {
      "dayOfWeek": "SUNDAY",
      "timeWindow": {
        "startTime": "02:00:00",
        "endTime": "05:00:00",
        "timeZone": "UTC"
      },
      "recurrenceRange": {
        "scheduleStartDate": "2026-09-01",
        "scheduleEndDate": "2027-03-31"
      }
    }
  },
  "filters": [
    { "managementZones": ["vu9U3hXa3q0AAAABABhidWlsdGluOm1hbmFnZW1lbnQtem9uZXMABnRlbmFudAAGdGVuYW50ACRhMjc4NWI5Zi1mYzQ0..."] }
  ]
}
```

Note the management zone is an objectId. For example, resolving it against `builtin:management-zones` gives the name `Production`; the zone's replacement is the segment of the same name, whose `includes` criteria show it selects the `prod-us-east` Kubernetes clusters. That is what the gen3 filter targets:

Gen3 equivalent (`dtctl apply` YAML):

```yaml
- schemaId: builtin:maintenance-windows
  scope: environment
  value:
    name: Weekly patching
    enabled: true
    autoDelete: false
    filter: 'matchesValue(k8s.cluster.name, "prod-us-east-*")'
    schedule:
      trigger:
        type: time
        recurring:
          time: "02:00:00"
          earliestStart: "2026-09-01"
          until: "2027-03-31"
          rule: "<weekly-sunday-scheduling-rule-uuid>"
      duration: 180
      timezone: UTC
```

### Window scoped to a specific entity, disabling synthetic execution

Classic — a single `entityId`, plus `disableSyntheticMonitorExecution`:

```json
{
  "enabled": true,
  "generalProperties": {
    "name": "API maintenance",
    "maintenanceType": "PLANNED",
    "suppression": "DETECT_PROBLEMS_AND_ALERT",
    "disableSyntheticMonitorExecution": true
  },
  "schedule": {
    "scheduleType": "ONCE",
    "onceRecurrence": {
      "startTime": "2026-08-12T16:00:00",
      "endTime": "2026-08-12T17:00:00",
      "timeZone": "Europe/Warsaw"
    }
  },
  "filters": [
    { "entityType": "HTTP_CHECK", "entityId": "HTTP_CHECK-1A2B3C4D5E6F7788" }
  ]
}
```

The classic `entityId` must be resolved to its Smartscape ID before it can be used:

```dql
smartscapeNodes "*" | filter in(id_classic, {"HTTP_CHECK-1A2B3C4D5E6F7788"}) | fields id, id_classic, name, type
```

Assume that returns `id = "HTTP_MONITOR-91954855562522AD"`. Because the classic filter carried an `entityId`, this becomes an ID match rather than a non-null check — and the scope has to be written twice, once for enrichment and once for the synthetic pause:

```yaml
- schemaId: builtin:maintenance-windows
  scope: environment
  value:
    name: API maintenance
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
    objectScopes:
      syntheticMonitors:
        disableSyntheticMonitors: true
        # Restricted field set — bare `id`, not dt.smartscape.http_monitor
        disableSyntheticMonitorFilter: 'matchesValue(id, "HTTP_MONITOR-91954855562522AD")'
```

Note the two filters use **different field names for the same monitor**: the top-level `filter` uses `dt.smartscape.http_monitor`, while `disableSyntheticMonitorFilter` must use bare `id`, because it only accepts `id`, `name`, `primary_tags.*` and `dt.security_context` (see [General properties](#general-properties)). Copying the top-level filter verbatim into the second field will be rejected.

The `objectScopes.syntheticMonitors` block above is **forward-preparation only** — it does not pause anything today, and there is no way to verify that it will. Omit it entirely if the schema does not accept it. Either way the synthetic-disable behaviour is lost for now: tell the customer these monitors will keep executing against the system under maintenance, and agree on automating enable/disable around the window if that traffic matters.

## Outcome

After migration, all future maintenance windows must be handled by `builtin:maintenance-windows`. All classic `builtin:alerting.maintenance-window` entries for future windows must be disabled.

Report the full inventory and its status as a table:

| Classic window | Classic suppression | Synthetic disable | Gen3 `filter` | Enforcement follow-ups | Status |
|---|---|---|---|---|---|
| Weekly patching | `DONT_DETECT_PROBLEMS` | no | `matchesValue(k8s.cluster.name, "prod-us-east-*")` | workflow trigger condition | definition ready |
| API maintenance | `DETECT_PROBLEMS_AND_ALERT` | yes | `matchesValue(dt.smartscape.http_monitor, "...")` | automate monitor enable/disable — `syntheticMonitors` not functional | definition ready, behaviour gap flagged to customer |

## Validation

**Creating the window proves nothing about coverage.** The filter validator is syntax-only, so a window referencing a nonexistent field saves successfully, reports healthy, and matches nothing. Validate coverage explicitly.

**Preview the filter before applying.** The maintenance window UI previews scope by appending the filter to a set of probe queries. Run the same probes with `dtctl` to check the filter matches what the customer expects. Each probe below is written with a worked example filter, `matchesValue(aws.region, "us-east-1")` — replace that expression with the one from the window being migrated.

Smartscape nodes:

```dql
smartscapeNodes "*", from:now()-2h | filter matchesValue(aws.region, "us-east-1") | limit 50
```

Davis events:

```dql
fetch dt.davis.events | filter matchesValue(aws.region, "us-east-1") | limit 50
```

Metrics:

```dql
metrics | filter matchesValue(aws.region, "us-east-1") | limit 50
```

User sessions:

```dql
fetch user.sessions | filter matchesValue(aws.region, "us-east-1") | limit 50
```

Synthetic monitor executions — `dt.synthetic.monitor.smartscape.id` selects them regardless of monitor type:

```dql
fetch events | filter isNotNull(dt.synthetic.monitor.smartscape.id) | filter matchesValue(aws.region, "us-east-1") | limit 50
```

Run each one with `dtctl query`:

```bash
dtctl query 'smartscapeNodes "*", from:now()-2h | filter matchesValue(aws.region, "us-east-1") | limit 50'
```

Empty results across all five probes means the filter matches nothing — treat that as a failed migration for that window, not a quiet success. Run this **before** applying, since the filter validator will not catch it afterwards.

Then confirm the window exists and check the filter that was actually stored:

```bash
dtctl get settings --schema builtin:maintenance-windows -o json --plain
```

Once a window has elapsed, confirm it took effect:

```dql
fetch events
| filter event.kind == "MAINTENANCE_WINDOW"
| dedup { maintenance_window.instance_id }, sort: { timestamp desc }
| fields maintenance_window.title, maintenance_window.filter, start_time, end_time
| sort start_time desc
```

Migration is complete when:

- Every future-dated classic entry has `enabled: false`
- Disabled classic entries have been retained, not deleted, for rollback capability
- At least one `builtin:maintenance-windows` entry exists and is active for each migrated window
- **Each gen3 window has been confirmed to match the intended entities** — not merely to have been created
- **Workflow problem triggers and alert-routing rules carry `maintenance.is_under_maintenance != true`** wherever the classic window previously suppressed alerting. Without this the customer will receive notifications they did not receive before.
- Windows blocked on prerequisites (primary tags, segments, scheduling rules) are recorded and handed back to the customer as explicit follow-up work
- **The customer has been told, explicitly, that problems are still created and alerted on during maintenance and that synthetic monitors still execute** — because `objectScopes.suppressProblems` and `objectScopes.syntheticMonitors` are not functional yet, regardless of whether the schema accepts them

## References

- [Settings API — Maintenance windows (gen3) schema](https://docs.dynatrace.com/docs/dynatrace-api/environment-api/settings/schemas/builtin-maintenance-windows)
- [Settings API — Classic maintenance window schema](https://docs.dynatrace.com/docs/dynatrace-api/environment-api/settings/schemas/builtin-alerting-maintenance-window)
- [Maintenance windows (Dynatrace Docs)](https://docs.dynatrace.com/docs/analyze-explore-automate/alerting-and-notifications/maintenance-windows) — gen3 overview, lifecycle, creation, and Grail usage
- [Use maintenance window data in Grail](https://docs.dynatrace.com/docs/shortlink/use-maintenance-window-data-grail) — confirms gen3 windows enrich rather than suppress, and documents the `maintenance.is_under_maintenance != true` workflow filter
- [Semantic dictionary — primary Grail fields](https://docs.dynatrace.com/docs/shortlink/semantic-dictionary-primary-grail-fields) — the fields offered as filter suggestions
- [Primary tags](https://docs.dynatrace.com/docs/shortlink/primary-tags#tags) — `primary_tags.*` convention and how primary tags are derived
- [`classic-maintenance-windows-synthetic.md`](classic-maintenance-windows-synthetic.md) — Migration guide for maintenance windows scoped to synthetic monitors (`SYNTHETIC_TEST`, `SYNTHETIC_TEST_STEP`, `HTTP_CHECK`, `HTTP_CHECK_STEP`, `SYNTHETIC_LOCATION`, `EXTERNAL_SYNTHETIC_TEST`, `EXTERNAL_SYNTHETIC_TEST_STEP`); filter mapping, phase requirements, and payload shape differ from the general guide above
- [`management-zones.md`](../../platform/management-zones/management-zones.md) — Management zone migration; prerequisite for any window filtered by `managementZones`, and the source of the segment or primary field to filter on
- [`autotagging.md`](../../platform/autotagging/autotagging.md) — Classic auto-tags → primary tags; prerequisite for any window filtered by `entityTags`
- [`alerting-and-problem-notifications.md`](../../platform/alerting-and-problem-notifications/alerting-and-problem-notifications.md) — Problem-notification migration to Workflows; where maintenance-aware alerting is actually configured
- [`entity-queries.md`](../../platform/entity-queries/entity-queries.md) and [`type-mappings.md`](../../platform/entity-queries/type-mappings.md) — Classic entity model → Smartscape mappings, for resolving entity IDs and selecting the right `dt.smartscape.*` field
- `dt-alerting` skill — full alerting lifecycle on the new platform; use it for all Workflow and trigger configuration guidance rather than configuring from this reference
