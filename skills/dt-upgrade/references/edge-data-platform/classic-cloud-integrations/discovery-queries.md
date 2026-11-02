# Connection Discovery Queries

All DQL queries for Stage 1 Step 1 (Discover Cloud Connections) and Step 2 (Classify Each Account).

Every query in this document has been verified against real Dynatrace environments. Run them via `dtctl query "<DQL>"`.

---

## Table of Contents

- [1. Classic Connection Discovery](#1-classic-connection-discovery)
- [2. New Connection Discovery (Smartscape)](#2-new-connection-discovery-smartscape)
- [3. AWS Metric Streams Detection](#3-aws-metric-streams-detection)
- [4. Classification Logic](#4-classification-logic)
- [5. New Connection Detection via Settings API](#5-new-connection-detection-via-settings-api)

---

## 1. Classic Connection Discovery

### 1.1 AWS Classic Connections

```dql
fetch dt.entity.aws_credentials, from:now()-12h
| fieldsAdd awsAccountId, entity.name, id, lifetime
| fieldsRemove can_access
```

- One row per classic AWS connection.
- `awsAccountId` — AWS Account ID (numeric string, e.g., `"444652832050"`). **Join key** to new connections.
- `entity.name` — human-readable connection name configured in Dynatrace.
- `id` — Dynatrace entity ID (`AWS_CREDENTIALS-*`).

### 1.2 Azure Classic Connections

```dql
fetch dt.entity.azure_credentials, from:now()-12h
| fieldsAdd entity.name, id, belongs_to
| fieldsRemove can_access
| fieldsAdd sub_id = belongs_to[`dt.entity.azure_subscription`][0]
| lookup [fetch dt.entity.azure_subscription | fieldsAdd azureSubscriptionUuid],
    sourceField:sub_id, lookupField:id, prefix:"sub."
| fields entity.name, id, sub_id, sub.azureSubscriptionUuid
```

- One row per classic Azure credential, with subscription UUID resolved inline.
- `sub.azureSubscriptionUuid` — Azure Subscription ID (e.g., `"7a78220a-..."`). **Join key** to new connections.
- If `belongs_to` is null → `sub_id` will be null. **Action:** include the row in the results with `sub.azureSubscriptionUuid: null` rather than discarding it.

**Syntax notes:**
- `belongs_to` returns a map of arrays keyed by related entity type. Extract the first element with `[0]` to get a scalar for `lookup`.
- `lookup` requires a scalar `sourceField` — extract to an intermediate field (`sub_id`) first.

### 1.3 GCP Classic Connections

```dql
fetch `dt.entity.cloud:gcp:project`, from:now()-12h
| fields entity.name, id, lifetime
```

- One row per active classic GCP project.
- `entity.name` **is the GCP project ID** (e.g., `"my-gcp-project"`). **Join key** to new connections.
- The backtick-quoted entity type is required because of the `:` characters.
- Grail applies `from:` against entity `lifetime` — no explicit filter needed.

---

## 2. New Connection Discovery (Smartscape)

> **Scope required**: `storage:smartscape:read`.
>
> **Timeframe**: Smartscape entities have a 35-day default retention. Without an explicit `from:`, DQL applies a 2-hour default, which will silently exclude accounts not updated recently. Always specify `from:` explicitly.

### 2.1 New AWS Connections

```dql
smartscapeNodes AWS_ACCOUNT, from:now()-12h
| fields id, name, `aws.account.id`
```

- `aws.account.id` — AWS account number (e.g., `"038026236411"`). **Join key** to `awsAccountId` from §1.1.
- `name` — AWS account alias (cloud-side display name, not Dynatrace connection name).

### 2.2 New Azure Connections

```dql
smartscapeNodes AZURE_MICROSOFT_RESOURCES_SUBSCRIPTIONS, from:now()-12h
| fields id, name, `azure.subscription`
```

- `azure.subscription` — Azure Subscription UUID (e.g., `"08b9810e-..."`). **Join key** to `sub.azureSubscriptionUuid` from §1.2.
- `name` — Azure subscription display name (cloud-side).

### 2.3 New GCP Connections

```dql
smartscapeNodes GCP_CLOUDRESOURCEMANAGER_GOOGLEAPIS_COM_PROJECT, from:now()-12h
| fields id, name, `gcp.project.id`
```

- `gcp.project.id` — GCP project ID slug (e.g., `"my-gcp-project"`). **Join key** to `entity.name` from §1.3.
- `name` — GCP project **display name** (NOT the slug). Use `gcp.project.id` as the join key.

---

## 3. AWS Metric Streams Detection

```dql
fetch metric.series, from:now()-12h
| filter dt.source == "AWS Metric Streams"
| summarize cnt=count(), by:`aws.account.id`
```

- Returns AWS account IDs with active Metric Streams traffic.
- If an account appears here, flag it as `not-yet-supported` for the Metric Streams portion.
- Uses the same timeframe as other queries — if the Firehose was paused longer than the window, no accounts will be flagged (intentional).

---

## 4. Classification Logic

After collecting results from §1, §2, and §3, classify each account:

```
For each unique account ID across all queries:
  classic = account ID found in classic query results (§1)
  new     = account ID found in new query results (§2)

  if classic AND new  → status: "Parallel"
  if classic AND !new → status: "Not Started"
  if !classic AND new → status: "Complete"

  if provider == AWS AND account ID in Metric Streams results (§3):
    add flag: "not-yet-supported (Metric Streams)"

  if Metric Streams query returns no results or fails:
    assume Metric Streams not detected for all accounts
    add note to assessment report: "Metric Streams detection inconclusive"
```

### Join Keys Summary

| Provider | Classic field | New field | Type |
|---|---|---|---|
| AWS | `awsAccountId` | `aws.account.id` | Numeric string |
| Azure | `sub.azureSubscriptionUuid` | `azure.subscription` | UUID string |
| GCP | `entity.name` | `gcp.project.id` | Project ID slug |

### Output Format

Present results as:

```
| Provider | Account ID | Connection Name | Status | Migration Blocked |
|----------|-----------|----------------|----------|-------------------|
| AWS      | 123456789 | prod-aws       | Parallel | No                |
| ...      |           |                |          | Yes (AWS Metric Streams) |
| Azure    | 7a78220a-... | prod-azure | Not Started | —              |
| GCP      | my-project | gcp-dev       | Complete | —                  |
```

---

## 5. New Connection Detection via Settings API

Smartscape queries (§2) detect accounts with active topology. For a complete picture — including connections that are configured but unhealthy or have metric polling disabled — also query the Settings API:

### AWS

```
dtctl get settings --schema builtin:hyperscaler-authentication.connections.aws -o json
```

Each object returns: `value.name`, `value.type`, `value.awsRoleBasedAuthentication.roleArn` (contains the AWS account ID), and `value.awsRoleBasedAuthentication.consumers`.

Only connections with `SVC:com.dynatrace.da` as a consumer perform metric and Smartscape polling.

### Azure

```
dtctl get settings --schema builtin:hyperscaler-authentication.connections.azure -o json
```

Each object returns: `value.name`, `value.type`, `value.federatedIdentityCredential.consumers`.

### GCP

```
dtctl get settings --schema builtin:hyperscaler-authentication.connections.gcp -o json
```

Each object returns: `value.name`, `value.type`, connection auth configuration.

> **Note**: Classic connections are NOT in Settings 2.0. AWS classic uses `builtin:cloud.aws`, Azure classic uses the legacy Configuration API (`/api/config/v1/azure/credentials`), and GCP classic has no settings schema at all.
