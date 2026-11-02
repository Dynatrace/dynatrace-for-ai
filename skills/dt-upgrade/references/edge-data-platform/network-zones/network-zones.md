# Network Zones Enforcement

**Gen3 replacement**: -- (network zones remain; enforcement becomes always-on)

**Phase 2 required**: yes

## What changes

Network zones let a customer control which ActiveGates a OneAgent may connect
to. In Phase 2, enforcement of those zones is a tenant-wide toggle. When the
toggle is off, zone definitions still exist as settings objects but do **not**
govern where OneAgents send their traffic — they are inert.

In Phase 3 enforcement is always on. The same definitions start governing
OneAgent-to-ActiveGate routing the moment enforcement takes effect. This is what
makes an unvalidated zone dangerous: a definition with no effect today can
silently break OneAgent routing tomorrow. The risk is not that network zones
change — it is that configurations nobody has exercised suddenly become
load-bearing.

So the assessment has two halves, and reporting only the first is not useful:

1. **Is the tenant compliant?** — is enforcement already on, or is there nothing
   to enforce?
2. **If not, is enabling enforcement safe?** — would any OneAgent lose its route
   once these definitions start being honoured?

## Prerequisites

- Settings 2.0 read access to `builtin:networkzones` and
  `builtin:networkzones.zones`.
- Grail access to `smartscapeNodes ACTIVEGATE` and the
  `dt.sfm.active_gate.system.cpu_usage` metric.
- A `dtctl` context for the tenant being assessed. Enforcement, zone
  definitions, and ActiveGates are all per tenant, so **assess each tenant
  separately** and report per tenant — never generalize one tenant's verdict to
  another.

## Instructions

1. Run tracking query **1 (enforcement state)**. If the schema is absent or the
   result is empty, or the object reports `enabled: false`, enforcement is
   **not** enabled — record that and continue. Do not treat it as a failed
   assessment (see the callout under query 1).
2. Run tracking query **2 (zone definitions)**. Keep `id`, `fallbackMode`, and
   `alternativeZones` for every object; all three are needed in step 5.
3. Run tracking query **3 (ActiveGate zone assignment)**.
4. Determine compliance:

   ```
   compliant = enforcement_enabled
               OR (no zone definitions AND no ActiveGate with a non-default zone)
   ```

   Note the two independent non-compliance triggers. An ActiveGate can carry a
   non-`default` zone even when no zone definitions exist, and that assignment
   becomes load-bearing too — a check that looks only at zone definitions
   under-detects.
