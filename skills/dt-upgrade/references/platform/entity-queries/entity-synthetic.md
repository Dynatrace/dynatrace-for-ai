# Synthetic Migration Guide

Migrate classic synthetic monitoring entity queries to Smartscape-based equivalents.

## Prerequisites

- Dynatrace tenant in Phase 2 or Phase 3 upgrade
- DQL access (Notebooks or Dashboards)
- Load `dt-dql-essentials` before writing final DQL

## Instructions

### Step 1: Identify the classic synthetic entity type

| Classic entity type | What it represents |
| --- | --- |
| `dt.entity.synthetic_test` | Browser monitor (clickpath or single-URL) |
| `dt.entity.synthetic_test_step` | Individual step within a browser monitor |
| `dt.entity.http_check` | HTTP monitor |
| `dt.entity.http_check_step` | Individual step within an HTTP monitor |
| `dt.entity.multiprotocol_monitor` | Network availability monitor (multi-protocol) |
| `dt.entity.synthetic_location` | Synthetic location (public or private) |

### Step 2: Map to Smartscape node type

| Classic entity type | Smartscape field | Smartscape node type | Status |
| --- | --- | --- | --- |
| `dt.entity.synthetic_test` | `dt.smartscape.browser_monitor` | `BROWSER_MONITOR` | planned |
| `dt.entity.synthetic_test_step` | `dt.smartscape.browser_monitor_step` | `BROWSER_MONITOR_STEP` | planned |
| `dt.entity.http_check` | `dt.smartscape.http_monitor` | `HTTP_MONITOR` | planned |
| `dt.entity.http_check_step` | `dt.smartscape.http_monitor_step` | `HTTP_MONITOR_STEP` | planned |
| `dt.entity.multiprotocol_monitor` | `dt.smartscape.network_availability_monitor` | `NETWORK_AVAILABILITY_MONITOR` | planned |
| `dt.entity.synthetic_location` | `dt.smartscape.synthetic_location` | `SYNTHETIC_LOCATION` | planned |

Smartscape-only nodes with no classic equivalent:

| Smartscape node type | Smartscape field |
| --- | --- |
| `CREDENTIAL_VAULT_ENTRY` | — |
| `SYNTHETIC_ENGINE` | — |

### Step 3: Identify configurations to update

For each entity type, check the following asset types for references to the classic entity ID or type and update them to Smartscape equivalents:

| Entity | dashboard | segment | anomaly-detector | anomaly-detection-metrics | slo | workflow | openpipeline | notebook |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `dt.entity.synthetic_test` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `dt.entity.synthetic_test_step` | ✓ | ✓ | ✓ | | | | | |
| `dt.entity.http_check` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `dt.entity.http_check_step` | ✓ | ✓ | | | ✓ | | | ✓ |
| `dt.entity.multiprotocol_monitor` | ✓ | | ✓ | | | | ✓ | ✓ |
| `dt.entity.synthetic_location` | ✓ | | ✓ | | | | ✓ | ✓ |

### Step 4: Rewrite common DQL constructs

| Classic construct | Smartscape replacement |
| --- | --- |
| `fetch dt.entity.synthetic_test` | `smartscapeNodes BROWSER_MONITOR` |
| `fetch dt.entity.http_check` | `smartscapeNodes HTTP_MONITOR` |
| `fetch dt.entity.multiprotocol_monitor` | `smartscapeNodes NETWORK_AVAILABILITY_MONITOR` |
| `fetch dt.entity.synthetic_location` | `smartscapeNodes SYNTHETIC_LOCATION` |
| `entity.name` | `name` |
| `entityName(dt.entity.synthetic_test)` | `getNodeName(dt.smartscape.browser_monitor)` |
| `dt.entity.synthetic_test` in signal filter | `dt.smartscape.browser_monitor` |
| `dt.entity.http_check` in signal filter | `dt.smartscape.http_monitor` |

### Step 5: Migrate relationship traversal

Classic relationship fields such as `belongs_to[dt.entity.synthetic_location]` must be replaced with `traverse` or `references` using Smartscape edge types.

Use the Smartscape edge table below to determine valid traversal directions and targets:

