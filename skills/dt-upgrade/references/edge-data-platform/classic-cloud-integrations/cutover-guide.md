# Cutover Guide

Provider-specific guidance for setting up new cloud connections, validating entities, enabling metrics, and removing classic connections.

---

## Table of Contents

- [1. New Connection Setup — Topology Only](#1-new-connection-setup--topology-only)
- [2. Entity Validation](#2-entity-validation)
- [3. Asset Migration & Alert Strategy](#3-asset-migration--alert-strategy)
- [4. Metric Configuration](#4-metric-configuration)
- [5. Classic Connection Removal](#5-classic-connection-removal)
- [6. Metric Streams Blocking (AWS Only)](#6-metric-streams-blocking-aws-only)

---

## 1. New Connection Setup — Topology Only

**Topology-only mode** = new connection created with metric ingest disabled. Smartscape nodes appear but no metric data flows yet.

Create the new connection with metric ingest disabled. This starts topology ingestion (Smartscape nodes appear) without metric data.

### AWS

**Settings schema:** `builtin:hyperscaler-authentication.connections.aws`

**Authentication:** IAM cross-account role-based or AWS Web Identity. No ActiveGate required.

**Required IAM permissions:** Read-only access to the AWS services being monitored. The IAM role needs permissions for:
- `ec2:Describe*`, `rds:Describe*`, `lambda:List*`, `s3:ListAllMyBuckets`, etc. — for entity discovery
- `cloudwatch:GetMetricData`, `cloudwatch:ListMetrics` — for metric polling (not needed initially when running topology-only, but will be needed when enabling metrics in a later step)

**Topology-only configuration:** The connection's consumer configuration controls what it does. For topology-only:
- The connection must have `SVC:com.dynatrace.da` as a consumer to perform Smartscape topology polling
- Metric ingest can be disabled independently in the connection configuration
- Polling interval: 5 minutes with a 7-minute delay — expect entities to appear within ~12 minutes of setup

**Verify connection via Settings API:**

```
dtctl get settings --schema builtin:hyperscaler-authentication.connections.aws -o json
```

### Azure

**Settings schema:** `builtin:hyperscaler-authentication.connections.azure`

**Authentication:** Federated Identity Credential. No ActiveGate required.

**Required permissions:** Service principal with **Reader** role on target subscriptions.

**Topology-only configuration:** Same consumer model as AWS. Configure with metric ingest disabled initially.

**Polling interval:** 5 minutes with a 5-minute delay — expect entities to appear within ~10 minutes of setup.

**Entity naming:** New entity types follow the pattern `AZURE_MICROSOFT_<PROVIDER>_<RESOURCETYPE>`, derived from ARM resource types. Example: `microsoft.compute/virtualmachines` → `AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINES`. No naming collisions with classic types.

**Verify connection via Settings API:**

```
dtctl get settings --schema builtin:hyperscaler-authentication.connections.azure -o json
```

### GCP

**Settings schema:** `builtin:hyperscaler-authentication.connections.gcp`

**Authentication:** Service account with Viewer role. Entity discovery uses Cloud Asset Inventory.

**Key difference from classic:** The classic GCP integration was a self-hosted GKE workload with no Settings schema. The new connection is fully platform-managed via Settings 2.0 — no GKE deployment required.

**Topology-only configuration:** Same consumer model as AWS/Azure. Configure with metric ingest disabled initially.

**Entity naming:** New entity types follow the pattern `GCP_<SERVICE>_GOOGLEAPIS_COM_<RESOURCE>`. Example: `compute.googleapis.com/Instance` → `GCP_COMPUTE_GOOGLEAPIS_COM_INSTANCE`. This is a complete change from classic, where all GCP entities were `CUSTOM_DEVICE` with `cloud:gcp:*` sub-types.

**Verify connection via Settings API:**

```
dtctl get settings --schema builtin:hyperscaler-authentication.connections.gcp -o json
```

---

## 2. Entity Validation

After setting up the new connection with topology-only, validate that Smartscape nodes have been created for the expected cloud resources.

### Validation Queries

Run these queries to confirm new entities exist. Always specify `from:` explicitly — Smartscape has 35-day retention but DQL defaults to a 2-hour window.

**AWS:**

```dql
smartscapeNodes AWS_ACCOUNT, from:now()-12h
| fields id, name, `aws.account.id`
```

For service-specific validation (examples):

```dql
smartscapeNodes AWS_EC2_INSTANCE, from:now()-12h
| summarize count()
```

```dql
smartscapeNodes AWS_LAMBDA_FUNCTION, from:now()-12h
| summarize count()
```

**Azure:**

```dql
smartscapeNodes AZURE_MICROSOFT_RESOURCES_SUBSCRIPTIONS, from:now()-12h
| fields id, name, `azure.subscription`
```

For service-specific validation (examples):

```dql
smartscapeNodes AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINES, from:now()-12h
| summarize count()
```

**GCP:**

```dql
smartscapeNodes GCP_CLOUDRESOURCEMANAGER_GOOGLEAPIS_COM_PROJECT, from:now()-12h
| fields id, name, `gcp.project.id`
```

For service-specific validation (examples):

```dql
smartscapeNodes GCP_COMPUTE_GOOGLEAPIS_COM_INSTANCE, from:now()-12h
| summarize count()
```

### Comparing Classic vs New Entity Counts

To compare expected (classic) vs actual (new) entity counts, **REQUIRED:** run the classic discovery queries from [discovery-queries.md](discovery-queries.md) alongside the new queries above. Key join fields:

| Provider | Classic field | New field |
|---|---|---|
| AWS | `awsAccountId` | `aws.account.id` |
| Azure | `azureSubscriptionUuid` (via lookup) | `azure.subscription` |
| GCP | `entity.name` | `gcp.project.id` |

### Troubleshooting Missing Entities

If expected entities don't appear:

1. **Check permissions** — the IAM role / service principal / service account may lack access to specific services. If permissions are missing, correct them and re-check after the next polling cycle (~12 minutes). If permissions are confirmed correct and entities still do not appear, proceed to step 2.
2. **Check service enablement** — the connection configuration may not have all required services enabled for topology discovery. Enable the missing services, wait 10 minutes, and re-check. If services are enabled and entities still do not appear, proceed to step 3.
3. **Allow propagation time** — All entity types should appear within 15–30 minutes of connection setup. If entities are not visible after 30 minutes, this is an error state — do not proceed.
4. **Check connection health** — verify the connection is active and not in an error state:

```
dtctl get settings --schema builtin:hyperscaler-authentication.connections.<provider> -o json
```

**Decision:**
- Entities visible and counts match → proceed to next step
- Entities partially visible (some missing) → check service enablement per provider in the sections above; wait 10 min; re-check
- No entities visible after 30 min → check IAM/RBAC permissions first; if correct, escalate to provider support

---

## 3. Asset Migration & Alert Strategy

Apply the remediation output from Stage 3 to migrate dashboards, SLOs, and alerts. This happens **before** enabling metric ingest — migrated dashboards and SLOs referencing new metric keys will not show data yet (this resolves after enabling metrics in the next step).

### Alert Migration Options

Alerts require special handling to avoid double alerting. **Pause and ask the user** which approach they prefer:

> "How would you like to handle alert migration?"
> - **Option 1**: Create new alerts in **disabled** state now. After metric validation in Step 4, simultaneously disable classic alerts and enable new alerts (no alerting gap, no double alerting).
> - **Option 2**: Migrate alerts only **after** the classic connection is disabled in Step 5. This means a brief gap in alerting coverage during the switchover.
>
> The right choice depends on your risk tolerance and environment criticality.

Do **not** proceed without the user's selection.

---

## 4. Metric Configuration

After entities are validated and assets are prepared (Stage 4c/4d in the main skill), enable metric ingest on the new connection.

### Enabling Metrics

Enable metric ingest in the connection configuration in the Dynatrace UI. Once enabled:
- Metric polling starts at the connection's polling interval (5 minutes for all providers)
- New metrics will have `dt.da.source` set (AWS: `aws-metric-poller`, Azure: `azure-metric-poller`, GCP: `gcp-cloud-monitoring`)

### Validating New Metrics

Verify metrics are being ingested using `dt.da.source` as the discriminator:

**AWS:**

```dql
fetch metric.series, from:now()-1h
| filter startsWith(metric.key, "cloud.aws.") AND isNotNull(dt.da.source)
| summarize cnt=count(), by:{metric.key, dt.da.source}
```

**Azure:**

```dql
fetch metric.series, from:now()-1h
| filter startsWith(metric.key, "cloud.azure.") AND dt.da.source == "azure-metric-poller"
| summarize cnt=count(), by:{metric.key}
```

**GCP:**

```dql
fetch metric.series, from:now()-1h
| filter startsWith(metric.key, "cloud.gcp.") AND dt.da.source == "gcp-cloud-monitoring"
| summarize cnt=count(), by:{metric.key}
```

### Parallel Running Notes

During parallel running (both classic and new connections active):
- Both connections ingest data independently — there is no conflict
- Classic metrics and new metrics coexist with different `dt.da.source` values (classic: null, new: populated)
- Classic entity IDs do **not** carry over to new Smartscape nodes — they are separate entity systems
- Dashboards/SLOs migrated to new metric keys will start showing data once metrics are flowing

---

## 5. Classic Connection Removal

After validating that new metrics are flowing and all assets work with new data:

### Step 1: Disable the Classic Connection (Do Not Delete)

Disable the classic connection in the Dynatrace UI. Do **not** delete it yet.

- AWS: Disable via Settings (`builtin:cloud.aws`)
- Azure: Disable via Config API v1 (legacy management)
- GCP: Stop/remove the GKE workload

### Step 2: Re-Validate

1. Re-run connection discovery queries — the account should show status `Complete` (new connection only, no active classic)
2. Re-run dependency scans (Stage 2) — confirm no remaining classic references in active assets
3. Verify all dashboards, SLOs, and alerts are functioning with new data

### Step 3: Observe Buffer Period

Keep the classic connection **disabled but not deleted** for a buffer period (at least one week — adjust based on environment criticality and change management requirements). This allows:
- Quick rollback if issues are discovered after cutover
- Time to identify any missed dependencies that weren't caught in scanning

### Step 4: Delete Only After Buffer Period With No Issues

After the buffer period has elapsed with no issues, delete the classic connection. Before deleting, confirm:
- No rollback requests or incidents traced to the cutover
- No missed dependencies surfaced during the buffer period

Classic metric historical data **remains available** per the environment's retention settings. Deleting the connection:
- Stops new data ingestion from classic polling
- Does **not** delete existing metric, entity, or topology data
- Historical data will age out naturally according to retention policies

---

## 6. Metric Streams Blocking (AWS Only)

AWS accounts using CloudWatch Metric Streams are **partially blocked** from migration.

### What Is Blocked

- Metric Streams is a push-based mechanism (via Kinesis Firehose) that is classic-only
- The new AWS connection does **not yet support** Metric Streams (planned for future)
- Metric Streams metric keys use a distinct format (`cloud.aws.<service>.<camelCase>By<Dim1><Dim2>`) that has no equivalent in the new connection
- Dashboards, alerts, and SLOs referencing Metric Streams metric keys **cannot be migrated yet**

### What Is NOT Blocked

- Classic **built-in polling** metrics on the same account CAN be migrated to the new connection
- Classic **non-built-in polling** metrics on the same account CAN be migrated
- Only the Metric Streams portion is blocked

### Detection

```dql
fetch metric.series, from:now()-12h
| filter dt.source == "AWS Metric Streams"
| summarize cnt=count(), by:`aws.account.id`
```

If this returns results for an account, flag the Metric Streams portion as migration-blocked but proceed with migrating the polling-based metrics for that account.
