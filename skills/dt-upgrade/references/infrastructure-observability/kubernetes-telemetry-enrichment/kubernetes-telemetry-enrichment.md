# Kubernetes Telemetry Enrichment

**Gen3 replacement**: Central settings for enrichment and primary Grail tags

**Phase 2 required**: no

## What changes

Customers can use one central place in Dynatrace to manage which metadata is put on all telemetry across all data sources. The central configuration covers primary tags, domain tags and enrichment of special fields.

For Kubernetes, the legacy per-cluster / per-environment schema `builtin:kubernetes.generic.metadata.enrichment` is replaced by the unified schema `builtin:ingest.enrichment.config`. The customer opts in per scope with the boolean `useIngestEnrichmentConfigSchema` on the legacy object. The opt-in copies the legacy rules to the new schema, but only under the conditions below.

> **If _any_ object already exists in the new schema at a given scope, enabling the opt-in migrates _nothing_ at that scope, not even the rules that have no counterpart. Those rules silently stop enriching within minutes.**

Suppression is **scope-wide, not per-target**. One unrelated new-schema object at environment scope blocks migration of all environment rules. One at cluster scope blocks all of that cluster's rules. Never tell a user to flip the toggle before running the inventory (Step 1).

Reference docs:

- [K8s enrichment migration guide](https://docs.dynatrace.com/docs/ingest-from/setup-on-k8s/guides/metadata-automation/k8s-enrichment-migration)
- [Central enrichment rules](https://docs.dynatrace.com/docs/manage/tags/tags-central-enrichment)
- [Primary Grail fields and tags](https://docs.dynatrace.com/docs/manage/tags/primary-tags)

## Prerequisites

Dynatrace Operator 1.10+, OneAgent 1.333+, ActiveGate 1.343+ (1.345+ for primary Grail tags on edge), Platform 1.345+ for the opt-in. `metadataEnrichment` must be enabled in the DynaKube. Ask the customer to confirm the Operator and ActiveGate versions before starting.

Permissions: `settings:objects:read` and `settings:objects:write`.

## Scope

| Enrichment type | Availability | Covered here |
|---|---|---|
| `K8S_NAMESPACE_LABEL` | GA | Yes |
| `K8S_NAMESPACE_ANNOTATION` | GA | Yes |
| `K8S_WORKLOAD_*`, `K8S_POD_*`, `AWS_TAG`, `GCP_*`, `AZURE_TAG`, `HOST_PROCESS_PROPERTY`, `CUSTOM` | Rolling out or not yet available | No |

The legacy schema only supported namespace labels and annotations, so a migration never needs the other types. Mention them only to answer "what else can I do on the new schema?"

## Customer actions

- Recreate K8s telemetry enrichment rules in the new schema, cluster by cluster, assisted by the forward migration (the opt-in).
- Reconcile the scopes where the opt-in would migrate nothing (Steps 2 and 3).
- Verify enrichment on metric dimensions after each flip (Step 4).

## Schema reference

| | Legacy | New |
|---|---|---|
| Schema ID | `builtin:kubernetes.generic.metadata.enrichment` | `builtin:ingest.enrichment.config` |
| Objects per scope | 1 (`multiObject: false`) | up to 50 (`multiObject: true`, `ordered: true`) |
| Shape | one object holding a `rules[]` array | one object **per rule** |
| Allowed scopes | `KUBERNETES_CLUSTER`, `environment` | `KUBERNETES_CLUSTER`, `environment`, `HOST`, `HOST_GROUP`, `AWS_ACCOUNT`, `AZURE_..._SUBSCRIPTIONS`, `GCP_PROJECT` |
| Opt-in flag | `useIngestEnrichmentConfigSchema` (boolean, on the legacy object) | n/a |
| Inheritance | cluster rules **override** environment rules | cluster rules **merge** with environment rules |

Legacy rule fields: `source`, `type` (`LABEL` or `ANNOTATION`), and either `target` (only `dt.security_context`, `dt.cost.product`, `dt.cost.costcenter`) or `primaryGrailTag: true`.

New rule fields: `type` (enum), `valueSource`, `target`, optional `condition` (DQL matcher), optional `valueExtraction` (DPL, `HOST_PROCESS_PROPERTY` only).

**The opt-in toggle only gates auto-copy, not read or merge.** New-schema objects at any scope are always live and merged into resolution the moment they exist, independent of that scope's toggle and of any other scope's toggle. Opting in a single cluster ahead of its environment is therefore riskier than it looks: the cluster starts merging with whatever new-schema objects already exist at environment scope, even if the environment's own toggle is still off.

## Approach

The end state is always the same: the environment scope **and** every Kubernetes cluster scope are governed by the new schema. There is no partial end state to aim for.

1. Inventory first (Step 1), then pick the strategy that changes the least actual enrichment behavior, not the one that is fastest to type.
2. Write the plan down (which scopes, what is hand-authored, in what order, what the customer will see change) before applying anything.
3. Get explicit confirmation on the plan before any write.

Steps 1 to 4 are the execution path. The precedence reference and rollback sections are consulted only when a conflict needs explaining or something must be undone. Do not run rollback just because it comes next in the file.

## Step 1: Inventory every scope

Read both schemas with no `--scope` filter, so nothing is missed.

```dtctl
dtctl get settings --schema builtin:kubernetes.generic.metadata.enrichment -o json
```

```dtctl
dtctl get settings --schema builtin:ingest.enrichment.config -o json
```

A **list** query never returns `scope` per item: the field comes back empty for every object. This is Settings API behavior, not a dtctl bug. A single-object GET returns the populated `scope`. Resolve scope per object:

```dtctl
dtctl get settings <objectId> -o json
```

Resolve cluster IDs to names:

```dql
fetch dt.entity.kubernetes_cluster
| fields id, entity.name
```

Watch for **stale scopes**: legacy objects can exist for clusters no longer in topology. Report them; do not silently migrate or delete them.

**Cluster scopes with no legacy object of their own inherit the environment scope's legacy object wholesale, toggle included.** A cluster needs its own opt-in decision only if it has its own legacy object. Note this per cluster so Step 2 does not propose flipping, or hand-authoring for, clusters that already inherit.

### Producing the inventory table

Before a scope earns a row, check it against both:

- `dt.entity.kubernetes_cluster`: is the cluster still in current topology?
- `builtin:cloud.kubernetes`: is its cluster connection `enabled: true`?

```dtctl
dtctl get settings --schema builtin:cloud.kubernetes -o json
```

Only **active scopes that have their own legacy object** go in the main table. Everything else (inherits environment, disabled cluster connection, or a legacy object for a cluster absent from both topology and connections) is listed below the table under **Disabled or removed entities, not impacted by this enrichment migration**, one line each.

| Scope | Old-schema rules | New-schema rules | Toggle | Migration path | Notes |
|---|---|---|---|---|---|

- **Old-schema rules**: count of `rules[]` in the legacy object. Note primary-tag rules inline, e.g. "3 (2 primary-tag)".
- **New-schema rules**: object count in `builtin:ingest.enrichment.config` at that scope.
- **Toggle**: `useIngestEnrichmentConfigSchema` on the legacy object.
- **Migration path**: derived mechanically from the new-schema count. **0** is Auto-migration ready. **1 or more** is Manual migration, with a sub-state: **reconciled** (every old rule's expected target is already in the new schema, so the flip is a harmless no-op) or **action needed** (at least one Missing or Partial row in the per-scope detail). Never show a bare "Manual migration" label.
- **Notes**: what is covered or missing, blockers, collisions and how they were resolved.

### Per-scope rule-level detail (Manual migration scopes only)

For every Manual migration scope, add a table under the main table:

| Old-schema rule | Expected new rules | Existing new rules | Status |
|---|---|---|---|

Match old rules to new objects by **normalized target**:

- Plain rule (`target: T`): expect one new object with `target: T`.
- `primaryGrailTag: true` rule (`source: X`): expect **two** objects, `k8s.namespace.<label|annotation>.<x>` and `primary_tags.<x>` (lowercased).

Status per row:

- **Reconciled**: all expected targets present.
- **Partial**: some but not all expected targets present (only possible for a primary-tag rule's two-object split).
- **Missing**: none of the expected targets present.
- **Extra**: a new-schema object that no old rule maps to. Surface it here; Step 2 asks why it exists.

Do not collapse a moved target into one "changed" row. If an old rule's source no longer matches a new object's `valueSource` for the same target, report it as both Missing and Extra. Whether that was deliberate is Step 2's judgment call.

**Re-read both schemas before acting if any time has passed** since building the table. New-schema objects can appear between reads and flip a scope from Auto-migration ready to Manual migration.

For more than 20 scopes, show only the lifted-out list, a one-line summary (total / Auto-migration ready / Manual migration action needed / Manual migration reconciled), and the names of the action-needed scopes. Offer the full table on request.

## Step 2: Classify each scope

| New-schema objects at the scope | What the toggle does | Customer action |
|---|---|---|
| **0** | Auto-migrates: every legacy rule is copied unmodified. `primaryGrailTag: true` becomes **two** objects. | Flip the toggle. Verify. Nothing to hand-author. |
| **1 or more** | **Nothing migrates.** Setup stays as-is; uncovered legacy rules stop applying. | Do not default to working around it. Ask why. |

Classify scopes independently: the environment can be blocked while a cluster is clean, and the reverse. Opting in and out repeatedly for the same scope does not create duplicate rules. Scopes with no legacy object of their own need no classification.

### Blocked scopes: resolve the conflict, do not paper over it

A pre-existing new-schema object is a signal, not just an obstacle. Before hand-authoring a parallel object, find out why it exists:

- If it was added deliberately (for example the customer repointed `dt.cost.product` to a different source), the right move may be to **adopt** it and backfill only the legacy rules that are still missing. This usually needs the customer's input. It is different from a stale scope: a stale scope is dead, a blocked scope's existing object usually is the customer's ongoing intent.
- Only after confirming the existing object should stay does hand-authoring the rest (Step 3) make sense.

**Hand-author the missing objects before flipping the toggle**, not after. Flipping first creates a window of minutes where enrichment is absent.

## Step 3: Hand-author the missing rules

This step assumes Step 2 concluded that every legacy rule is preserved unchanged. If the customer adopted a pre-existing object, hand-author only the legacy rules still missing.

| Legacy rule | New-schema object(s) |
|---|---|
| `type: LABEL`, `source: X`, `target: T` | 1 object: `type: K8S_NAMESPACE_LABEL`, `valueSource: X`, `target: T` |
| `type: ANNOTATION`, `source: X`, `target: T` | 1 object: `type: K8S_NAMESPACE_ANNOTATION`, `valueSource: X`, `target: T` |
| `type: ANNOTATION`, `source: X`, `primaryGrailTag: true` | **2 objects**: `target: k8s.namespace.annotation.X` and `target: primary_tags.X`, both `type: K8S_NAMESPACE_ANNOTATION`, `valueSource: X` |
| `type: LABEL`, `source: X`, `primaryGrailTag: true` | **2 objects**: `target: k8s.namespace.label.X` and `target: primary_tags.X`, both `type: K8S_NAMESPACE_LABEL`, `valueSource: X` |

`primary_tags.<key>` is lowercased in auto-migration output (legacy source `Asdf` becomes `primary_tags.asdf`).

Count the objects before starting: _n_ plain rules plus 2 for each `primaryGrailTag` rule. A 6-rule legacy object with two primary-tag rules needs **8** new objects.

### Validator constraints that will reject your objects

The static schema advertises `target` as free text up to 350 characters. A runtime validator overrides that:

> Target must be `dt.security_context`, `dt.cost.costcenter`, `dt.cost.product`, a key prefixed with `primary_tags.`, or the value source prefixed with `k8s.namespace.annotation.` for type `K8S_NAMESPACE_ANNOTATION`.

- **No custom targets.** Only the three fixed dimensions, `primary_tags.*`, or the pass-through form.
- **Pass-through targets are bound 1:1 to their own `valueSource`.** The target must equal `k8s.namespace.annotation.<that object's own valueSource>`. You cannot repoint a pass-through target at another source, and two pass-through objects cannot share one target string.
- **`condition` is not supported** for `K8S_NAMESPACE_LABEL` and `K8S_NAMESPACE_ANNOTATION` (`"Condition is not supported for type ..."`).
- **Uniqueness** is enforced on the tuple (`type`, `valueSource`, `valueExtraction`, `target`, `condition`).

### Writing the objects

Derive the file format from an existing object dump rather than assuming it: run `dtctl create settings --help`, then mirror the `schemaId` / `scope` / `value` shape returned by Step 1. Preview first, then create:

```dtctl
dtctl create settings -f <file> --dry-run
```

```dtctl
dtctl create settings -f <file>
```

Re-read after every write:

```dtctl
dtctl get settings --schema builtin:ingest.enrichment.config --scope <scope> -o json
```

### Then flip the toggle

Read the legacy object, set `useIngestEnrichmentConfigSchema: true` in a copy of it, and apply that copy. Re-read to confirm the `rules` array is unchanged: only the flag should differ.

```dtctl
dtctl get settings <objectId> -o yaml
```

```dtctl
dtctl apply -f <edited-legacy-object-file>
```

## Step 4: Verify

Enrichment surfaces as **metric dimensions**. This is the reliable check even on tenants with no log ingest.

```dql
timeseries c = sum(dt.kubernetes.workload.pods_desired),
  by: {k8s.cluster.name, k8s.namespace.name, k8s.workload.name, dt.cost.product, dt.cost.costcenter, dt.security_context},
  from: now()-1h
```

For pass-through and primary-tag targets, add the field to `by:{}` with backticks:

```dql-snippet
by: {`k8s.namespace.annotation.team`, `primary_tags.team`}
```

Read namespace labels and annotations for one cluster:

```dql-template
fetch dt.entity.cloud_application_namespace
| filter clustered_by[dt.entity.kubernetes_cluster] == "<CLUSTER_ID>"
| fields entity.name, kubernetesAnnotations, cloudApplicationLabels
```

### Timing

- Rules take effect within a few minutes. Changes affecting Kubernetes workloads can take **up to 15 minutes** to propagate, and affected pods may need to restart.
- In practice, rule creation and toggle cutover land in about 3 to 4 minutes, and object add or remove re-resolution in about 1 to 2 minutes.
- **Poll for the full 15 minutes before concluding a rule did not take effect.**

### Confounders: exclude these before blaming the migration

Namespaces and workloads can carry **direct** `metadata.dynatrace.com/<field>` annotations (for example `metadata.dynatrace.com/dt.security_context`). These populate the same dimensions through an independent mechanism, are unaffected by either schema, and survive migration. Before reporting a dimension as working or broken, check whether the namespace or workload sets it directly:

```dql
fetch dt.entity.cloud_application_namespace
| fields entity.name, kubernetesAnnotations
| filter contains(toString(kubernetesAnnotations), "metadata.dynatrace.com")
```

Second confounder: a rule whose `source` key is not present on any live namespace produces nothing. That is not a migration failure. Confirm the key exists on at least one namespace before treating a null dimension as a problem.

## Precedence reference

Not a sequential step. Read this when Step 2 or 3 surfaces two rules aimed at the same target, or when a customer asks why a value is not the one they expect.

1. **Within a scope:** for each target, the first rule _in list order_ wins. List order often matches creation order, but that is not the same as creation order deciding precedence. The Settings API supports explicit reordering (`insertAfter` / `insertBefore` on write) and the UI can reorder too. Check the current order before reasoning about precedence; do not infer it from creation timestamps.
2. Precedence is **re-evaluated dynamically** on add or remove. Deleting the winning object promotes the next one within about 1 to 2 minutes.
3. **Cluster scope beats environment scope** for a shared target, regardless of which schema generation produced either rule. Inheritance (what happens when a cluster leaves a target uncovered) is new-schema behavior only: an uncovered cluster-scope target falls through to the environment rule. The legacy schema never did this, since a legacy cluster object fully overrode the environment.
4. **Environment rules apply** for a target left uncovered at cluster scope.

Practical reading of the override-to-merge change: **cluster wins on overlap, environment fills the gaps.** A customer who relied on a cluster object shadowing the whole environment config will start seeing environment rules appear for targets the cluster object does not cover.

## Rollback

Run this only if verification (Step 4) found a problem, or the customer asks to revert. A clean Step 4 ends the work.

1. Set `useIngestEnrichmentConfigSchema: false` on the legacy object. Migration copies rather than modifies, so the legacy rules are intact.
2. **Toggle off only; leave the new-schema objects you created.** They are the evidence for debugging, and the legacy rules keep working with the toggle off regardless of what else exists in the new schema.
3. Delete the created new-schema objects only for a deliberate full revert, and confirm which ones against the Step 1 inventory first. Never delete anything that pre-dated the migration.
4. **Toggling off is not enough if the legacy object itself was created as part of the work.** A scope that had no legacy object before needs the object deleted, not just flipped.
5. Diff against the Step 1 inventory by `objectId` and `value`. Report any delta; do not report success without the diff.

## Scenario matrix

| Legacy rules at scope | New-schema objects at scope | Toggle flip result |
|---|---|---|
| 1 or more | 0 | All rules copied; `primaryGrailTag` becomes 2 objects |
| 1 or more | 1 or more, colliding on a target | **Nothing migrates.** The new object wins that target; uncovered legacy rules stop |
| 1 or more | 1 or more, on an unrelated target | **Nothing migrates.** Suppression is scope-wide, not per-target |
| 0 | any | Nothing to migrate |
| Same target at cluster and environment | n/a | Cluster wins |
| Target only at environment | n/a | Environment applies |

Primary Grail tag **runtime rendering** depends on hosts or processes existing (primary tags are counted per host or process). The migration behavior, the two-object split, is documented. If primary tags do not appear after a correct migration, that is a runtime question for the primary tags doc, not a migration defect.

## Fleet-scale workflow

For tenants with many cluster scopes, do not run Steps 1 to 4 from a blank slate per scope.

### Fleet status summary

Classify every cluster without inspecting each one:

```dtctl
dtctl get settings --schema builtin:cloud.kubernetes -o json
```

```dtctl
dtctl get settings --schema builtin:kubernetes.generic.metadata.enrichment -o json
```

Every cluster scope present in the first list (configured connections) but absent from the second (explicit legacy objects) has no legacy object of its own. It inherits the environment's toggle and rules and needs nothing.

For the clusters that do have their own legacy object, **check the toggle before classifying**. `Toggle: true` means the scope already went through this migration: mark it **Already migrated** and move on. This is a free read from the same list query, and it keeps the summary cheap to re-run mid-rollout. If an Already migrated scope later looks broken, that is a Step 4 question, not a reason to re-triage it.

Classify only the `Toggle: false` clusters per Step 2, and the environment scope the same way (it drives every inheriting cluster). Cross-check `enabled` on `builtin:cloud.kubernetes` and current topology, and lift out disabled or stale clusters as in Step 1. Use the Step 1 columns with **Already migrated** as an additional Migration path value.

### Choose a mode per scope, not one for the whole fleet

- **Bulk mode:** every Auto-migration ready scope is a mechanical toggle flip. Confirm the full list with the customer once, then flip and verify each per Step 4. Do not ask per-scope confirmation for 40 identical scopes.
- **Deep-dive mode:** every Manual migration scope gets Steps 1 to 3 individually. These are the cases the "ask why" guidance is for. Do not batch or template them.
- **Accept-the-loss fast path:** the customer may decide a blocked or inheriting scope is not worth reconciling. Flipping without hand-authoring is legitimate, but it must be **surfaced and confirmed as a deliberate decision**, never the silent result of skipping Step 3. State which rules will stop applying first.

Migrating the environment scope first resolves every inheriting cluster in the same step. Check the fleet summary for how many clusters that covers before choosing where to start.

For a cluster-by-cluster rollout, two things to watch:

- A cluster with no configuration of its own needs a **brand-new legacy object** to get its own on/off switch. To undo that later, delete the object; turning it off is not enough.
- A migrated cluster should fall back to the environment's rules for anything it does not define, but this is only confirmed when the environment is also migrated. If the environment is still on the old schema, check in Step 4 that the fallback works before rolling out further. Test on one low-risk cluster first.

### Per-cluster effective-ruleset report

When asked "what will actually apply to this cluster once everything is on the new schema", do not list only the cluster's own rules. Report three columns per target:

| Target | Cluster-origin rule | Environment-origin rule | Effective (merged) value |
|---|---|---|---|

- **Cluster-origin**: from that cluster's own new-schema objects (post-migration or hand-authored).
- **Environment-origin**: from the environment's new-schema objects, checked **regardless of the environment's own toggle**, since new-schema objects are read unconditionally once they exist.
- **Effective**: cluster wins where both exist, otherwise the environment's value, otherwise nothing.

This report only makes sense once both scopes are on the new schema, or when projecting what they will look like after migration. For a still-legacy scope, use the Step 1 inventory.

## Tracking progress

Progress is the share of legacy objects with the opt-in set.

```dtctl
dtctl get settings --schema builtin:kubernetes.generic.metadata.enrichment -o json
```

Count objects with `useIngestEnrichmentConfigSchema: true` against the total, then add clusters without their own legacy object (they follow the environment). Compare with the configured connections:

```dtctl
dtctl get settings --schema builtin:cloud.kubernetes -o json
```
