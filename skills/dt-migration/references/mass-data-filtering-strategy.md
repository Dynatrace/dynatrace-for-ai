# Mass Data Filtering Strategy

Covers **Situations 1 and 2** from the Query Purpose Classification in SKILL.md: migrating DQL queries where entities serve only as a filter on mass data (timeseries, logs, metrics). For pure entity list queries (Situation 3), return to SKILL.md.

## Step 1 — Resolve the filter conditions

### A. Tag-based filter — `tag(X)` or `matchesValue(tags, "X")`

> **Tag origins:** Tags in Dynatrace have three possible sources:
>
> 1. **Rule-based** — created via auto-tagging rules (`builtin:tags.auto-tagging`).
 > 2. **Imported** — automatically applied from cloud providers (e.g., AWS tags, Azure tags, GCP labels) or other integrations. Imported tags are recognizable by a bracketed prefix in their key, e.g. `[AWS]Name`, `[Environment]Stage`.
> 3. **Manually applied** — added by users through the UI or the Dynatrace API.
>
> Only **rule-based tags** can be migrated by inspecting the tagging rule configuration as described below. For imported or manually applied tags there is no declarative rule to resolve; you must identify the underlying entity attribute or condition that the tag represents and use that directly as the filter (treat as Step 1B). However, the values behind imported or manually applied tags may still be available as enriched dimensions on the mass data — the field discovery in Step 2 still applies and should be executed to check for a direct match.

Fetch the tagging rule config:

```dtctl
dtctl get settings --schema builtin:tags.auto-tagging -o json
```

Find the entry where `value.name` matches the tag key. Rules within a tag have OR semantics; conditions within a rule have AND semantics. If a condition key ends with `_TAG`, recursively resolve that tag's rule.

**Propagation flags:** `pgToHostPropagation`, `pgToServicePropagation`, `serviceToHostPropagation` mean the tag applies to a different entity type than the rule's `entityType`. Note which entity type the conditions actually describe — this drives approach selection in Step 3.

**key:value tags:** Inspect `valueFormat` for placeholders like `{Host:Kubernetes:label//key}`. If the value comes from a K8s label, `k8s.workload.name` is often a simpler discriminator.

Map condition keys to semantic fields via [auto-tagging-field-mapping.md](auto-tagging-field-mapping.md). Resolve `*_TAG` conditions recursively.

### B. Explicit attribute filter — non-tag `classicEntitySelector` predicates

The conditions are already explicit in the selector string. Parse each predicate using [entity-selector-predicates.md](entity-selector-predicates.md) and map to its semantic field using the table below.

| `classicEntitySelector` predicate | Entity type | Semantic field (mass data / smartscape node) |
|---|---|---|
| `entityName(X)` | any | `name` on smartscape node; `entity.name` on `fetch dt.entity.*` |
| `entityId(X)` | any | `id_classic` on smartscape node; `id` on `fetch dt.entity.*` |
| `hostGroupName(X)` | HOST | `host.group.name` on HOST node (`getNodeField` or smartscapeNodes) |
| `hostGroupId(X)` | HOST | `dt.host_group.id` (enriched) or `dt.entity.host_group` (entity id) |
| `serviceTechnologyTypes(X)` | SERVICE | no enriched field; use `service.technology` on SERVICE smartscape node |
| `serviceType(X)` | SERVICE | no enriched field; use `service.type` on SERVICE smartscape node |
| `databaseName(X)` | SERVICE | `db.namespace` (enriched on spans/metrics) |
| `toEntityId(X)` | any | `id_classic` on smartscape node |
| `k8sNamespaceName(X)` | CLOUD_APPLICATION / K8S_NAMESPACE | `k8s.namespace.name` (enriched) |
| `k8sWorkloadName(X)` | CLOUD_APPLICATION | `k8s.workload.name` (enriched) |
| `k8sClusterName(X)` | K8S_CLUSTER | `k8s.cluster.name` (enriched) |
| `awsRegion(X)` | AWS_* | `aws.region` (enriched) |
| `managementZone(X)` | any | **Not migratable** — management zones are access-control constructs in Grail. Rewrite using the underlying entity conditions directly. |

---

## Step 2 — Discover available fields (MANDATORY — execute before proceeding)

**STOP. Execute the commands below now.** The outputs determine which approach is viable. Do not proceed to Step 3 without these results.

### 2a. Inspect the mass data source

Run `fieldsSnapshot` on the data source from the original query to discover enriched dimensions:

```dtctl
dtctl query 'fieldsSnapshot metrics, by:{metric.key} | filter metric.key == "<the_metric>" | fields field'
```

```dtctl
dtctl query 'fieldsSnapshot logs, by:{dt.system.bucket} | filter matchesValue(dt.system.bucket, "<the_bucket>") | fields field'
```

**Record from the output:**

1. Which enriched dimensions match the resolved conditions from Step 1 (e.g., `k8s.namespace.name`, `host.name`)
2. Whether a `dt.smartscape.*` dimension exists for the relevant entity type (e.g., `dt.smartscape.host`)
3. Whether a `dt.entity.*` dimension exists (e.g., `dt.entity.host`)

### 2b. Inspect the smartscape node type

