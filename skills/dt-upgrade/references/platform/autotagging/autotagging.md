# Autotagging

<!-- Jira: none -->

**Gen3 replacement**: Source-side primary tags (`primary_tags.*`) via `DT_TAGS` or `OTEL_RESOURCE_ATTRIBUTES`; central enrichment configuration (`builtin:ingest.enrichment.config`) for rule-based mapping pushed to OneAgent without touching hosts; OpenPipeline enrichment as a last resort

**Phase 2 required**: no

## Contents

- [What changes](#what-changes)
- [Why there is no direct Gen3 equivalent](#why-there-is-no-direct-gen3-equivalent)
- [Assessing your autotagging footprint](#assessing-your-autotagging-footprint)
  - [Never infer a source from a name](#never-infer-a-source-from-a-name)
  - [Tags applied outside auto-tagging rules](#tags-applied-outside-auto-tagging-rules)
- [Migration strategy](#migration-strategy)
  - [Naming convention for primary tag keys](#naming-convention-for-primary-tag-keys)
  - [Option A — OneAgent enrichment](#option-a--oneagent-enrichment)
  - [Option B — OpenTelemetry resource attributes](#option-b--opentelemetry-resource-attributes)
  - [Option C — Central enrichment configuration](#option-c--central-enrichment-configuration)
  - [Option D — OpenPipeline primary Grail tag rules (last resort)](#option-d--openpipeline-primary-grail-tag-rules-last-resort)
  - [Extensions telemetry](#extensions-telemetry)
  - [RUM telemetry](#rum-telemetry)
  - [Kubernetes telemetry](#kubernetes-telemetry)
  - [Cloud connection telemetry](#cloud-connection-telemetry)
  - [Synthetic telemetry](#synthetic-telemetry)
  - [Precedence](#precedence)
- [Customer actions](#customer-actions)
- [Tracking queries](#tracking-queries)
- [Related references](#related-references)
- [Documentation](#documentation)

## What changes

Classic Dynatrace auto-tagging (`builtin:tags.auto-tagging`) is a server-side rule engine that evaluates conditions against the Smartscape entity model after data arrives and stamps matching entities with tags. Those tags are then referenced by management zones and by classic dashboards and entity/problem selectors to scope their views. **Alerting profiles are scoped by management zone, not by tag** — `problemSelector` does expose `entityTags(...)` alongside `managementZoneIds(...)`, so a *selector* can filter by tag independently of any zone, but a profile's own scope is a management zone. Do not plan an alerting-profile migration around tag criteria; see [alerting-and-problem-notifications.md](../alerting-and-problem-notifications/alerting-and-problem-notifications.md).

In Gen3 (Grail), entity-based post-ingest enrichment does not exist at scale. Tags must be present on the data **at ingest time** so that Grail pipelines can route records, assign buckets, and evaluate access control without performing on-read joins. Auto-tagging rules will be removed in Phase 3.

## Why there is no direct Gen3 equivalent

Auto-tagging stamps tags on **entities** (Smartscape nodes — services, hosts, process groups). Grail does not resolve entity relationships at query time: all filtering, routing, and access control operates on fields already present on each signal record. A tag produced after ingestion cannot influence routing or bucket assignment for records that have already arrived.

The replacement is to push the same discriminating information — team name, application, environment stage — onto the data at the source, before telemetry reaches Dynatrace. Once those values are present as `primary_tags.*` fields on every log line, metric data point, and trace span, Segments, IAM policies, and bucket routing rules can use them directly without any entity-model traversal.

The **nearest conceptual analog** to classic auto-tagging is [central enrichment configuration](#option-c--central-enrichment-configuration) (Option C): like auto-tagging, it is a central, server-side rule engine (condition → tag), but it runs at OneAgent enrichment time — before ingest — and produces `primary_tags.*` that flow onto every signal, instead of stamping Smartscape entities after ingest. Rules that matched on host groups, host tags, or a host-name naming convention often migrate to it almost 1:1.

## Assessing your autotagging footprint

Export the auto-tagging settings from your tenant:

```bash
dtctl get settings --schema "builtin:tags.auto-tagging" -o json > tenant.builtin_tags.auto-tagging.json
```

Or from the UI: **Settings → Auto-tagging → Export**.

The export file (`*.builtin_tags.auto-tagging.json`) is a JSON array. Each element has this structure:

```json
{
  "objectId": "<stable-uid>",
  "schemaId": "builtin:tags.auto-tagging",
  "value": {
    "name": "<rule name>",
    "rules": [ ... ]
  }
}
```

`value.name` is the rule name — the string that appears in management zone conditions, either as the whole tag value (plain-name tags like `Synthetic`) or as the key before the `:` in key-value tags (e.g. `keptn_project:sockshop` → rule name is `keptn_project`).

**Key numbers to establish before migrating:**

- **Total rules** — how many auto-tagging rules exist on the tenant
- **Rules used in MZ conditions** — cross-reference tag values in MZ `_TAGS` conditions against the rule name list (see [mz-export-schema.md](../management-zones/mz-export-schema.md) for how MZ conditions reference tags)
- **Rules not referenced by any MZ** — candidates for early deprecation; no MZ dependency to break

Cloud-origin tags (`[AWS]...`, `[GCP]...`, `[Azure]...`) appearing in MZ conditions are not auto-tagging rules — they are propagated from cloud provider metadata and need no migration entry.

**Map out the target primary tag keys.** The footprint is not just a count — the goal is to produce a concrete mapping of the new `primary_tags.*` keys the environment will need. For each load-bearing auto-tag rule (those referenced by MZ conditions), decide:

- The **target `primary_tags.*` key** it becomes, following the [naming convention for primary tag keys](#naming-convention-for-primary-tag-keys) below (normalise to `snake_case`, collapse plain-name tag families into a single key with multiple values).
- Whether the value is already covered by a **built-in primary Grail field** (`k8s.cluster.name`, `aws.account.id`, `dt.host_group.id`, …) — if so, no new tag is needed; downstream filters use the Grail field directly. See [auto-tagging-field-mapping.md](../entity-queries/auto-tagging-field-mapping.md) for the auto-tag condition-key → built-in Grail/semantic field lookup.
- The **source of the value** at the workload (a cloud tag, K8s label, process/host property) that will feed the enrichment.
- The **originating signal/workload type**, which decides the delivery path: host/process telemetry uses the A–D hierarchy, while Kubernetes, RUM, and extension-collected telemetry follow their dedicated subsections below.

The result is a mapping table — classic auto-tag rule → target primary tag key (or built-in field) → value source — that becomes the direct input to the migration strategy below. Each target key is then delivered through one of the enrichment options.

### Never infer a source from a name

A rule name, tag key, or property name tells you **nothing** about where its value comes from. Resolve every mapping from the rule's actual `conditions` and `valueFormat` in the export, never from what the name suggests.

- **`Cluster` is not `k8s.cluster.name`.** It is just as likely a WebSphere, database, failover, or HA cluster, or a customer-specific concept. Only a rule that demonstrably reads Kubernetes cluster metadata maps to `k8s.cluster.name`.
- **`Namespace` is not `k8s.namespace.name`.** It may be an application, messaging, or naming-scheme namespace.
- **`Environment` is ambiguous three ways** — a deployment stage, a Dynatrace environment (tenant), or, inside a classic placeholder like `{Host:Environment:<key>}`, *host custom metadata*, which has nothing to do with either.
- The same goes for `Application`, `Stage`, `Service`, `Region`, `Node`, and `Zone`.

Mapping a rule to a built-in primary Grail field on the strength of its name silently produces an empty or wrong tag: the classic rule keeps working until Phase 3, while the Gen3 filter that replaced it quietly matches nothing.

**When the export does not settle it, do not guess.** If the condition or placeholder does not identify the underlying attribute, and neither this file nor the tenant confirms it, record the rule as unresolved and ask the customer what the value means. An unmapped rule that is flagged is recoverable; a confidently wrong mapping is not.

### Tags applied outside auto-tagging rules

The `builtin:tags.auto-tagging` export only shows rule-based tags. Many customers also run **scheduled scripts or automations** that write manual tags through the Tags API (`POST /api/v2/tags`), usually to do what auto-tagging cannot: copy a tag across an entity relationship, or split one name or ID into several tags. These tags are just as load-bearing for management zones and alerting, but they never appear in the export, so a footprint built from the export alone misses them.

**Detect them.** List the tag keys actually present on the entity types in scope and compare them against the `value.name` list from the export. Any key with no matching rule (and that is not a cloud-origin `[AWS]`/`[Azure]`/`[GCP]` tag) was applied some other way — ask the customer what sets it.

```dql-template
fetch dt.entity.<entity_type>
| expand tag = tags
| fieldsAdd tagKey = splitString(tag, ":")[0]
| summarize entities = count(), by: {tagKey}
| sort entities desc
```

**Classify each script job by what it does, not by the tag name**, then route it:

| Script pattern | Gen3 path |
|---|---|
| **Relationship propagation** — copy ownership tags from a calling service onto the database, cache, or queue it calls, or from a host/process onto a related entity | No equivalent: Grail does not traverse entity relationships. Spans the calling process records (including its database and cache calls) already carry that process's `primary_tags.*`, so first ask what still consumes the tag on the downstream entity. If ownership of the downstream data itself is required, tag it at its own source. |
| **Extension entities inheriting tags** from the host, process, or service they relate to | [Extensions telemetry](#extensions-telemetry) — set primary tags on the monitoring configuration (per endpoint where targets differ). Local extensions already inherit host-level tags. |
| **Parsing Kubernetes names** — cluster name → site/stage, namespace name `<product>-<stage>` → two tags, workload label → application | Check the built-in `k8s.cluster.name` / `k8s.namespace.name` primary fields first. Kubernetes ingest enrichment rules have no DPL extraction, so values encoded in a name need dedicated `metadata.dynatrace.com` annotations or DynaKube resource attributes ([Kubernetes telemetry](#kubernetes-telemetry)). Labels or annotations that already carry the value map directly with a namespace, workload, or pod label/annotation rule. |
| **Parsing cloud resource IDs or properties** — subscription, resource group, region, SKU | Use the built-in cloud fields where they exist; otherwise [Option D](#option-d--openpipeline-primary-grail-tag-rules-last-resort). |
| **Cleaning up values** — splitting a comma-separated tag value into several tags | Fix the value at the source; do not reproduce the cleanup in a pipeline. |
| **Alert-scoping or exclusion tags** — e.g. marking system mount points as excluded from disk alerting | Not a primary tag. Migrate with the owning alerting feature, e.g. [classic-disk-anomaly-detection.md](../../infrastructure-observability/classic-disk-anomaly-detection/classic-disk-anomaly-detection.md). |

The scripts themselves keep running after the upgrade — they write classic entity tags, not `primary_tags.*`, so they do nothing for Grail scoping. Plan to retire each job once its Gen3 path is in place, and do not count a tag as migrated just because the script still applies it.

## Migration strategy

Follow the enrichment hierarchy in order — start with the least invasive option that covers the use case and only move to the next if the previous approach doesn't apply. Central enrichment configuration (Option C) is the closest 1:1 path for auto-tag rules that keyed off host groups, host tags, or host-name naming conventions — no per-workload changes needed. OpenPipeline (Option D) is the last resort for host and process data — but for cloud connection data it is a required second step, not a fallback (see [Cloud connection telemetry](#cloud-connection-telemetry)).

**First, route by where the data originates.** The A–D hierarchy applies to host- and process-based telemetry. Telemetry from **Kubernetes**, **cloud connections**, **RUM**, **Synthetic**, and **extensions** has workload-specific enrichment paths that differ from (or extend) the hierarchy — if the auto-tag rule scoped that kind of data, follow the matching subsection below ([Kubernetes telemetry](#kubernetes-telemetry), [Cloud connection telemetry](#cloud-connection-telemetry), [RUM telemetry](#rum-telemetry), [Synthetic telemetry](#synthetic-telemetry), [Extensions telemetry](#extensions-telemetry)) instead of defaulting to A–D. RUM in particular has no source-side option and needs a DQL processor in a base pipeline.

**The ingest enrichment configuration (Option C) is applied by the component that collects the data, never later.** It does not reach data sent through the ingest APIs, or OTLP data that passes through an OpenTelemetry Collector. For those, set the tag at the source (Option B, `DT_TAGS`) or use Option D.

### Naming convention for primary tag keys

The target key name is the same regardless of which delivery option (A–D) you use. Normalise auto-tag rule names to `snake_case` and prefix with `primary_tags.`:

- `Application Name` → `primary_tags.application_name`
- `Owner` → `primary_tags.owner`
- `Team` → `primary_tags.team`

The **resulting field** is always the full `primary_tags.*` name, but how you type it differs per option: Options A, B and D take what you write literally (A–B need the full key, D takes the suffix only), while Option C's UI adds the `primary_tags.` prefix to the key you enter — see [Option C](#option-c--central-enrichment-configuration). A key without the `primary_tags.` prefix (in `DT_TAGS`, a host tag, or a resource attribute) stays a regular attribute and does not propagate.

**Plain-name tags** (no value — an entity either has the tag or does not) should not be mechanically migrated to `primary_tags.<key>=true`. If several similar tags share a prefix (e.g. `@division-en`, `@division-it`, `@division-de`), collapse them into a single key with multiple values: `primary_tags.division=en`, `primary_tags.division=it`, etc.

**20-tag limit:** 20 primary tags is the **default** maximum per host or process. Plan within it and prioritise the most business-critical keys first — but it is a configurable default (`optionMaxNumPrimaryGrailTags`), not a hard ceiling, so a customer with a genuine need for more has something to ask for rather than a wall. Confirm what actually happens to tags beyond the limit against the customer's tenant before relying on it.

### Option A — OneAgent enrichment

**Host-level** (applies to all processes and signals from the host — preferred when a whole host belongs to one team or environment):

Warning: the example commands below must be executed directly on the affected host by the user.

* At install time: `Dynatrace-OneAgent-Linux.sh --set-host-tag="primary_tags.team=backend"`
* On an existing installation: `oneagentctl --set-host-tag="primary_tags.team=backend"`

**Process-level** (`DT_TAGS` — overrides host-level for that process, useful when different processes on the same host need different tags):

```bash
DT_TAGS="primary_tags.application_name=payment primary_tags.team=backend"
```

Multiple tags are space-separated. Use process-level for: specific processes on shared hosts, containerized workloads without OTel instrumentation, AWS Lambda / Azure Functions (where host-level config is not available).

Process-level tags never reach the HOST or DISK node — they stay on the process and its data. On AWS Lambda the code module reads **only** `DT_TAGS`; it reaches spans, service metrics, and the function logs, but not the `AWS_LAMBDA_FUNCTION` node, which comes from the cloud connection — tag that node through an AWS tag rule ([Cloud connection telemetry](#cloud-connection-telemetry)).

### Option B — OpenTelemetry resource attributes

```bash
OTEL_RESOURCE_ATTRIBUTES="primary_tags.application_name=payment,primary_tags.team=backend,service.name=payment"
```

Use for services instrumented with the OpenTelemetry SDK. On a process that OneAgent monitors, `primary_tags.*` entries in `OTEL_RESOURCE_ATTRIBUTES` behave exactly like `DT_TAGS`.

OpenTelemetry Collectors do not read the ingest enrichment configuration (Option C). For OTLP data that goes through a Collector, set the tags as resource attributes or in the Collector itself; Option D still applies at ingest.

### Option C — Central enrichment configuration

Central enrichment configuration (**Ingest enrichment configuration**, **Settings > Collect and capture > Ingest enrichment configuration**, schema `builtin:ingest.enrichment.config`) defines rules in Dynatrace that the collecting component applies — OneAgent for host and process data, the Operator for Kubernetes data, the cloud connection for cloud data. For host and process data, no changes on the hosts are required and no agent restart is needed.

Rule types: `HOST_PROCESS_PROPERTY` (host/process property), `CUSTOM` (static literal), `K8S_NAMESPACE_LABEL` / `K8S_NAMESPACE_ANNOTATION`, `K8S_WORKLOAD_LABEL` / `K8S_WORKLOAD_ANNOTATION`, `K8S_POD_LABEL` / `K8S_POD_ANNOTATION` (see [Kubernetes telemetry](#kubernetes-telemetry)), and the cloud tag rules `AWS_TAG`, Azure tag, and GCP label (see [Cloud connection telemetry](#cloud-connection-telemetry)). This section covers the OneAgent rule types.

This is the **nearest analog to classic auto-tagging**: a central, rule-based engine that maps existing attributes to tags. The difference is that it runs pre-ingest and produces `primary_tags.*` on every signal, rather than stamping Smartscape entities after ingest.

**When to use:**
- Changing every deployment individually (host tags, `DT_TAGS`, manifests) is impractical, but the context you want already exists on the host — via host tags, host groups, or a host-name/process-group naming convention.
- Migrating auto-tag rules that matched infrastructure attributes (host group, host name) — the rule condition mirrors the old auto-tag condition, and a DPL transformation replaces the old regex value extraction.

**How a rule is configured** — each rule is a **condition** plus an **enrichment**:

| Part | Description |
|---|---|
| **Condition** | Selects the hosts/processes to enrich, using OneAgent input fields: `dt.host_group.id`, `host.name`, `host.tags.<key>`, `k8s.cluster.name`, `k8s.namespace.name`, `aws.account.id`. Operators: `matchesValue` (equals), `matchesPhrase` (contains, begins/ends with), `isNull`, `isNotNull`, combined with `AND`, `OR`, `NOT`. Conditions only take effect on rules that **OneAgent** evaluates — Kubernetes and cloud skip custom literal rules that carry a condition. |
| **Enrichment** | A **static value** or a **DPL transformation** on an input field. Each rule writes **one** primary tag under `primary_tags.<key>` (or one primary field: Security context, Cost center, or Cost product). No partial output — if the DPL pattern doesn't match, nothing is written. |

**Rule anatomy in the UI** — each rule is edited as **Rule type** (e.g. *Host/process property*) → **Source attribute**, picked from a dropdown, where templated entries such as `host.tags.<key>` or `process.custom_metadata.<key>` require you to fill in `<key>` → **Target** (*Primary tag*, or a primary field) plus the key to write → optional **Override value with DPL expression** → optional **Condition** that limits rule execution. Before saving, the dialog previews the **Resulting mapping**.

**Enter the target key suffix only** — `team`, not `primary_tags.team`. The UI adds the `primary_tags.` prefix itself and shows the full field name in the **Resulting mapping** preview; read the key off that preview instead of typing the prefix yourself. This differs from Options A–B, where you write the full `primary_tags.*` key. The suffix-only rule applies to the **UI only**: a settings object written through the Settings API carries the full key in `target`:

```json
{ "type": "HOST_PROCESS_PROPERTY", "valueSource": "process.custom_metadata.team", "target": "primary_tags.team" }
```

**Migrating a classic rule — fixed source-attribute mappings.** Work down this ladder. The first case that matches the classic rule's input source determines the enrichment rule; do not improvise a source attribute outside it.

1. **`valueFormat` is a static literal** → static-value enrichment. No source attribute, no DPL. This is the common case (see [regex-to-dpl.md](regex-to-dpl.md#classic-valueformat-placeholders)).
2. **Input is a host tag or process tag** → one rule, source `host.tags.<key>` / `process.tags.<key>`, target the primary tag key. Value passes through unchanged; no DPL.
3. **Input is a custom property** — including the classic `{Host:Environment:<key>}` placeholder, which reads **host custom metadata** and not a deployment stage (`dt.host.property.<key>` names the same property) → source `host.custom_metadata.<key>` / `process.custom_metadata.<key>`. Same 1:1 passthrough.
4. **Input is the host group, host name, or process-group detected name with metadata encoded in the name** → source is the corresponding attribute and the value comes from a **DPL expression**. One rule per extracted value — same source and condition, `:value` at a different position ([regex-to-dpl.md](regex-to-dpl.md#one-tag-per-rule)).
5. **Input is a cloud or Kubernetes attribute** → no DPL extraction for either; the value passes through 1:1.
   - **Cloud tags on a OneAgent-monitored VM** — OneAgent reads the instance tags from the cloud's instance metadata service and exposes them as host properties `aws.tags.<key>` (EC2) / `azure.tags.<key>` (Azure VMs). Map them with a host/process property rule, `valueSource: aws.tags.<key>`. This tags HOST, DISK, and PROCESS nodes, OneAgent logs, and process metrics. **Known issue:** on EC2 the value does not yet reach spans or service metrics — until fixed, also set a host tag or `DT_TAGS` with the same value.
   - **Cloud tags on cloud connection data** (CloudWatch metrics, cloud entities, cloud events) → a cloud tag rule plus Option D, see [Cloud connection telemetry](#cloud-connection-telemetry).
   - **Kubernetes labels or annotations** → a namespace, workload, or pod label/annotation rule, see [Kubernetes telemetry](#kubernetes-telemetry).
6. **Anything else** → do not guess a source attribute. Fall back to [Option A](#option-a--oneagent-enrichment)/[B](#option-b--opentelemetry-resource-attributes) at the source or [Option D](#option-d--openpipeline-primary-grail-tag-rules-last-resort), and report the rule as unmapped.

**Source attributes and Grail field names are different namespaces — do not mix them.** An enrichment rule's *source attribute* is scoped to the entity it reads and carries a `host.` / `process.` prefix (`host.dt.host_group.id`); the *Grail field* the same data lands in, and the field used in a rule **condition**, is the unprefixed name (`dt.host_group.id`). Use the prefixed form only in the source-attribute dropdown.

Source attribute strings confirmed on a live tenant:

| Classic auto-tag input | Enrichment source attribute | Shape |
|---|---|---|
| Host group / `{HostGroup:Name}` | `host.dt.host_group.id` | DPL (or 1:1 if the whole name is the value) |
| Host tag | `host.tags.<key>` | 1:1 |
| Process / process-group tag | `process.tags.<key>` | 1:1 |
| Host custom property | `host.custom_metadata.<key>` | 1:1 |
| Process custom property | `process.custom_metadata.<key>` | 1:1 |

**Confirmed available, exact attribute name to be taken from the dropdown:** host name (`{Host:DetectedName}`; the Grail field is `host.name`, but the prefixed source-attribute string was not captured — do not assume it is identical), process-group detected name, AWS tags, Azure tags, Kubernetes namespace labels and annotations. Kubernetes cluster labels and annotations were also seen in the dropdown, but no documented Kubernetes rule type reads them (only namespace, workload, and pod) — confirm on the customer's tenant before relying on them.

**Never source a rule from a primary tag.** A rule will happily read `process.tags.primary_tags.team` and write it into another `primary_tags.*` key — there is no guard against chaining primary tags into each other. Always source from the original attribute.

**Scopes and inheritance:** every scope inherits from the **environment** scope. Each component reads its own scope first, then the environment scope:

| Component | Where to put its rules |
|---|---|
| OneAgent (host, process, local extension data) | **Host group** scope if needed, otherwise environment |
| Operator / ActiveGate (Kubernetes data) | **K8s cluster** scope or environment — never host group |
| Cloud connection | **Cloud** scope (AWS account, Azure subscription, GCP project) or environment |

The component receives its own scope's rules first, then the environment rules, and checks them top-down: for each target key, the **first rule that applies** wins. A narrower rule only wins if it applies — if its source property is missing, its condition doesn't match, or its value extraction returns nothing, the next rule (and then the environment scope) is checked. Enrichment applied to a host is inherited by its processes, containers, disks, and network interfaces.

Do not put Kubernetes rules at host group scope: Cloud Native Full Stack picks them up from the node's host group, Application Observability does not, so a cluster that switches modes silently loses the values.

**DPL transformation — deriving a tag from a naming convention.** When metadata is encoded in the host name or process-group name, use a DPL value-extraction expression on the input field. Each rule extracts **one** segment into **one** primary tag: the segment to keep is marked with `:value`, and the rule maps `:value` to the target key. To populate several tags from the same name, create one rule per tag — same source and condition, with `:value` at a different position.

Classic auto-tagging used regexes for this extraction. See [regex-to-dpl.md](regex-to-dpl.md) for the supported DPL matcher subset, a rewrite table, and a worked example of extracting multiple tags from the same naming convention (e.g. `<env>-<team>-<region>-<role>-<index>` — one rule per tag, all sharing the same source and condition).

**Limitations:**
- Cloud tags **collected by OneAgent** on AWS and Azure hosts are available as host/process property sources. Cloud tags on cloud connection data (including GCP labels) use the cloud tag rules plus Option D instead — see [Cloud connection telemetry](#cloud-connection-telemetry).
- Data sent through the ingest APIs, and OTLP data forwarded by an OpenTelemetry Collector, never gets ingest enrichment rules — use source-side tags or Option D.
- Serverless workloads (e.g. AWS Lambda, Azure Functions) do not support central enrichment configuration — enrich them via `DT_TAGS` (Option A) instead.
- Regex and nested condition functions (e.g. `isNull(isNotNull(x))`) are not supported in conditions.
- Defining the same key multiple times within one source is undefined behavior.

### Option D — OpenPipeline primary Grail tag rules (last resort)

When neither source-side enrichment (Options A–B) nor central enrichment configuration (Option C) is feasible, use **OpenPipeline primary Grail tag rules** (**Settings > Process and contextualize > OpenPipeline > Primary Grail tags**, schema `builtin:openpipeline.primary-grail-tag`) to derive `primary_tags.*` fields from fields already present on incoming records at ingest time.

Rules run as the first OpenPipeline stage for **every source except RUM** (including extension and Synthetic data) and are evaluated **before routing**, so the resulting `primary_tags.*` fields are immediately available for routing, bucket assignment, and access control. Changes apply almost immediately.

**A rule overwrites by default.** With the default matching condition, a primary Grail tag rule **replaces** a value that is already set — including values from pod annotations, `DT_TAGS`, host tags, and ingest enrichment rules. To only fill in a missing value and keep what the source set, give the rule the matching condition `isNull(primary_tags.<key>)`. Use this for every migration rule unless overwriting is intended.

**When to use:**
- **Cloud connection data** — required, not a fallback: a cloud tag rule puts `aws.tags.<key>` / `azure.tags.<key>` / `gcp.labels.<key>` on the data, and a primary Grail tag rule promotes it ([Cloud connection telemetry](#cloud-connection-telemetry)).
- The discriminator lives on the **record fields**, not on a host/process attribute that OneAgent can see (Option C operates on OneAgent host/process input fields; OpenPipeline operates on the record).
- Data that never gets ingest enrichment rules — API-ingested data and OTLP data forwarded by an OpenTelemetry Collector.
- The same logical tag is named differently across cloud providers (e.g. `aws.tags.env`, `azure.tags.env`, `gcp.labels.env` → `primary_tags.env`) — a single OpenPipeline rule can consolidate all variants centrally.
- `DIMENSION` or non-tag `SELECTOR` MZ conditions that cannot be expressed as source-side tags

**How a rule is configured:**

| Parameter | Description |
|---|---|
| **Primary tag field name** | Key suffix only — `env` produces `primary_tags.env`. Must be unique across all rules. |
| **Matching condition** | DQL expression scoping which records the rule applies to. The default matches all records and **overwrites** existing values; include `isNull(primary_tags.<key>)` to only fill missing values. |
| **Source fields** | Ordered list (up to 10). First field that exists and is non-null/non-empty on the record wins. |
| **Keep source field** | Whether to retain or drop the source fields after promotion. Primary Grail fields and Semantic Dictionary protected fields are always retained regardless. |

**Limits:** max 20 rules per environment; max 10 source fields per rule.

**Source field formats for cloud and Kubernetes tags:**

The field name to use as a source depends on whether the tag lives on a **signal record** or on a **Smartscape entity**:

| Source type | Signal records (logs, metrics, traces, events) | Entity records (hosts, K8s namespaces, …) |
|---|---|---|
| Azure tags | `azure.tags.<key>` | `tags:azure[<key>]` |
| AWS tags | `aws.tags.<key>` | `tags:aws[<key>]` |
| GCP labels | `gcp.labels.<key>` | `tags:gcp_labels[<key>]` |
| GCP tags (resource tags, not labels) | `gcp.tags.<tag-id>` | — |
| Kubernetes labels | `k8s.namespace.label.<key>` | `tags:k8s.labels[<key>]` |

Use the signal-record form when the OpenPipeline rule targets logs, metrics, or traces. Use the entity-record form when it targets entity data. Listing both in the source fields list of a single rule is valid — the first non-null match wins.

**Using the matching condition:**

The matching condition is a DQL expression that scopes which records the rule applies to. Always start from `isNull(primary_tags.<key>)` so the rule does not overwrite values set at the source, and add scoping (`and …`) unless the source field is specific enough that false matches are impossible.

Prefer **primary Grail fields** as condition attributes where they exist — they are indexed and evaluated efficiently:

```dql-snippet
k8s.cluster.name == "prod-cluster-01"
aws.account.id == "123456789012"
dt.host_group.id == "hg-payments-prod"
```

When primary fields don't cover the condition, use process or cloud attributes that mirror the original auto-tag or MZ rule condition — the goal is to match the same entity population the auto-tag rule would have matched. For example, if an auto-tag rule matched on `SERVICE_TAGS` with a specific tag value, the equivalent condition scopes the rule to records that already carry that tag before the primary tag is written.

**Example — consolidate cloud-provider environment tags:**

A rule targeting `primary_tags.env` with source fields `["aws.tags.env", "azure.tags.env", "gcp.labels.env"]` and matching condition `isNull(primary_tags.env)` maps whichever cloud tag is present on each record to a single `primary_tags.env` — no per-cloud logic needed in downstream queries or Segment filters.

See [mz-classification.md](../management-zones/mz-classification.md) for how to identify which MZ rule types fall outside the scope of source-side tagging.

### Extensions telemetry

Telemetry collected by the Dynatrace **Extensions framework** is enriched primarily **per monitoring configuration**. This is the path for auto-tag rules that scoped extension-collected data. Extension data (local and remote) also goes through OpenPipeline primary Grail tag processing, so [Option D](#option-d--openpipeline-primary-grail-tag-rules-last-resort) can still add or replace tags on it.

- **Local extensions** (run on OneAgent) automatically **inherit** everything OneAgent carries on that host — host tags (Option A) and the values of host/process property and custom literal ingest enrichment rules (Option C). You can additionally set primary **tags** explicitly per monitoring configuration; primary fields come from the host and cannot be set explicitly.
- **Remote extensions** (run on the Extension Execution Controller, with no host) inherit nothing — configure **both** primary fields and tags explicitly per monitoring configuration.

Enrichment can be set at two levels: **whole configuration** (applies to all data from the configuration) and **per endpoint** (overrides whole-configuration values for the same key). Precedence: endpoint → whole-configuration → host-level (local extensions only).

Configure it in the UI (**Extensions** → your extension → monitoring configuration → **Primary tags** / **Primary fields**) or via the Extensions API — `PUT /api/v2/extensions/{name}/monitoringConfigurations/{id}`:

```json
{
  "primaryTags": [
    { "key": "primary_tags.environment", "value": "production" },
    { "key": "primary_tags.team", "value": "platform" }
  ]
}
```

To migrate an auto-tag rule that scoped extension-collected entities, set the equivalent `primary_tags.*` on the extension's monitoring configuration (whole-config for shared metadata, per-endpoint where individual targets differ).

### RUM telemetry

Real User Monitoring data (web RUM JavaScript, mobile OneAgent) enters through the `rumagent` ingest source and has **no at-source** configuration for primary tags. RUM also **skips** OpenPipeline primary Grail tag processing, so neither ingest enrichment rules (Option C) nor primary Grail tag rules ([Option D](#option-d--openpipeline-primary-grail-tag-rules-last-resort)) tag RUM data. The only path is an **OpenPipeline DQL processor** in a base pipeline of each RUM configuration scope.

The recommended anchor is **`frontend.name`** — a primary field on `user.events` and `user.sessions`. A single frontend name, or a group representing the same product/team, derives organizational metadata such as team ownership.

OpenPipeline has a separate **configuration scope** per RUM signal type (User events, User sessions, Smartscape events, Events, Business events, Timeseries) with no shared enrichment step — configure the rule in **each scope** where you want the tag. Best practice: add the DQL processor to a **base pipeline** (via pipeline groups) so `primary_tags.*` is set before team-specific pipelines run.

For scalar scopes (everything except User sessions), use a DQL processor with matching condition `isNotNull(frontend.name)`:

```dql-snippet
fieldsAdd primary_tags.team = if(matchesValue(frontend.name, "Astroshop*"), "shop-team", else: null)
| fieldsAdd primary_tags.team = if(isNull(primary_tags.team) and matchesValue(frontend.name, "Checkout*"), "checkout-team", else: primary_tags.team)
```

**User sessions is the exception:** a session can span multiple frontends, so `frontend.name` is an **array** there. Build an array of candidate values and drop nulls, so the tag carries every team the session touched:

```dql-snippet
fieldsAdd primary_tags.team = arrayCompact(array(
  if(arrayIndexOf(frontend.name, "Astroshop") >= 0, "shop-team", else: null),
  if(arrayIndexOf(frontend.name, "Checkout") >= 0, "checkout-team", else: null)
))
```

To migrate an auto-tag rule that scoped RUM/application entities, derive the equivalent `primary_tags.*` from `frontend.name` in each RUM configuration scope. Check RUM-on-Grail is enabled for the frontends first (see [enable-rum-on-grail.md](../../digital-experience/enable-rum-on-grail/enable-rum-on-grail.md)).

**Caveats:** RUM primary-tag guidance is still evolving — validate the DQL against your tenant. OpenPipeline is currently the only path (no at-source enrichment); the mapping must be applied separately in every configuration scope; and `frontend.name` is set at ingest, so historical records are not retroactively re-tagged when frontend detection changes.

### Kubernetes telemetry

Kubernetes workloads are enriched with primary Grail fields and tags via the Dynatrace Operator. Enrichment requires `metadataEnrichment: enabled` in the DynaKube (Operator 1.10+, OneAgent 1.333+, ActiveGate 1.343+; workload and pod rule types need Operator 1.11). Choose the first mechanism below that covers your use case.

1. **Built-in primary fields** — `k8s.cluster.name` and `k8s.namespace.name` are populated on all Kubernetes telemetry with no configuration. If cluster/namespace scoping is all you need, there is nothing to migrate.

2. **Dedicated annotations** — add `metadata.dynatrace.com/primary_tags.<key>` annotations to a `Namespace` (applies to all workloads) or a `Pod` (overrides the namespace for that pod). This sets the primary tag directly. The primary fields `dt.security_context`, `dt.cost.costcenter`, and `dt.cost.product` use the same convention.

   ```yaml
   metadata:
     annotations:
       metadata.dynatrace.com/primary_tags.team: payments
       metadata.dynatrace.com/primary_tags.environment: production
   ```

3. **DynaKube resource attributes** — define attributes in the DynaKube and the Operator propagates them to all telemetry without touching workloads. Keys prefixed `primary_tags.*` become primary tags. Use `.spec.resourceAttributes` for all signals, or `.spec.oneAgent.<mode>.additionalResourceAttributes` / `.spec.otlpExporterConfiguration.additionalResourceAttributes` for scoped overrides (these take precedence). Soft limit ~10 attributes.

   ```yaml
   spec:
     resourceAttributes:
       primary_tags.team: "alpha"
   ```

4. **Kubernetes ingest enrichment rules (map existing labels/annotations)** — the recommended path when namespaces, workloads, or pods already carry the context (team, environment, cost center) as labels or annotations; no manifest changes. The rule writes the value **directly** to `primary_tags.<key>` — no OpenPipeline step needed. Rule types in the [ingest enrichment configuration](#option-c--central-enrichment-configuration):

   | Rule type | Value comes from | Tags |
   |---|---|---|
   | `K8S_NAMESPACE_LABEL` / `K8S_NAMESPACE_ANNOTATION` | a label/annotation on the namespace | all signals, plus pod, deployment, and namespace nodes |
   | `K8S_WORKLOAD_LABEL` / `K8S_WORKLOAD_ANNOTATION` (Operator 1.11) | a label/annotation on the deployment, stateful set, or daemon set | all signals, plus pod and deployment nodes — never the namespace |
   | `K8S_POD_LABEL` / `K8S_POD_ANNOTATION` (Operator 1.11) | a label/annotation on the pod | all signals, plus pod, container, and process nodes |
   | `CUSTOM` (static literal) | the value itself | all signals and Kubernetes nodes in the rule's scope |

   Put these rules at **K8s cluster** or **environment** scope, never host group scope (see [Option C scopes](#option-c--central-enrichment-configuration)). There is no DPL extraction: the label value passes through unchanged. Values the Operator resolves from Kubernetes metadata are applied when a **pod starts**, so existing pods need a restart; custom literal rules reach running pods without one. For enablement details, see [Kubernetes telemetry enrichment](../../infrastructure-observability/kubernetes-telemetry-enrichment/kubernetes-telemetry-enrichment.md).

5. **OpenPipeline (last resort)** — derive primary tags at ingest with [Option D](#option-d--openpipeline-primary-grail-tag-rules-last-resort) when none of the above apply (with `isNull(primary_tags.<key>)`, so it does not overwrite values from the mechanisms above).

**Tags don't flow up.** A pod annotation tags the pod, its containers, and processes, never the deployment or namespace node.

**Precedence (K8s):** pod annotation → namespace annotation → DynaKube resource attributes → ingest enrichment rule. A primary Grail tag rule (Option D) runs after all of these and overwrites unless it has the `isNull` condition.

**Migration tie-in:** auto-tag rules keyed on cluster or namespace need no work — `k8s.cluster.name`/`k8s.namespace.name` are already primary fields. For team/app/environment tags, map existing labels or annotations with a Kubernetes ingest enrichment rule, set dedicated annotations (per workload/namespace), or use DynaKube resource attributes (fixed cluster-wide value).

### Cloud connection telemetry

Data from the AWS, Azure, and Google Cloud connections (cloud metrics, cloud logs for linked services, cloud entities, and cloud events) is enriched by the **cloud connection**, not by OneAgent. Two steps are needed today:

1. A **cloud tag rule** in the ingest enrichment configuration — `AWS_TAG`, the Azure tag rule, or the GCP label rule — puts the resource tag on the data as `aws.tags.<key>`, `azure.tags.<key>`, or `gcp.labels.<key>`.
2. A **primary Grail tag rule** ([Option D](#option-d--openpipeline-primary-grail-tag-rules-last-resort)) promotes that field to `primary_tags.<key>`. Give it the matching condition `isNull(primary_tags.<key>)`, otherwise it overwrites values set at the source.

Put the cloud tag rule at the **cloud scope** (AWS account — settings scope `AWS_ACCOUNT-aws.account.id:<account-id>` — Azure subscription, or GCP project) or the environment scope.

Cloud tag rules only touch cloud connection data. **OneAgent running on a cloud VM produces OneAgent data**, which the cloud tag rule does not enrich — use a host/process property rule on `aws.tags.<key>` / `azure.tags.<key>` instead (see the [fixed source-attribute mappings](#option-c--central-enrichment-configuration), step 5). AWS logs only get AWS tags for linked services (for example Lambda and RDS); EC2 logs from Firehose are not linked, so use OneAgent for EC2 logs.

### Synthetic telemetry

Synthetic monitors have their own **per-monitor primary Grail tags** (limit 10) and **inherit nothing** — neither ingest enrichment rules nor host tags apply. To migrate an auto-tag rule that scoped synthetic monitors (for example a plain `Synthetic` tag), set the equivalent `primary_tags.*` on each monitor. Synthetic events and metrics also go through OpenPipeline primary Grail tag processing, so [Option D](#option-d--openpipeline-primary-grail-tag-rules-last-resort) can fill gaps.

### Precedence

When the same `primary_tags.*` key is set through more than one option, the more specific definition wins:

1. **Process-level** (`DT_TAGS` / `OTEL_RESOURCE_ATTRIBUTES`, Options A–B)
2. **Host-level** (installer or `oneagentctl`, Option A)
3. **Central enrichment configuration** rule (Option C)

Host-level tags fill in any keys the process didn't override. **OpenPipeline** (Option D) runs on the record at ingest, **after** all of these, and with its default condition **overwrites** whatever they set. Give every Option D rule the matching condition `isNull(primary_tags.<key>)` so that source and central enrichment keep precedence over pipeline-derived values.

User pipelines run after routing and can still change most `primary_tags.*` fields, but a change there does not re-route the record — it only changes what is stored. To influence routing, set the tag at the source, in the ingest enrichment configuration, or in a primary Grail tag rule.

## Customer actions

- Export `builtin:tags.auto-tagging` settings and establish the total rule count
- Ask whether any scripts or automations write tags through the Tags API, and compare the tag keys present on entities against the export to find them; classify each script job by pattern ([Tags applied outside auto-tagging rules](#tags-applied-outside-auto-tagging-rules))
- Cross-reference tag rule names against management zone conditions to identify which rules are load-bearing for entity scoping (see [mz-export-schema.md](../management-zones/mz-export-schema.md))
- Classify each load-bearing rule: does the tag key map to a **built-in Grail field** (`k8s.cluster.name`, `aws.account.id`, etc.)? If so, no source-side action is required — update downstream filters to use the Grail field directly. Base this on the rule's conditions and `valueFormat`, never on the rule name: a rule called `Cluster` or `Namespace` is not a Kubernetes one until the export proves it ([Never infer a source from a name](#never-infer-a-source-from-a-name))
- Leave rules whose value source the export does not identify **explicitly unresolved** and ask the customer, rather than assigning a plausible attribute
- Route each rule by where its data originates: **Kubernetes** ([Kubernetes telemetry](#kubernetes-telemetry)), **cloud connection** ([Cloud connection telemetry](#cloud-connection-telemetry)), **RUM** ([RUM telemetry](#rum-telemetry)), **Synthetic** ([Synthetic telemetry](#synthetic-telemetry)), and **extension-collected** telemetry ([Extensions telemetry](#extensions-telemetry)) follow their dedicated subsections; host/process telemetry follows the A–D hierarchy below
- For host/process rules, choose the delivery mechanism following the hierarchy: OneAgent host/process-level (A) → OTEL resource attributes (B) → central enrichment configuration (C) → OpenPipeline primary Grail tag rules (D, last resort)
- For auto-tag rules that matched infrastructure attributes (host group, host name) — especially those using regex value extraction — prefer central enrichment configuration (Option C); it is the closest 1:1 replacement and needs no per-workload changes (see [regex-to-dpl.md](regex-to-dpl.md) to translate the regexes)
- When building Option C rules, derive the source attribute from the [fixed source-attribute mappings](#option-c--central-enrichment-configuration) ladder rather than guessing: tags → `host.tags.<key>` / `process.tags.<key>`, custom properties → `host.custom_metadata.<key>` / `process.custom_metadata.<key>`, host group → `host.dt.host_group.id` with DPL. Report rules whose input source is not on that list (Cloud Foundry, AWS/Azure PaaS) as unmapped instead of inventing an attribute
- For `DIMENSION` or non-tag `SELECTOR` MZ rules, use OpenPipeline primary Grail tag rules (Option D) or Grail query filters directly
- Give every Option D rule the matching condition `isNull(primary_tags.<key>)` unless it is meant to overwrite source values
- Validate coverage: after deploying source-side tags, confirm the data and entities carry the expected `primary_tags.*` before disabling auto-tagging rules. **SERVICE entities never carry `primary_tags.*`** (by design) — for auto-tag rules that targeted services, check spans and service metrics instead, and build segments with an extra Entities include for the team's services (see [Tracking queries](#tracking-queries))
- Auto-tagging rules are removed in Phase 3 — complete migration before the Phase 3 cutover

## Tracking queries

Find entities carrying a specific auto-tag rule name (replace `<rule-name>` with the actual rule name):

```dql-template
fetch dt.entity.service
| filter "<rule-name>" in tags
| fields entity.name, tags
| limit 20
```

Verify source-side primary tag coverage after migration (replace `application_name` with the migrated key):

```dql
fetch logs, from: now()-24h
| filter isNotNull(primary_tags.application_name)
| summarize logCount = count(), by: {primary_tags.application_name}
| sort logCount desc
```

The SERVICE Smartscape node has no `primary_tags.*` fields, so a filter on `primary_tags.team` alone matches a team's data but not its services. Service metrics carry both the primary tag and the service ID, so they link the two — use this as a segment variable and add an **Entities** include `type = SERVICE AND id in ($dt.smartscape.service)` next to the **Data (all types)** include `primary_tags.team = $primary_tags.team`:

```dql
metrics
| filter isNotNull(primary_tags.team) and primary_tags.team != ""
| fields primary_tags.team, dt.smartscape.service
| summarize by: primary_tags.team, dt.smartscape.service = collectDistinct(dt.smartscape.service)
| sort lower(primary_tags.team)
```

## Related references

- [regex-to-dpl.md](regex-to-dpl.md) — translate classic auto-tagging regex value extraction to DPL transformations (for central enrichment configuration, Option C)
- [mz-export-schema.md](../management-zones/mz-export-schema.md) — how MZ conditions reference auto-tagging rules (for the footprint cross-reference)
- [mz-classification.md](../management-zones/mz-classification.md) — which MZ rule types fall outside source-side tagging scope
- [enable-rum-on-grail.md](../../digital-experience/enable-rum-on-grail/enable-rum-on-grail.md) — enable RUM on Grail for frontends before deriving RUM primary tags
- [kubernetes-telemetry-enrichment.md](../../infrastructure-observability/kubernetes-telemetry-enrichment/kubernetes-telemetry-enrichment.md) — interim/enablement path for Kubernetes metadata enrichment
- [analyze-exports.md](../management-zones/analyze-exports.md) — offline script to cross-reference auto-tagging rules against MZ conditions
- [auto-tagging-field-mapping.md](../entity-queries/auto-tagging-field-mapping.md) — auto-tag condition-key → built-in Grail/semantic field lookup
- [management-zones.md](../management-zones/management-zones.md) — related management zone migration

## Documentation

- [Primary Grail fields and tags](https://docs.dynatrace.com/docs/manage/tags/primary-tags)
- [Tags overview](https://docs.dynatrace.com/docs/manage/tags) — links every domain page
- Domain pages: [OneAgent](https://docs.dynatrace.com/docs/manage/tags/primary-tags/tags-domain-oneagent), [Kubernetes](https://docs.dynatrace.com/docs/manage/tags/primary-tags/tags-domain-k8s), [AWS](https://docs.dynatrace.com/docs/manage/tags/primary-tags/tags-domain-aws), [Azure](https://docs.dynatrace.com/docs/manage/tags/primary-tags/tags-domain-azure), [Google Cloud](https://docs.dynatrace.com/docs/manage/tags/primary-tags/tags-domain-gcp), [OpenTelemetry](https://docs.dynatrace.com/docs/manage/tags/primary-tags/tags-domain-otel), [RUM](https://docs.dynatrace.com/docs/manage/tags/primary-tags/tags-domain-rum), [Synthetic](https://docs.dynatrace.com/docs/manage/tags/primary-tags/tags-domain-synthetic), [Extensions](https://docs.dynatrace.com/docs/manage/tags/primary-tags/tags-domain-extensions)
- [Primary tags across an AWS estate](https://docs.dynatrace.com/docs/manage/tags/tags-example-end-to-end-aws) — one tag schema across EKS, EC2, RDS, Lambda, RUM, and Synthetic

<!-- TODO: add links once available:
  - Auto-tagging classic (settings UI / API reference)
-->

Primary-tag behavior in this file applies to Dynatrace Operator 1.11 and OneAgent/ActiveGate 1.350 (reviewed 2026-10).
