# Network Connection Monitoring Configuration

Configuration reference for `builtin:network-connection-monitoring` — the Settings 2.0 object that controls OneAgent network flow data collection.

## Setting Fields

| Field | Default | Description |
|---|---|---|
| `enabled` | `true` | Enable new OneAgent network connection monitoring (writes to `default_network_flows` Grail bucket) |
| `enabledClassic` | `false` | Enable legacy process connection monitoring (not Grail-compatible; not queryable via DQL) |
| `reportedConnections` | `auto` | Which connections to capture: `auto` (failures only: refused/reset), `all`, or `custom` thresholds |
| `ipFilterMode` | `all` | IP scope: `all`, `private`, `public`, `inclusion`, or `exclusion` |
| `aggregation.interval` | `1` | Aggregate similar connections across N minutes (range: 1–10) |
| `aggregation.rateLimit` | `100` | Max connections reported per host per minute |

**Recommended for full visibility:** `enabled: true`, `reportedConnections: all`, `ipFilterMode: all`.

> Grail event pricing for network flows is economical — `reportedConnections: all` is not a cost concern. The `aggregation.rateLimit` (default 100/host/min) provides a natural volume cap; raise it on high-connection-count hosts if events are being dropped.

## Scope

The setting applies at `environment`, `HOST_GROUP`, or `HOST` scope. Environment-level sets the default; scope-level entries override it for specific groups or hosts.

> Tenants that previously used classic monitoring may have scope-level overrides re-enabling `enabledClassic` for specific hosts. Check all scope levels, not just the environment default.

## Read Current State

```
dtctl get settings --schema builtin:network-connection-monitoring -o json
```

## Apply Configuration

Export, edit, and apply back:

```
dtctl get settings --schema builtin:network-connection-monitoring -o yaml > network-connection-monitoring.yaml
```

Edit `network-connection-monitoring.yaml`:

```yaml
objectid: <objectId from export>
schemaid: builtin:network-connection-monitoring
scope: ""
value:
  enabled: true
  enabledClassic: false
  reportedConnections: all
  ipFilterMode: all
  aggregation:
    interval: 1
    rateLimit: 100
```

Dry-run first, then apply:

```
dtctl apply -f network-connection-monitoring.yaml --dry-run
dtctl apply -f network-connection-monitoring.yaml
```

For HOST_GROUP or HOST scope, set `scope` to the entity ID.

## Validate Events Are Flowing

After enabling, confirm events appear (allow ~15 minutes for first events):

```dql
fetch events, bucket:{"default_network_flows"}, from:now()-1h
| fields flow.start, flow.end, dt.entity.host, dt.entity.process_group_instance,
    network_flow.source.address, network_flow.destination.address,
    network_flow.destination.port, network_flow.network.transport,
    network_flow.bytes.rx, network_flow.bytes.tx
| limit 10
```

If empty after 15 minutes:
- Verify OneAgent is version 1.337 or later on the monitored hosts.
- Check for HOST or HOST_GROUP scope overrides that may re-disable new monitoring or re-enable classic.

## References

- [OneAgent network connection monitoring](https://docs.dynatrace.com/docs/shortlink/oneagent-network-connection-monitoring)