5. If the tenant is **not** compliant, run tracking query **4 (routing
   coverage)** and classify every zone from step 2 as described in
   [Classifying zones](#classifying-zones). Do not skip this because the verdict
   is already known: the severity is what tells the customer whether enabling
   enforcement is safe, and CRITICAL zones are the finding that matters.
6. If any zone is CRITICAL, run tracking query **5 (live ActiveGates)** to
   confirm the coverage picture reflects gates that are actually connected, not
   just configured.
7. Report using the tables in [Outcome](#outcome), then walk the customer
   through the matching branch in [Customer actions](#customer-actions).
8. **Do not change tenant settings as part of the assessment.** Enabling
   enforcement is a single tenant-wide toggle that immediately affects OneAgent
   routing for every host, and deleting zone definitions is equally
   consequential. Present the plan and let the customer execute it, or get
   explicit per-change confirmation first.

If a check cannot run — missing permission, query error — report the tenant as
**inconclusive** and say which check failed. Do not report a tenant as compliant
on the strength of the checks that did succeed.

## Tracking queries

### 1. Enforcement state

```bash
dtctl get settings --schema builtin:networkzones -o json --plain
```

Four distinct outcomes, only one of which means enforcement is on:

| Outcome | Meaning |
|---|---|
| HTTP 404, `No schema with topic identifier 'builtin:networkzones'` | The enforcement toggle has not been rolled out to this tenant. Enforcement is **not** enabled. |
| `[]` — schema present, no settings object | Enforcement is **not** enabled. |
| `[{"value":{"enabled":false}}]` | Enforcement is **not** enabled. |
| `[{"value":{"enabled":true}}]` | Enforcement is enabled. |

Read `enabled` explicitly rather than inferring enforcement from the object
merely existing — a present object with `enabled: false` is the same situation
as no object at all.

> **Important — an absent schema is not an error and not a pass:** this command
> exits non-zero on tenants where the schema does not exist. Treat both the 404
> and the empty array as *enforcement not enabled*, and keep going — reading
> `value.enabled` off the first array element without checking raises an error on
> exactly those tenants, and the assessment then reports nothing instead of
> reporting a real finding. An absent toggle also does not mean the tenant is
> safe: the zone definitions still become load-bearing when Phase 3 arrives, so
> queries 2 and 3 still have to run.

### 2. Zone definitions

```bash
dtctl get settings --schema builtin:networkzones.zones -o json --plain
```

Each object carries the fields that decide routing behaviour:

```json
{
  "value": {
    "id": "us-east-1.prod.1",
    "fallbackMode": "ANY_ACTIVE_GATE",
    "alternativeZones": []
  }
}
```

### 3. ActiveGate zone assignment

```dql
smartscapeNodes ACTIVEGATE
| filter dt.network_zone.id != "default"
| summarize gates = count(), by: { dt.network_zone.id }
| sort gates desc
```

`dt.network_zone.id` is present on every ActiveGate Smartscape node, so no
classic API call is needed.

Compare this zone list against query 2. A zone that appears here but has no
settings object behind it is an ActiveGate pointed at an undefined zone — report
it, because enforcement will act on that assignment.

### 4. Routing coverage per zone

```dql
smartscapeNodes ACTIVEGATE
| fieldsAdd routing = if(in("AGENT_ROUTING", modules), 1, else: 0)
| summarize { gates = count(), routing_gates = sum(routing) }, by: { dt.network_zone.id }
| sort routing_gates asc
```

`routing_gates`, not `gates`, is the coverage number. Sorting ascending puts the
zones at risk first.

> **Important — `purpose` is not routing capability:** an ActiveGate node exposes
> a `purpose` field that is often `"routing"`, but it is a coarse deployment
> label set independently of which modules are actually installed. A gate
> labelled `routing` can carry only unrelated modules and be unable to route
> OneAgent traffic, and on many tenants gates report no usable `purpose` at all.
> Keying coverage on `purpose` therefore both misses routing-capable gates and
> counts gates that cannot route — in the worst case flagging every zone on a
> tenant as uncovered and burying the real findings in false alarms. Always use
> the `AGENT_ROUTING` entry in `modules`.

> **Important — a zone with no ActiveGates is absent from these results:** this
> query groups over ActiveGates, so a defined zone that has no gates at all
> produces **no row**. When joining query 4 onto query 2, treat a missing zone as
> `routing_gates = 0`, not as unknown or as covered. Those empty zones are
> exactly the ones most likely to be CRITICAL.

### 5. Live ActiveGates per zone

```dql
timeseries cpu = avg(dt.sfm.active_gate.system.cpu_usage),
  by: { dt.network_zone.id, dt.active_gate.id },
  from: now()-7d
| fieldsAdd last_seen = cpu[-1]
| filter isNotNull(last_seen)
| summarize live_gates = count(), by: { dt.network_zone.id }
| sort live_gates desc
```

Query 4 reads Smartscape, which reflects how gates are *configured* and can
include gates that have stopped reporting. This query counts only gates that are
currently connected. The two counts routinely differ, and that is expected — use
query 4 to audit configuration and query 5 to confirm gates are actually up. A
zone that looks covered in query 4 but has no live gates is not covered in
practice.

Group by `dt.active_gate.id`, which is always present and unique per ActiveGate
— not `dt.entity.active_gate`, which is `null` for a gate whose Smartscape
entity has aged out and collapses every such gate into one row. The 7-day window
ensures intermittently reporting gates appear in the series in the first place;
`cpu[-1]` reads the last (possibly null) time bin for each gate, and
`filter isNotNull(last_seen)` then drops any gate that is not currently emitting
the metric — enforcing the "currently connected" contract even across the wider
window. Note: `cpu[-1]` is used rather than `arrayLast(cpu)` because `arrayLast`
skips null elements and would return an older non-null sample for an offline gate,
causing it to pass the filter incorrectly.

## Classifying zones

Join query 4 onto every zone definition from query 2:

1. Build a map of `dt.network_zone.id` → `routing_gates` from query 4.
2. A zone is **covered** if its own `routing_gates > 0`, or if any zone listed in
   its `alternativeZones` has `routing_gates > 0`. Remember that a zone missing
   from the map has `routing_gates = 0`.
3. Assign severity from `fallbackMode` and coverage:

| Severity | Condition | Consequence once enforcement takes effect |
|---|---|---|
| **CRITICAL** | Not covered, `fallbackMode: NONE` | OneAgent traffic dropped |
| **CRITICAL** | Not covered, `ONLY_DEFAULT_ZONE`, and `default` has no routing-capable gate | No route available |
| MEDIUM | Not covered, `ONLY_DEFAULT_ZONE`, `default` is covered | Routes via `default`; network locality lost |
| LOW | Not covered, `ANY_ACTIVE_GATE` | Routes via any gate; network locality lost |
| OK | Covered | Routes as designed |

`fallbackMode` is what decides severity, because it decides what happens to a
OneAgent whose zone has no reachable ActiveGate: `ANY_ACTIVE_GATE` falls back to
any gate, `ONLY_DEFAULT_ZONE` falls back to the `default` zone only, and `NONE`
**drops the traffic**.

Lead the report with CRITICAL zones and name them individually. LOW and MEDIUM
counts are worth reporting in aggregate — they usually mark zones that were
defined and then abandoned — but they do not drop traffic, so they must not
crowd out the CRITICAL list.

> **Important — a non-empty `alternativeZones` is not coverage:** a zone can list
> many alternatives and still be CRITICAL if none of those alternatives has a
> routing-capable ActiveGate of its own. Resolve each alternative against the
> coverage map rather than treating the list's presence as a fallback.

> **Important — OneAgent-side zone assignment is not queryable:**
> `smartscapeNodes HOST` exposes no network-zone field, so which zone a given
> OneAgent will resolve to cannot be read from Smartscape. Per-zone ActiveGate
> coverage is a proxy: it proves a zone *can* serve traffic, not that a specific
> host will route through it. Say so when reporting, and where the customer needs
> a definitive per-host answer, point them at the OneAgent configuration on the
> host itself.

## Examples

### Tenant already enforcing

Query 1 returns `[{"value":{"enabled":true}}]`.

→ Compliant. Phase 3 changes nothing here. Report and stop; queries 2–5 are not
needed.

### Tenant with nothing to enforce

Query 1 returns `[]`, query 2 returns no objects, query 3 returns no rows.

→ Compliant. Nothing becomes load-bearing in Phase 3. Report and stop.

### Tenant with inert definitions

Query 1 returns 404. Query 2 returns three zones:

| id | `fallbackMode` | `alternativeZones` |
|---|---|---|
| `zone-a` | `NONE` | — |
| `zone-b` | `ONLY_DEFAULT_ZONE` | `zone-a` |
| `zone-c` | `ANY_ACTIVE_GATE` | — |

Query 4 returns:

| `dt.network_zone.id` | `gates` | `routing_gates` |
|---|---|---|
| `default` | 12 | 9 |
| `zone-c` | 4 | 0 |

→ Not compliant, and enabling enforcement is **not** safe as-is:

- `zone-a` — **CRITICAL**. Absent from query 4, so `routing_gates = 0`, and
  `fallbackMode: NONE` drops the traffic.
- `zone-b` — MEDIUM. Its only alternative `zone-a` is uncovered, so `zone-b` is
  uncovered too, but `default` is covered and absorbs the traffic with a loss of
  locality.
- `zone-c` — LOW. Has four gates but none routing-capable, so it is uncovered;
  `ANY_ACTIVE_GATE` keeps traffic flowing.

Report `zone-a` as the blocker, and take the customer through Branch B.

## Customer actions

### Quick safety (always do first)

- Confirm write access to `builtin:networkzones` and `builtin:networkzones.zones`.
- Record a baseline: save the query 4 and query 5 results plus a host count, so
  the post-change comparison is meaningful.
- Plan a maintenance window if the tenant carries production traffic — enabling
  enforcement affects OneAgent routing immediately and tenant-wide.

Then pick the branch that matches the customer's intent for the existing zone
definitions.

### Branch A — the definitions are not intended

Delete the zone objects and clear network-zone assignments from ActiveGates.
This is the lower-risk branch: nothing becomes load-bearing in Phase 3 because
nothing is left to enforce. Re-run queries 1–3 to confirm the tenant reaches the
"no zone definitions and no ActiveGate carries a zone" state.

### Branch B — the definitions are intended

Enable enforcement ahead of Phase 3, in this order. The order matters: enabling
first and fixing afterwards means running with dropped traffic in between.

1. Resolve every CRITICAL zone. For each one, either deploy a routing-capable
   ActiveGate into the zone, or add a *covered* zone to its `alternativeZones`,
   or relax `fallbackMode` away from `NONE`.
2. Re-run queries 4 and 5 and re-classify — confirm no zone is still CRITICAL.
3. Set `enabled: true` on `builtin:networkzones`.
4. Work through the verification checklist below.

If the enforcement schema is absent on the tenant, the toggle cannot be enabled
early. Complete steps 1 and 2 anyway — the definitions still become load-bearing
when Phase 3 arrives, and resolving CRITICAL zones is what prevents the outage.

### Verification checklist

- [ ] Query 1 returns `enabled: true`, or queries 2 and 3 both return nothing
- [ ] No zone classifies as CRITICAL
- [ ] Every zone that was covered before the change is still covered
- [ ] No zone dropped to zero `live_gates` after the change
- [ ] Host telemetry is continuous across the change window — no host stopped reporting

### Rollback

Set `enabled: false` on `builtin:networkzones`. Enforcement stops governing
routing and OneAgents fall back to their previous behaviour. Because this is a
single settings object, rollback is fast — which is what makes a maintenance
window a workable safety net.

### References

- [Dynatrace: Network zones](https://docs.dynatrace.com/docs/manage/network-zones)

## Outcome

Report per tenant. First a status line:

| Tenant | Enforcement | Zone definitions | ActiveGates with a zone | Status |
|---|---|---|---|---|
| \<tenant\> | \<enabled / not enabled / schema absent\> | \<count\> | \<count\> | \<Compliant / Action required / Inconclusive\> |

Then, whenever the status is *Action required*, a zone table sorted with CRITICAL
first:

| Zone | `fallbackMode` | routing gates | covered by | Severity |
|---|---|---|---|---|
| \<id\> | \<mode\> | \<count\> | \<own / alternative zone / default / none\> | \<CRITICAL / MEDIUM / LOW / OK\> |

State plainly whether enabling enforcement is safe today: it is safe when no
zone is CRITICAL, and it is not safe otherwise. If any zone is CRITICAL, name
those zones as the blockers and give the specific fix for each from Branch B
step 1.

The migration is complete when query 1 reports `enabled: true` (or queries 2 and
3 return nothing), no zone classifies as CRITICAL, and host telemetry is
continuous across the change.