Run `fieldsSnapshot` on the smartscape node type that matches the entity type from Step 1:

```dtctl
dtctl query 'fieldsSnapshot smartscape.nodes, by:{node.type} | filter node.type == "<TYPE>" | fields field'
```

**Record from the output:** which node attributes match the resolved conditions (e.g., `host.group.name`, `service.technology`).

---

## Step 3 — Select the approach

Use the discovery outputs from Step 2 to select the first matching approach. Follow this order strictly.

### Check 1 → Direct dimension filter

**Condition:** Step 2a shows the resolved condition is available as an enriched dimension on the mass data.

```dql
timeseries avg(dt.host.cpu.idle), filter:k8s.namespace.name == "my-ns" AND k8s.workload.name == "my-app"
```

This is the simplest and most performant path. Use it whenever possible.

### Check 2 → getNodeField (same-node smartscape filter)

**Condition:** Step 2a shows a `dt.smartscape.*` dimension exists, **and** Step 2b shows the condition attribute is available on that node type, **but** the attribute is not an enriched dimension on the mass data.

```dql
timeseries avg(dt.host.cpu.idle), filter:getNodeField(dt.smartscape.host, "host.group.name") == "my-group"
```

Multiple conditions on the same node:

```dql
timeseries avg(dt.host.cpu.idle), filter:getNodeField(dt.smartscape.host, "host.group.name") == "my-group" AND getNodeField(dt.smartscape.host, "cloud.provider") == "aws"
```

### Check 3 → in [smartscapeNodes] subquery (cross-node filter)

**Condition:** The condition targets a **different** node type than the data's smartscape dimension, or neither Check 1 nor Check 2 applies.

With `dt.smartscape.*` — project `id`:

```dql
timeseries avg(dt.host.cpu.idle), filter:dt.smartscape.host in [smartscapeNodes "PROCESS" | filter name == "Cassandra" | traverse edgeTypes: {runs_on}, targetTypes: {HOST}, direction: forward | fields id]
```

Pattern: start at the node type that carries the condition -> filter -> traverse to target node type.

## Step 4 — Verify equivalence (MANDATORY — execute before delivering)

**STOP. Execute the commands below now.** Do not deliver the migrated query without verification evidence.

### 4a. Output shape check

Compare the columns/fields between the original and migrated query. They must match. If you renamed fields (e.g., `entity.name` -> `name`), alias them back to the original names.

### 4b. Probe run

Validate syntax, then run the migrated query with a short timeframe:

```dtctl
dtctl verify query '<migrated_query>'
```

```dtctl
dtctl query '<migrated_query>'
```

Check:

- **Non-empty results:** The query returns data. Zero rows when the original would return data means the approach selection or field mapping is wrong — go back to Step 2.
- **Plausible values:** Spot-check that metric values, entity names, and row counts are reasonable.

If the original query can still execute (deprecated constructs may still work temporarily), run both side-by-side and compare row counts and a sample of values.

### 4c. Document deviations

If exact equivalence is not achievable, add a leading comment:

```
/* Migration note: <what differs and why> */
```

---

## Critical constraints

| Constraint | Detail |
|---|---|
| `PROCESS_GROUP` node type does not exist | Only `PROCESS` is available in smartscapeNodes. Substituting may over-select. |
| Nested array fields | e.g. `process.software_technologies[].type` — cannot be filtered in smartscapeNodes expressions. |
| `dt.smartscape.*` vs `dt.entity.*` | Check 2 requires `dt.smartscape.*`. Check 3 works with both (`id` for smartscape, `id_classic` for entity). |
| `fetch dt.entity.*` has no Grail tags | Rule-based tags are not present on smartscape nodes. Always resolve to underlying conditions (Step 1A). |
| `managementZone(X)` is not migratable | Management zones are access-control constructs; no equivalent attribute exists. |

---

## Checklist (condensed)

Use this as a sequential checklist. Each step has a required output.

1. **Classify** — Mass data query (Pattern A) or entity list sub-source (Pattern B)? -> *output: pattern type*
2. **Resolve conditions** — `tag(X)` -> Step 1A (`dtctl get settings`). Explicit predicate -> Step 1B (lookup table). -> *output: list of (entity type, field, value) conditions*
3. **Discover fields** — Execute `dtctl query 'fieldsSnapshot ...'` on the mass data source AND the smartscape node type. -> *output: list of available enriched dimensions and node attributes*
4. **Select approach** — Walk Check 1 -> Check 2 -> Check 3 using the discovery outputs. -> *output: selected approach with rationale*
5. **Write query** — Apply the selected approach. Include the original as a `/* */` trailing comment.
6. **Verify** — Execute `dtctl verify query` then `dtctl query` on the migrated query, confirm non-empty results, check output shape matches original. -> *output: verification evidence (row count, field comparison)*
7. **Deliver** — Return the migrated query with mapping resolution and any open assumptions.

---

## When to abandon

Return the original query with a `/* */` comment explaining the closest approximation if:
- No viable approach exists for the resolved conditions.
- 3+ distinct approaches tried and failed.
- Verification (Step 4) shows non-equivalent results that cannot be reconciled.

```
/* Migration not completed: <reason>. Closest approximation: <what was tried>. */
<original query unchanged>
```
