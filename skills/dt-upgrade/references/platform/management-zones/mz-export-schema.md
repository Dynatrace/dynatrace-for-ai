# Management Zone Export Schema

Reference for reading `builtin:management-zones` export files during migration analysis. Use this alongside [mz-classification.md](mz-classification.md) to understand what each zone does before choosing a migration path. For a ready-to-run script that parses both export file types and cross-references auto-tagging rules against MZ conditions, see [analyze-exports.md](analyze-exports.md).

## Contents

- [Top-level structure](#top-level-structure)
- [Rule types](#rule-types)
- [Common condition keys](#common-condition-keys)
- [Where a condition's value lives](#where-a-conditions-value-lives)
- [Tag formats in conditions](#tag-formats-in-conditions)
- [Extracting auto-tag references from an MZ](#extracting-auto-tag-references-from-an-mz)
- [Related references](#related-references)

## Top-level structure

The export file (`*.builtin_management-zones.json`) is a JSON array. Each element is a settings object:

```json
{
  "objectId": "<stable-uid>",
  "schemaId": "builtin:management-zones",
  "scope": "",
  "value": {
    "name": "<MZ name>",
    "rules": [ ... ]
  }
}
```

`value.name` is the human-readable MZ name. `value.rules` may be an empty array — zones with no rules have no automatic entity matching and require manual classification.

## Rule types

Each rule has a `type` field:

| Type | Meaning |
|---|---|
| `ME` | Monitored Entity — matches entities by their attributes, tags, or metadata |
| `DIMENSION` | Metric dimension — matches metrics by dimension key/value filters |
| `SELECTOR` | Entity Selector — matches entities using an Entity Selector expression |

### ME — Monitored Entity attribute rule

```json
{
  "type": "ME",
  "enabled": true,
  "attributeRule": {
    "entityType": "SERVICE",
    "serviceToHostPropagation": false,
    "serviceToPGPropagation": false,
    "conditions": [
      {
        "key": "SERVICE_TAGS",
        "operator": "EQUALS",
        "tag": "keptn_project:cpu-usage"
      }
    ]
  }
}
```

The propagation flags (`serviceToHostPropagation`, `serviceToPGPropagation`, and the
open-ended rest — see below) extend zone membership to related entities. **Ignore
them for this purpose only:** they do not affect *which auto-tagging rules a zone
references*, so they play no part in the cross-reference extraction described below.

**They are decisive for portability, and must not be ignored there.** Any truthy
field whose name ends in `Propagation` makes the zone depend on Smartscape topology,
which raw Grail records do not carry — that puts the zone in the
`analyze_relationships` category, which cannot be ported as-is. Match the suffix
generically rather than checking the two names above: the flag set is open-ended
(process-group→host, process-group→service, Azure→process-group, Azure→service and
custom-device-group variants all exist). See
[evaluate-and-classify.md](evaluate-and-classify.md#grail-equivalence-categories)
for the classification rule. Treating a propagating zone as directly portable is the
most damaging error available in this workflow.

### DIMENSION — Metric dimension rule

```json
{
  "type": "DIMENSION",
  "enabled": true,
  "dimensionRule": {
    "appliesTo": "METRIC",
    "conditions": [
      {
        "conditionType": "METRIC_KEY",
        "ruleMatcher": "BEGINS_WITH",
        "value": "kubelet_volume_stats"
      }
    ]
  }
}
```

`appliesTo` is `"METRIC"`, `"LOG"`, or `"ANY"`. A `"METRIC"` rule filters metrics by key. A `"LOG"` rule matches log attributes directly — a log field (`conditionType: "DIMENSION"` with a `key`) or the source file (`conditionType: "LOG_FILE_NAME"`) — and is the most portable rule in the schema: its condition is already a predicate over log records and translates almost literally into a Segment filter. `"ANY"` applies to both metrics and logs. `"LOG"` and `"ANY"` rules never appear in the usage metric (`dt.sfm.server.management_zones.queries_counter`, which counts only the classic entity/metric path), so a zone whose rules are purely log-based looks unused in the usage ranking and risks being triaged as junk. See [evaluate-and-classify.md](evaluate-and-classify.md#log-based-management-zones) for the portability and verification detail. DIMENSION rules do not reference auto-tagging rules and cannot be migrated via source-side tagging. See [mz-classification.md — Dimension 7](mz-classification.md#dimension-7--metric--entity-selector-rules) for the migration path.

### SELECTOR — Entity selector rule

```json
{
  "type": "SELECTOR",
  "enabled": true,
  "entitySelector": "type(SERVICE),fromRelationships.runsOn(type(\"RELATIONAL_DATABASE_SERVICE\"),tag(\"[AWS]Name:orders-db-prod\"))"
}
```

SELECTOR rules may reference tags via `tag("...")` substrings in the `entitySelector` string. Apply the same tag-format logic as for `_TAGS` condition keys to extract auto-tag rule references.

## Common condition keys

These `key` values appear in `attributeRule.conditions` for `ME` rules:

| Key | What it matches |
|---|---|
| `SERVICE_TAGS` | Auto-tag or manual tag on a service entity |
| `HOST_TAGS` | Auto-tag or manual tag on a host entity |
| `PROCESS_GROUP_TAGS` | Auto-tag or manual tag on a process group |
| `BROWSER_MONITOR_TAGS` | Tag on a browser synthetic monitor |
| `KUBERNETES_CLUSTER_NAME` | Kubernetes cluster name (attribute, not a tag) |
| `PROCESS_GROUP_PREDEFINED_METADATA` | Predefined metadata, e.g. K8s namespace via `dynamicKey: KUBERNETES_NAMESPACE` |
| `HOST_CLOUD_TYPE` | Cloud provider enum: `AZURE`, `EC2`, `GOOGLE_CLOUD_PLATFORM` |
| `NAME` | Entity name string |

Keys ending in `_TAGS` hold the full tag string in the `tag` field of the condition and are the primary source of auto-tagging rule references.

## Where a condition's value lives

A condition's value does not always arrive in the same field. **A parser that reads
only `stringValue` silently drops conditions** — it produces a smaller inventory that
looks complete, which is worse than crashing. Read the carrier, not a fixed field
name:

| Carrier | Used by | Example keys |
|---|---|---|
| `stringValue` (with `caseSensitive`) | free-text matches | `NAME`, `HOST_GROUP_NAME` |
| `enumValue` | closed-set attributes | `HOST_CLOUD_TYPE` |
| `dynamicKey` | keyed metadata lookups | `PROCESS_GROUP_PREDEFINED_METADATA` |
| `entityId` | direct entity references | `HOST_GROUP_ID` |
| `tag` | every `_TAGS` key | `SERVICE_TAGS`, `HOST_TAGS` |
| *no value field at all* | `EXISTS` / `NOT_EXISTS` operators | any key |

The last row is the one that breaks naive parsers twice over: an existence check has
no value to read, and skipping it because the value is absent drops a condition that
is doing real filtering work.

## The operator decides whether there is a value domain

The carrier tells you where the value is; the **operator** tells you whether the condition compares a value at all. Observed live: `EQUALS`, `BEGINS_WITH`, `CONTAINS`, `NOT_CONTAINS`, `EXISTS`, `TAG_KEY_EQUALS`. Three consequences for the port:

- **`TAG_KEY_EQUALS` and `EXISTS` have no value domain.** `TAG_KEY_EQUALS` with `"tag": "team"` matches the tag *key* whatever its value — it ports to a presence check (`isNotNull`), not an equality filter. Do **not** run the [value-domain check](management-zones.md#stage-3--verify-enrichment) against these and do not report them dead when no literal matches: there is no literal. Which form dominates varies by tenant, so read the operator on every tag condition rather than assuming one.
- **`NOT_CONTAINS` is a negation.** The Segment must invert it. A rule inventory that records only the key and value silently turns an exclusion into an inclusion.
- **`EQUALS`, `BEGINS_WITH`, `CONTAINS` compare values** and are the only ones the value-domain check applies to.

**Treat this list as open, not closed.** In one reference environment, 28 of 204 ME
conditions used a carrier outside `stringValue`/`enumValue`/`dynamicKey` — so an
unfamiliar carrier is a normal occurrence, not corrupt data. Record the condition's
`key` regardless of which carrier is present, and report any carrier you cannot
interpret rather than dropping the condition.

## Tag formats in conditions

When a condition key ends in `_TAGS`, the `tag` field holds the tag string in one of these formats:

| Format | Example | Auto-tag rule name to look up |
|---|---|---|
| Key-value | `keptn_project:sockshop` | `keptn_project` (part before `:`) |
| Plain name | `Synthetic` | `Synthetic` (the whole string) |
| Cloud-origin | `[AWS]Name:orders-db-prod` | Not an auto-tagging rule — skip |

Cloud-origin tags are prefixed with `[AWS]`, `[GCP]`, or `[Azure]`. They originate from cloud provider tag propagation and have no corresponding Dynatrace auto-tagging rule.

## Extracting auto-tag references from an MZ

To find which auto-tagging rules a management zone depends on:

1. Walk `value.rules` for each MZ.
2. For `ME` rules: collect every `tag` field from conditions whose `key` ends in `_TAGS`.
3. For `SELECTOR` rules: extract all `tag("...")` substrings from the `entitySelector` string.
4. For each collected tag string: discard cloud-origin prefixes (`[AWS]`, `[GCP]`, `[Azure]`); for key-value tags, take the part before `:`. The result is the auto-tagging rule name to look up.
5. Look up each rule name in the auto-tagging export using `value.name` as the key. Match case-sensitively first; fall back to case-insensitive if no exact match, and note the discrepancy.
6. `DIMENSION` rules never reference auto-tagging rules — skip them during cross-reference analysis.

The cross-reference output is two lists: **matched rules** (rule name, objectId, MZ names that reference it) and **unmatched tag references** (tag values with no corresponding auto-tagging rule — cloud tags, Keptn tags from external CI/CD, manually applied tags).

## Related references

- [mz-classification.md](mz-classification.md) — classify what each zone does (7-dimension taxonomy)
- [analyze-exports.md](analyze-exports.md) — offline script that applies the extraction described here
- [management-zones.md](management-zones.md) — management zone migration strategy and runbook
- [autotagging.md](../autotagging/autotagging.md) — migrating the auto-tagging rules referenced by MZ conditions
