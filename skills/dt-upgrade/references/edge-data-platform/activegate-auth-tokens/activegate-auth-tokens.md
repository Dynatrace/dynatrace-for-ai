# ActiveGate Authentication Tokens

**Gen3 replacement**: --

**Phase 2 required**: yes

## What changes

Phase 3 enforces that all customer-managed ActiveGates authenticate with the Dynatrace cluster using an **ActiveGate token** (`authToken`). The token must be present in the `authorization.properties` file on each AG instance.

Token format:

```
dt0g02.<8-char-public>.<64-char-secret>
```

Example: `dt0g02.ABCD1234.<SECRET>`

The public part is safe to display and log. Treat the secret part like a password — never log or display it.

Starting in Phase 3:

- ActiveGates on version **1.223 or earlier** (token status: **Unsupported**) cannot authenticate and will not connect.
- ActiveGates on version 1.225 or later without a valid token (status: **Absent**, **Invalid**, or **Unknown**) will fail to authenticate.

## Token status reference

Check token status in **Fleet Management > ActiveGates**, filter by **Alert type: Token**.

| Status | Meaning | Action |
|---|---|---|
| **Valid** | AG is authenticating with a valid token | None |
| **Absent** | AG supports tokens but still uses tenant token | Generate and configure a token |
| **Invalid** | Token format is malformed | Generate a new token |
| **Unknown** | Token format is valid but not recognized by the cluster | Generate a new token |
| **Expiring** | Token expires in 30 days or fewer | Rotate the token |
| **Unsupported** | AG is version 1.223 or earlier | Upgrade the AG |

## Prerequisites

- Dynatrace tenant admin access, or a Dynatrace API token with `activeGates:read` and `activeGateTokens:write` scopes (classic Environment API), or a Platform Token with `fleet-management:activegate.tokens:read` and `fleet-management:activegate.tokens:write` scopes (Fleet Management API)
- SSH (Linux) or RDP (Windows) access to AG hosts to update `authorization.properties` and restart the AG service
- AG installer for the latest version, downloaded from the **Fleet Management** app (or **Deploy Dynatrace > ActiveGate** in the tenant UI)

## Instructions

