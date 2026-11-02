# Messaging and Queue Usage

**Gen3 replacement**: Service-centric `dt.service.messaging.*` metrics and messaging spans

**Phase 2 required**: yes

Classic `QUEUE` entities have no Phase 3 replacement, and the classic queue metrics stop receiving
new data. Use the bundled `messaging-queue-scanner` to report configurations that reference a
classic queue entity ID or either classic queue metric:

- `builtin:queue.incoming_requests`
- `builtin:queue.outgoing_requests`

This assessment is usage-gated. It reports only exact references found in dashboards, notebooks,
Service-Level Objectives, classic SLOs, Site Reliability Guardians, metric events, and Davis custom
alerts. It does not inventory unused queues, infer usage from metric data, or change the tenant.

## Prerequisites

- Python 3.12+. The scanner is dependency-free and runs directly from `scanner/src`.
- The shared scan layer at `../shared-scripts/config_scan.py`.
- A configured `dtctl` context with access to the configuration sources and Grail.
- Alternatively, a platform token (`dt0s16.*`) with `storage:entities:read`,
  `settings:objects:read`, `document:documents:read`, `document:documents:admin`, and
  `slo:slos:read`.
- Run the assessment before Phase 3 while referenced classic queue entities can still be enriched.

Without `document:documents:admin`, dashboards and notebooks are scanned only as visible to the
current identity and their coverage is reported as partial. Do not request write permissions.

## Instructions

Run the recommended scan using an authenticated `dtctl` context:

```bash
cd scanner
PYTHONPATH=src python3 -m messaging_queue_scanner scan --context <name>
```

Omit `--context` to use the current context. Use `--output-dir <path>` for another report location.

If `dtctl` is unavailable, run the read-only HTTP transport:

```bash
cd scanner
PYTHONPATH=src python3 -m messaging_queue_scanner scan \
  --transport http \
  --tenant https://<environment>.apps.dynatrace.com
```

Set `DT_PLATFORM_TOKEN` rather than placing the token on the command line. Both transports request
tenant-wide document access first. If that permission is unavailable, they scan visible documents,
mark dashboards and notebooks partial, and never return a clean verdict.

The scanner:

- reads all seven source groups representing the five agreed configuration areas;
- removes cached dashboard and notebook query results before matching;
- matches exact uppercase `QUEUE-<16 hexadecimal characters>` IDs and the two exact classic metric
  keys in executable query, selector, and configuration fields;
- enriches only referenced queue IDs with their classic entity details;
- records `complete`, `partial`, or `failed` coverage for every configuration source; and
- writes `summary.json`, a self-contained `report.html`, and `scan-data.json`.

`scan-data.json` stores every referenced queue identity, classic metric key, matching artifact,
field path, and original query or selector, plus the already-fetched body of every affected
configuration. This data can be reused without repeating the tenant-wide usage scan.

Interpret the report verdict as follows:

| Verdict | Meaning | Customer report action |
|---|---|---|
| `affected` | At least one exact queue ID or classic queue metric reference was found | Report every configuration that requires review |
| `clean` | All configuration sources were read completely and no reference was found | Omit messaging and queues from the customer report |
| `incomplete` | No reference was found, but source coverage is incomplete | Report the incomplete assessment; do not claim no usage |

If findings exist alongside an incomplete source, the verdict remains `affected` and the report also
lists the incomplete sources. Re-run those sources before treating the findings as exhaustive.

## Detection

| Source | Matching configuration fields |
|---|---|
| Dashboards and notebooks | Query, DQL, variable, and `state.input` fields; cached `state.result` data is removed |
| Service-Level Objectives | `customSli.indicator` and `sliReference.variables[].value` |
| Classic SLOs | `value.filter` and `value.metricExpression`; `value.metricName` names the metric the SLO produces and is not matched |
| Site Reliability Guardians | Objective `dqlQuery` fields |
| Metric events | Values under `value.queryDefinition` |
| Davis custom alerts | Analyzer input values |

Both SLO generations are scanned, as separate sources: *Service-Level Objectives* is the app
(`dynatrace.service.level.objectives`), read through the platform SLO API, and *Classic SLOs* is the
`builtin:monitoring.slo` settings schema. Second-generation configurations are not migrated on the
customer's behalf, so a classic SLO reading a retired queue metric is reported like any other
configuration. A tenant holding no classic SLOs reports the source as complete with zero objects,
not as incomplete.

`dtctl` 0.30.3 drops `sliReference` from template-based SLOs. The scanner counts those definitions
as unread and marks SLO coverage partial. Use `--transport http` with `slo:slos:read` to read them in
full.

Referenced queue IDs are enriched with:

```dql-template
fetch dt.entity.queue
| filter in(id, array("QUEUE-<ID>"))
| fields id, entity.name, queueName, queueDestinationType, queueVendorName
```

An unresolved ID remains a finding. Enrichment adds context and never gates detection or the
verdict.

## Customer actions

- Review every reported configuration and identify whether it represents publishing, receiving, or
  processing messages.
- Replace queue-entity filters with service and messaging-destination fields that preserve the
  intended scope.
- Replace classic queue metrics with the appropriate `dt.service.messaging.*` metric or a
  span-based query after validating its semantics and thresholds.
- Re-run the scan after resolving any partial or failed source.

The scanner does not mechanically map incoming or outgoing requests to publish, receive, or process.
That choice depends on the original configuration's semantics.

## Examples

Render a sample report without contacting a tenant:

```bash
cd scanner
PYTHONPATH=src python3 -m messaging_queue_scanner demo
```

Rebuild HTML and repair tenant links from an existing `summary.json`:

```bash
cd scanner
PYTHONPATH=src python3 -m messaging_queue_scanner render \
  --output-dir ./messaging-queue-report \
  --ui-url https://<environment>.apps.dynatrace.com
```

Rendering preserves an existing `scan-data.json`; it cannot recreate affected configuration bodies
from `summary.json` alone.

## Outcome

For each affected configuration, the report contains:

- its type, name, ID, and a link that opens it in the tenant;
- every referenced queue ID and classic queue metric key;
- each matching field path and original query or selector;
- resolved queue name, destination type, and vendor when available; and
- the completion state of every configuration source.

The *Referenced queues* table links each resolved queue to its classic entity page
(`/ui/apps/dynatrace.classic.queues/ui/entity/QUEUE-<ID>`). An unresolved ID is left unlinked
because no entity page stands behind it; it remains a finding either way. Both the link and the
classic app it opens disappear with Phase 3, which is the same window the assessment already asks
for.

Unused queues are omitted. A complete scan with no findings omits this topic from the broader
customer report.

## Validation

A `clean` verdict is valid only when all seven source groups are complete. Cached document results
cannot create findings, matching is exact, and queue enrichment is limited to explicitly referenced
IDs.

## References

- [Shared configuration scan](../shared-scripts/README.md)