| Source | Edge | Target | Notes |
| --- | --- | --- | --- |
| `BROWSER_MONITOR` | `runs_on` | `SYNTHETIC_LOCATION` | |
| `HTTP_MONITOR` | `runs_on` | `SYNTHETIC_LOCATION` | |
| `NETWORK_AVAILABILITY_MONITOR` | `runs_on` | `SYNTHETIC_LOCATION` | |
| `BROWSER_MONITOR` | `contains` | `BROWSER_MONITOR_STEP` | |
| `HTTP_MONITOR` | `contains` | `HTTP_MONITOR_STEP` | |
| `BROWSER_MONITOR_STEP` | `belongs_to` | `BROWSER_MONITOR` | |
| `HTTP_MONITOR_STEP` | `belongs_to` | `HTTP_MONITOR` | |
| `BROWSER_MONITOR` | `monitors` | `FRONTEND` | Automatic assignment |
| `BROWSER_MONITOR` | `is_assigned_to` | `FRONTEND` | Manual assignment |
| `HTTP_MONITOR` | `monitors` | `SERVICE` | |
| `HTTP_MONITOR` | `is_assigned_to` | `FRONTEND` | Manual assignment |
| `NETWORK_AVAILABILITY_MONITOR` | `monitors` | `HOST` | |
| `BROWSER_MONITOR` | `uses` | `CREDENTIAL_VAULT_ENTRY` | |
| `HTTP_MONITOR` | `uses` | `CREDENTIAL_VAULT_ENTRY` | |
| `HTTP_MONITOR` | `updates` | `CREDENTIAL_VAULT_ENTRY` | |
| `SYNTHETIC_ENGINE` | `belongs_to` | `SYNTHETIC_LOCATION` | |

**Static vs dynamic edges:**

- **Static** (config/infrastructure-based): `runs_on`, `contains`, `belongs_to` — accessible via `references[edge_type.target_type]` on `smartscapeNodes` and also via `smartscapeEdges`
- **Dynamic** (observed at runtime): `monitors`, `is_assigned_to` — accessible ONLY via `smartscapeEdges` or `traverse`; `references` returns an empty array for dynamic edges. Note: `monitors` is dynamic for synthetic sources specifically; across all Smartscape node types it can be static (e.g. `ONEAGENT→HOST` is static).

## Node Fields

### Base fields (all Smartscape nodes)

| Field | Type | Classic equivalent | Notes |
| --- | --- | --- | --- |
| `id` | smartscapeId | — | Smartscape entity ID |
| `id_classic` | string | entity ID | Bridge to `dt.davis.problems`; do NOT use for timeseries joins (use `id`) |
| `name` | string | `entity.name` | Entity display name |
| `type` | string | `entity.type` | UPPER_SNAKE_CASE |
| `tags` | record | tags array | `tags[key] = [values]` — record type, not array |
| `lifetime` | timeframe | — | `{ start, end }` |
| `references` | record | — | Static edges; use `references[edge_type.target_type]` directly (e.g. `fieldsAdd x = references[belongs_to.host]`) — no prior `fieldsAdd references` step needed |

### Synthetic monitor interface fields (all monitor types)

| Field | Classic equivalent |
| --- | --- |
| `enabled` | — |
| `deleted` | — |
| `frequency` | — |
| `dt.security_context` | `securityContext` (always `string[]`) |
| `last_successful_execution_timestamp` | — |
| `last_failed_execution_timestamp` | — |
| `creation_timestamp` | — |

### Per-type fields

| Field | Node type | Classic equivalent |
| --- | --- | --- |
| `http_monitor.type` | `HTTP_MONITOR` | `httpMonitorSubtype` (`"HTTP"` or `"HIGH_RESOURCE"`) |
| `network_monitor.type` | `NETWORK_AVAILABILITY_MONITOR` | `multiProtocolMonitorSubtype` (`"ICMP"`, `"TCP"`, …) |
| `device_profile` | `BROWSER_MONITOR` | `deviceProfile` |

### SYNTHETIC_LOCATION extra fields

| Field | Classic equivalent |
| --- | --- |
| `cloud.provider` | `cloudProvider` |
| `location_type` | `locationType` (`PUBLIC` or `PRIVATE`) |
| `deployment_type` | `deploymentType` |
| `geo.continent.name` / `geo.country.name` / `geo.city.name` | — |
| `geo.location.latitude` / `geo.location.longitude` | — |
| `deleted` | `isDeleted` |

### BROWSER_MONITOR_STEP / HTTP_MONITOR_STEP extra fields

