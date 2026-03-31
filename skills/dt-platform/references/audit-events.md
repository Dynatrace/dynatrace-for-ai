# Audit Events

Audit trail for all API calls, authentication events, settings changes, and
document operations in `dt.system.events` with
`event.kind == "AUDIT_EVENT"`.

> **High volume.** Filter by `event.provider` or `event.type` to
> narrow scope.

## Contents

- [Discovery Query](#discovery-query)
- [Fields](#fields)
- [Providers](#providers)
- [Event Types](#event-types)
- [Common Workflows](#common-workflows)
- [Best Practices](#best-practices)

## Discovery Query

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "AUDIT_EVENT"
| summarize count = count(), by: {event.provider, event.type}
| sort count desc
```

## Fields

### Common Fields (All Audit Events)

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | timestamp | When the audit record was created |
| `event.kind` | string | Always `"AUDIT_EVENT"` |
| `event.type` | string | HTTP method or operation — see [Event Types](#event-types) |
| `event.provider` | string | Source system — see [Providers](#providers) |
| `event.id` | string | Unique event identifier |
| `event.outcome` | string | HTTP status code (`"200"`, `"201"`, `"403"`) or outcome string (`"success"`) |
| `event.version` | string | Event schema version |
| `user.id` | string | User UUID or `"UNKNOWN"` for token-based access |
| `user.organization` | string | `"CUSTOMER"` or null |
| `authentication.type` | string | `"OAUTH2"` or `"TOKEN"` |
| `origin.address` | string | Source IP address |
| `resource` | string | API path or resource identifier |
| `dt.security_context` | string | Always `"AUDIT_EVENT"` |

### Settings-Specific Fields

Present when `event.provider == "SETTINGS"`:

| Field | Type | Description |
|-------|------|-------------|
| `details.dt.settings.schema_id` | string | Settings schema (e.g., `"builtin:user-appfw-preferences"`) |
| `details.dt.settings.schema_version` | string | Schema version |
| `details.dt.settings.scope_id` | string | Scope of the setting |
| `details.dt.settings.scope_type` | string | Scope type (e.g., `"user"`, `"environment"`) |
| `details.dt.settings.object_id` | string | Settings object ID |
| `details.json_after` | string | JSON state after change |
| `details.json_patch` | string | JSON patch describing the change |
| `details.source` | string | Origin type (e.g., `"rest"`) |
| `origin.type` | string | `"REST"` |
| `dt.app.id` | string | Originating app ID |

## Providers

| Provider | Description |
|----------|-------------|
| `API_GATEWAY` | Platform API calls (GET/POST/PUT/PATCH/DELETE) |
| `CLASSIC_API` | Classic API v1/v2 calls |
| `Hyperscaler authentication` | Cloud provider auth events |
| `SETTINGS` | Settings CRUD with change details |
| `SLO` | SLO operations |
| `DEVOBS_MANAGEMENT` | DevObs breakpoint/project operations |
| `DOCUMENTS` | Document store operations |
| `API_TOKEN` | Token management |
| `APP_REGISTRY` | App install/update events |

## Event Types

### HTTP Method Types (API_GATEWAY, CLASSIC_API)

| Type | Description |
|------|-------------|
| `GET` | Read operations |
| `POST` | Create operations |
| `PUT` | Full update operations |
| `PATCH` | Partial update operations |
| `DELETE` | Delete operations |

### Authentication Types

| Type | Description |
|------|-------------|
| `LOGIN` | User login |
| `LOGOUT` | User logout |

### Settings Types (SETTINGS provider)

| Type | Description |
|------|-------------|
| `CREATE` | New settings object created |
| `UPDATE` | Existing settings object modified |
| `DELETE` | Settings object removed |

### Sharing Types (DOCUMENTS provider)

| Type | Description |
|------|-------------|
| `ENV_SHARE_CREATE` | Environment-level share |
| `DIRECT_SHARE_CREATE` | Direct share to specific users |
| `DIRECT_SHARE_RECIPIENTS_ADD` | Recipients added to share |
| `DIRECT_SHARE_RECIPIENTS_DELETE` | Recipients removed from share |
| `DOCUMENT_METADATA_READ` | Document metadata accessed |
| `DOCUMENT_READ` | Document content accessed |

### DevObs Types (DEVOBS_MANAGEMENT provider)

| Type | Description |
|------|-------------|
| `breakpoint.created` | Debug breakpoint created |
| `breakpoint.updated` | Debug breakpoint modified |
| `breakpoint.deleted` | Debug breakpoint removed |
| `breakpoint.all_deleted` | All breakpoints cleared |
| `project.created` | DevObs project created |
| `project.updated` | DevObs project modified |

### App Registry Types

| Type | Description |
|------|-------------|
| `app.installed` | App installed |
| `app.updated` | App updated |

### Other Types

| Type | Description |
|------|-------------|
| `PERMISSION_NO_CHANGE` | Permission check with no modification |
| `ENABLE` | Resource enabled |
| `DISABLE` | Resource disabled |

## Common Workflows

### API Activity by Provider

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "AUDIT_EVENT"
| summarize request_count = count(), by: {event.provider}
| sort request_count desc
```

### Failed Requests

```dql
fetch dt.system.events, from: -24h
| filter event.kind == "AUDIT_EVENT"
| filter NOT in(event.outcome, "200", "201", "204", "success")
| summarize failures = count(), by: {event.provider, event.type, event.outcome}
| sort failures desc
```

### Settings Changes by Schema

Track configuration changes across the environment:

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "AUDIT_EVENT"
| filter event.provider == "SETTINGS"
| summarize changes = count(), by: {details.dt.settings.schema_id, event.type}
| sort changes desc
```

### User Activity (Top API Consumers)

```dql
fetch dt.system.events, from: -24h
| filter event.kind == "AUDIT_EVENT"
| filter event.provider == "API_GATEWAY"
| summarize request_count = count(), by: {user.id, authentication.type}
| sort request_count desc
| limit 20
```

### Authentication Events Timeline

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "AUDIT_EVENT"
| filter in(event.type, "LOGIN", "LOGOUT")
| summarize logins = count(), by: {timeframe = bin(timestamp, 1d), event.type}
| sort timeframe asc
```

### Token vs OAuth Usage

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "AUDIT_EVENT"
| summarize count = count(), by: {authentication.type}
```

### Specific Settings Schema Audit Trail

```dql-template
fetch dt.system.events, from: -7d
| filter event.kind == "AUDIT_EVENT"
| filter event.provider == "SETTINGS"
| filter details.dt.settings.schema_id == "<SCHEMA_ID>"
| fields timestamp, event.type, user.id, details.dt.settings.scope_id, details.json_patch
| sort timestamp desc
```

### Write Operations by Source IP

Identify external integrations or suspicious access patterns:

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "AUDIT_EVENT"
| filter in(event.type, "POST", "PUT", "PATCH", "DELETE", "CREATE", "UPDATE")
| summarize write_count = count(), by: {origin.address, authentication.type}
| sort write_count desc
| limit 20
```

## Best Practices

1. **Filter by `event.provider` first** — Narrows scope significantly given
   the high volume
2. **Use `event.outcome` for failure analysis** — HTTP status codes for
   API_GATEWAY/CLASSIC_API, `"success"` for SETTINGS
3. **Settings changes include full diff** — `details.json_patch` shows exactly
   what changed; `details.json_after` shows the final state
4. **Token-based access shows `user.id == "UNKNOWN"`** — Use `origin.address`
   and `resource` to identify the integration
5. **Short time ranges recommended** — 24h for activity monitoring, 7d for
   trend analysis