1. Run the tracking queries in the [Validation](#validation) section to identify non-compliant AGs.
2. Check token status in **Fleet Management > ActiveGates**, filter by **Alert type: Token**. Use the status table above to determine the required action per AG.
3. For each AG with status **Unsupported** (version 1.223 or earlier): upgrade it using the AG installer from the **Fleet Management** app (or **Deploy Dynatrace > ActiveGate**). The installer upgrades in-place and preserves configuration. On first connection after upgrade, the cluster automatically replaces the installer's seed token with an individual `authToken` and writes it to `authorization.properties`.
4. For each AG with status **Absent**, **Invalid**, or **Unknown**: generate a new individual token via the **Fleet Management API** (`fleet-management:activegate.tokens:write` scope) or the classic Environment API — `POST /api/v2/activeGateTokens` (see [API reference](https://docs.dynatrace.com/docs/dynatrace-api/environment-api/tokens-v2/activegate-tokens/post-activegate-token)) — then add it to `authorization.properties` (format below) and restart the AG service.
5. For each AG with status **Expiring**: rotate the token by generating a new one, updating `authorization.properties`, and restarting the service.
6. Re-run the validation queries to confirm all AGs are compliant.

> **Containerized AGs** (StatefulSet, Kubernetes Operator): seed tokens cannot be used. Individual tokens must be generated via the **Fleet Management API** (`fleet-management:activegate.tokens:write` scope) or the classic Environment API — `POST /api/v2/activeGateTokens` — and injected as environment variables or mounted secrets — do **not** edit `authorization.properties` directly on containers.

## authorization.properties configuration

**File locations:**

| Platform | Path |
|---|---|
| Linux | `/var/lib/dynatrace/gateway/config/authorization.properties` |
| Windows | `%PROGRAMDATA%\dynatrace\gateway\config\authorization.properties` |

**Single-tenant AG** (tenant section):

```properties
[<tenantUUID>]
authToken = dt0g02.<PUBLIC>.<SECRET>
```

**Multi-tenant AG** (`multitenant` working mode, one AG serving several tenants):

Add `authToken` to **every** tenant section — a section without one stops authenticating in Phase 3, and `mainTenant = true` must appear in exactly one section:

```properties
[<tenantUUID>]
tenantToken = <tenant-token>
authToken = dt0g02.<PUBLIC>.<SECRET>
mainTenant = true

[<tenantUUID2>]
tenantToken = <tenant-token-2>
authToken = dt0g02.<PUBLIC>.<SECRET>
```

**Restart the AG service after any change:**

```sh
# Linux (requires root)
systemctl restart dynatracegateway

# Windows
net stop "Dynatrace Gateway" && net start "Dynatrace Gateway"
```

## Customer actions

- Upgrade every AG on version 1.223 or earlier to the latest version (available from the **Fleet Management** app or **Deploy Dynatrace > ActiveGate** in the tenant UI)
- For each AG with a non-Valid token status: generate a new token, update `authorization.properties`, and restart the AG service
- For containerized AGs: generate individual tokens via API and inject them via environment variables or secrets

## Examples

### All AGs compliant

Version query — all rows `Compliant`. Log query — empty. Fleet Management Token alerts — none.

→ No action needed.

### AGs requiring remediation

Version query output:

| name           | ag_version              | version_status | token_status |
|---|---|---|---|
| ag-prod-eu-01  | 1.346.0.20250101-120000 | Compliant      | Present      |
| ag-staging-01  | 1.200.0.20210301-000000 | Needs upgrade  | Absent       |
| ag-staging-02  | 1.223.0.20210901-000000 | Needs upgrade  | Absent       |

Log query output:

| dt.entity.active_gate | content                                                                | count |
|---|---|---|
| ACTIVEGATE-ABC123     | Invalid authToken property according to its pattern. [tenant=abc, ...] | 47    |

Fleet Management token alerts: `ag-prod-eu-02` — status **Absent**.

→ Upgrade `ag-staging-01` and `ag-staging-02` (version below 1.225).  
→ Generate and configure a new token for `ACTIVEGATE-ABC123` (status **Invalid**) and `ag-prod-eu-02` (status **Absent**).

### Fully remediated

Version query — all `Compliant`. Log query — empty. Fleet Management Token alerts — none.

→ All AGs are Phase 3 ready.

## Outcome

All customer-managed ActiveGates must show token status **Valid** in Fleet Management:
- Running version 1.225 or later.
- `authorization.properties` contains a valid `authToken` (`dt0g02.*.*`).

Output a compliance summary table per AG:

| name | ag_version | version_status | token_status | action |
|---|---|---|---|---|
| ag-prod-eu-01 | 1.346.0.20250101-120000 | Compliant | Present | None |
| ag-staging-01 | 1.223.0.20210901-000000 | Needs upgrade | Absent | Upgrade AG |
| ag-prod-eu-02 | 1.301.0.20240101-000000 | Compliant | Absent | Generate token |

## Validation

**Query 1 — Version and token-presence compliance:**

Uses `smartscapeNodes "ACTIVEGATE"` — the live entity census view. The `dt.active_gate.version` field contains the full build version (e.g. `1.346.0.20250101-120000`); the `substring` call extracts the major.minor portion for comparison. `dt.active_gate.auth_token.id` is `null` when no token is configured.

```dql
smartscapeNodes "ACTIVEGATE"
| fieldsAdd ag_version = dt.active_gate.version,
            auth_token_id = dt.active_gate.auth_token.id,
            is_containerized
| fieldsAdd major_minor = substring(ag_version, from:0, to:indexOf(ag_version, ".", from:5))
| fieldsAdd version_status = if(toDouble(major_minor) >= 1.225, "Compliant", else:"Needs upgrade")
| fieldsAdd token_status = if(isNotNull(auth_token_id), "Present", else:"Absent")
| fields name, ag_version, major_minor, version_status, auth_token_id, token_status, is_containerized
| sort version_status desc, token_status asc
```

**Query 2 — authToken log warnings:**

> ⚠ On large environments this query can scan hundreds of GB. Narrow the timeframe to `from:now()-1h` for a quick check, or filter by a specific `dt.entity.active_gate` ID.

```dql
fetch logs, from:now()-1h
| filter matchesPhrase(content, "Invalid authToken property according to its pattern.")
   OR matchesPhrase(content, "Not all tenants from the 'authorization.properties' file were configured correctly across all tenants.")
| summarize count = count(), by:{dt.entity.active_gate, content}
| sort count desc
```

Remediation is complete when:

- All rows in Query 1 show `version_status = Compliant` and `token_status = Present`.
- Query 2 returns no rows.
- Fleet Management Token alerts show no **Absent**, **Invalid**, **Unknown**, **Expiring**, or **Unsupported** statuses.

## References

- [ActiveGate security](https://docs.dynatrace.com/docs/ingest-from/dynatrace-activegate/activegate-security) — token format, status table, Fleet Management
- [ActiveGate files](https://docs.dynatrace.com/docs/ingest-from/dynatrace-activegate/configuration/where-can-i-find-activegate-files) — file paths on Linux and Windows
- [Stop and restart ActiveGate](https://docs.dynatrace.com/docs/ingest-from/dynatrace-activegate/operation/stop-restart-activegate) — service management commands
- [POST activeGateTokens API](https://docs.dynatrace.com/docs/dynatrace-api/environment-api/tokens-v2/activegate-tokens/post-activegate-token) — generate individual tokens