| Field | Node type | Classic equivalent | Notes                                                       |
| --- | --- | --- |-------------------------------------------------------------|
| `name` | `BROWSER_MONITOR_STEP` | `entity.name` on `dt.entity.synthetic_test_step` | Step display name (e.g. `"Loading of..."`, `"click on..."`) |
| `name` | `HTTP_MONITOR_STEP` | `entity.name` on `dt.entity.http_check_step` | Step display name                                           |
| `step.sequence_number` | both | — | Order within monitor (from 0)                               |
| `http.request.method` | `HTTP_MONITOR_STEP` | — | HTTP method (e.g. `"GET"`, `"POST"`)                        |
| `step.url` | `HTTP_MONITOR_STEP` | — | URL checked                                                 |
| `dt.synthetic.step.type` | `BROWSER_MONITOR_STEP` | — | Step action type (e.g. `"navigate"`, `"click"`)             |
| `screenshot.thumbnail_uri` | `BROWSER_MONITOR_STEP` | — | The screenshot thumbnail URI of the step                    |

### Type conversion

Verified on `HTTP_MONITOR`: `enabled` and `deleted` are returned as `boolean`, `frequency` as `long` — explicit casts are not required and `filter enabled == true` works as-is. If you encounter type mismatches on other node types or in older tenant versions, `toBoolean()`/`toLong()` can be used defensively:

| Field | Optional cast |
| --- | --- |
| `deleted` | `toBoolean(deleted)` |
| `enabled` | `toBoolean(enabled)` |
| `frequency` | `toLong(frequency)` |

### Classic field → Smartscape field name changes

| Classic field | Smartscape field |
| --- | --- |
| `locationType` | `location_type` |
| `isDeleted` | `deleted` |
| `isEnabled` | `enabled` |
| `syntheticMonitorFrequency` | `frequency` |
| `httpMonitorSubtype` | `http_monitor.type` |
| `multiProtocolMonitorSubtype` | `network_monitor.type` |
| `deviceProfile` | `device_profile` |
| `securityContext` | `dt.security_context` |
| `entity.name` | `name` |

## Key DQL Rules

### toSmartscapeId() is a type cast only

`toSmartscapeId(value)` changes the type from `string` to `smartscapeId` — it does NOT rename the prefix. `toSmartscapeId("HTTP_CHECK-ABC")` still returns `HTTP_CHECK-ABC`. To convert a classic entity ID to its Smartscape node ID, rename the prefix with `replaceString()` first, then wrap with `toSmartscapeId()`:

```dql-snippet
toSmartscapeId(replaceString(field, "HTTP_CHECK-", "HTTP_MONITOR-"))
```

**Classic → Smartscape prefix rename table:**

| Classic prefix | Smartscape prefix |
| --- | --- |
| `SYNTHETIC_TEST-` | `BROWSER_MONITOR-` |
| `HTTP_CHECK-` | `HTTP_MONITOR-` |
| `MULTIPROTOCOL_MONITOR-` | `NETWORK_AVAILABILITY_MONITOR-` |
| `SYNTHETIC_LOCATION-` | `SYNTHETIC_LOCATION-` (unchanged) |
| `HOST-` | `HOST-` (unchanged) |

### Tags filtering

`tags` on `smartscapeNodes` is a `record`, not an array. Classic tag filter patterns do not apply:

- `in(string, record)` — does NOT work (DQL warns, returns null)
- `tags["key"]` (string literal in brackets) — parse error; use an unquoted key instead

For known, static tag keys use bracket access with an unquoted identifier:

```dql-snippet
| filter tags[env] == "production"
```

For context-qualified tags (e.g. from Kubernetes labels or auto-tagging rules) use the backtick-quoted context prefix:

```dql-snippet
| filter `tags:k8s.labels`[team] == "payments"
```

Use `contains(toString(tags), $TagVariable)` only when the key itself is a dashboard variable and cannot be expressed as a static identifier:

```dql-snippet
| filter $MonitorTag == "*" or contains(toString(tags), $MonitorTag)
```

### References for static edges only

`references[edge_type.target_type]` works only for static edges (`runs_on`, `contains`, `belongs_to`). For dynamic edges (`monitors`, `is_assigned_to`), use `smartscapeEdges` or `traverse`.

### Timeframe scoping

`smartscapeNodes` and `smartscapeEdges` accept `from:` / `to:` params. When a related entity may be older than the query window (e.g. a FRONTEND assigned to a monitor long ago), widen the window:

```dql
smartscapeNodes FRONTEND, from:-180d
```

## entityAttr() Replacement Patterns

`entityAttr()` is not supported in Smartscape queries. The replacement depends on query type — see [dql-function-migration.md](dql-function-migration.md#entityattr) for the general rule:

- **Signal queries** (`timeseries`, `fetch logs`, etc.): use `getNodeField(dt.smartscape.<type>, "field")`
- **Node queries** (`smartscapeNodes`): access the field directly (`name`, `tags`, etc.)
- **Mid-migration node queries** where only a classic `dt.entity.*` dimension is available: use a `lookup` to `smartscapeNodes` joined on `id_classic` (see below)

**Signal query — `getNodeField`:**

```dql-snippet
// BEFORE
| fieldsAdd monitor_tags = entityAttr(dt.entity.synthetic_test, "tags")

// AFTER (once dt.smartscape.browser_monitor is available as a signal dimension)
| fieldsAdd monitor_tags = getNodeField(dt.smartscape.browser_monitor, "tags")
```

**Node query — direct field access:**

Inside a `smartscapeNodes` pipeline the attributes are available as plain fields:

```dql-snippet
| fields name, tags
```

**Mid-migration lookup (classic dimension only):**

Use when the signal still carries a classic `dt.entity.*` dimension and no Smartscape equivalent is present yet.

Single attribute:

```dql-snippet
| lookup [smartscapeNodes BROWSER_MONITOR | fields id_classic, monitor_tags = tags],
  sourceField:dt.entity.synthetic_test, lookupField:id_classic, fields:{monitor_tags}
```

Multiple attributes — combine into one lookup:

```dql-snippet
| lookup [smartscapeNodes BROWSER_MONITOR | fields id_classic, monitor_tags = tags, monitor_name = name],
  sourceField:dt.entity.synthetic_test, lookupField:id_classic, fields:{monitor_tags, monitor_name}
```

Location `cloudProvider` and `name`:

```dql-snippet
| lookup [smartscapeNodes SYNTHETIC_LOCATION | fields id_classic, location = name, cloud_provider = cloud.provider],
  sourceField:dt.entity.synthetic_location, lookupField:id_classic, fields:{location, cloud_provider}
```

With type hint (e.g. `entityAttr(entity, type:"dt.entity.application", "entity.name")`):

```dql-snippet
| lookup [smartscapeNodes FRONTEND | fields id_classic, entity_name = name],
  sourceField:entity, lookupField:id_classic, fields:{entity_name}
```

**Classic attribute → Smartscape field:**

| Classic attribute in `entityAttr()` | Smartscape field | Node type |
| --- | --- | --- |
| `"entity.name"` | `name` | any |
| `"cloudProvider"` | `cloud.provider` | `SYNTHETIC_LOCATION` |
| `"tags"` | `tags` | any |
| `"id"` | alias directly — no lookup needed | any |

## Dual-Mode Query Pattern

When a tenant is mid-migration, timeseries data exists under both `dt.entity.*` (classic) and `dt.smartscape.*` (Smartscape) dimensions depending on when it was ingested. Query both and normalize to a single Smartscape ID with `coalesce`:

```dql
timeseries {sumAV = sum(dt.synthetic.browser.availability), cntAV = count(dt.synthetic.browser.availability)},
  by: {dt.entity.synthetic_test, dt.smartscape.browser_monitor}
| filter dt.entity.synthetic_test == "SYNTHETIC_TEST-BF77450C45A51AE4"
    or dt.smartscape.browser_monitor == toSmartscapeId("BROWSER_MONITOR-BF77450C45A51AE4")
| fieldsAdd monitor_id = coalesce(
    dt.smartscape.browser_monitor,
    toSmartscapeId(replaceString(toString(dt.entity.synthetic_test), "SYNTHETIC_TEST", "BROWSER_MONITOR"))
  )
| summarize availability = sum(sumAV[]) / sum(cntAV[]), by: {timeframe, interval, monitor_id}
```

**Every `dt.entity.*` field used in `coalesce()` or `fieldsAdd` MUST appear in the timeseries `by:{}` block**, otherwise DQL throws `FIELD_DOES_NOT_EXIST`.

For NAM (NETWORK_AVAILABILITY_MONITOR) — three dimensions need dual-mode treatment:

```dql
timeseries {sumAv = sum(dt.synthetic.multi_protocol.availability), cntAv = count(dt.synthetic.multi_protocol.availability)},
  by: {
    dt.smartscape.network_availability_monitor, dt.entity.multiprotocol_monitor,
    dt.smartscape.synthetic_location, dt.entity.synthetic_location,
    dt.smartscape.host, dt.entity.host
  }
| fieldsAdd monitor_id = coalesce(
    dt.smartscape.network_availability_monitor,
    toSmartscapeId(replaceString(toString(dt.entity.multiprotocol_monitor), "MULTIPROTOCOL_MONITOR", "NETWORK_AVAILABILITY_MONITOR"))
  )
| fieldsAdd location_id = coalesce(
    dt.smartscape.synthetic_location,
    toSmartscapeId(toString(dt.entity.synthetic_location))
  )
| fieldsAdd host_id = coalesce(
    dt.smartscape.host,
    toSmartscapeId(toString(dt.entity.host))
  )
| summarize availability = sum(sumAv[]) / sum(cntAv[]), by: {timeframe, interval, monitor_id, location_id, host_id}
```

**Nested timeseries subqueries** need their own `coalesce` block — fields defined in the outer query are not visible inside a nested `lookup [ timeseries ... ]`.

## Examples

### Example 1: List all browser monitors

Classic:

```dql
fetch dt.entity.synthetic_test
| fields entity.name, id
```

Smartscape:

```dql
smartscapeNodes BROWSER_MONITOR
| fields entity.name = name, id
```

### Example 2: List all HTTP monitors

Classic:

```dql
fetch dt.entity.http_check
| fields entity.name, id
```

Smartscape:

```dql
smartscapeNodes HTTP_MONITOR
| fields entity.name = name, id
```

### Example 3: Filter synthetic timeseries by monitor type

| Monitor type | Metric |
| --- | --- |
| Browser (`SYNTHETIC_TEST`) | `dt.synthetic.browser.availability` |
| HTTP (`HTTP_CHECK`) | `dt.synthetic.http.availability` |
| NAM (`MULTIPROTOCOL_MONITOR`) | `dt.synthetic.multi_protocol.availability` |

Classic (browser monitor, inline entity filter):

```dql
timeseries avg(dt.synthetic.browser.availability),
  filter: { dt.entity.synthetic_test == "SYNTHETIC_TEST-ABC123" }
```

Smartscape (browser monitor, Smartscape field in signal filter):

```dql
timeseries avg(dt.synthetic.browser.availability),
  filter: { dt.smartscape.browser_monitor == toSmartscapeId("BROWSER_MONITOR-ABC123") }
```

Classic (HTTP monitor, inline entity filter):

```dql
timeseries avg(dt.synthetic.http.availability),
  filter: { dt.entity.http_check == "HTTP_CHECK-ABC123" }
```

Smartscape (HTTP monitor, Smartscape field in signal filter):

```dql
timeseries avg(dt.synthetic.http.availability),
  filter: { dt.smartscape.http_monitor == toSmartscapeId("HTTP_MONITOR-ABC123") }
```

Classic (NAM, inline entity filter):

```dql
timeseries avg(dt.synthetic.multi_protocol.availability),
  filter: { dt.entity.multiprotocol_monitor == "MULTIPROTOCOL_MONITOR-ABC123" }
```

Smartscape (NAM, Smartscape field in signal filter):

```dql
timeseries avg(dt.synthetic.multi_protocol.availability),
  filter: { dt.smartscape.network_availability_monitor == toSmartscapeId("NETWORK_AVAILABILITY_MONITOR-ABC123") }
```

### Example 4: List monitors with their location (static edge via references)

```dql
smartscapeNodes BROWSER_MONITOR
| fieldsAdd locations = references[runs_on.synthetic_location]
| fields entity.name = name, id, locations
```

### Example 5: Resolve location names via smartscapeEdges (dynamic-safe)

```dql
smartscapeNodes HTTP_MONITOR
| fields id, name
| lookup [
  smartscapeEdges runs_on
  | filter source_type == "HTTP_MONITOR" and target_type == "SYNTHETIC_LOCATION"
  | fieldsAdd locName = getNodeName(target_id), provider = getNodeField(target_id, "cloud.provider")
  | summarize {locations = collectArray(target_id), locationLabels = collectArray(locName)}, by:{source_id}
], sourceField:id, lookupField:source_id, fields:{locations, locationLabels}
```

### Example 6: Step → parent monitor bridge

```dql-snippet
| lookup [
  smartscapeEdges belongs_to
  | filter source_type == "HTTP_MONITOR_STEP" and target_type == "HTTP_MONITOR"
  | summarize monitor_id = takeFirst(target_id), by:{source_id}
], sourceField:dt.smartscape.http_monitor_step, lookupField:source_id, fields:{monitor_id}
| lookup [smartscapeNodes HTTP_MONITOR | fields id, monitor_tags = tags],
  sourceField:monitor_id, lookupField:id, fields:{monitor_tags}
```

## References

- Full type and field mapping table: `type-mappings.md`
- End-to-end migration workflow: `migration-workflow.md`
- Filtering mass data (timeseries/logs) by entity: `mass-data-filtering-strategy.md`
- DQL function rewrites (`entityName`, `entityAttr`, selectors): `dql-function-migration.md`
