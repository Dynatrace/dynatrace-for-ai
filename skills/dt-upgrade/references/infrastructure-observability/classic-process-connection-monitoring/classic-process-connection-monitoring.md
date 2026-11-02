# Classic OneAgent Process Connection Monitoring

**Gen3 replacement**: OneAgent network connection monitoring

**Phase 2 required**: yes

## What changes

Classic process connection monitoring stored connection data in the classic model — not compatible with Grail and not queryable via DQL. New OneAgent network connection monitoring writes structured flow events to the `default_network_flows` Grail bucket, enabling DQL-based investigation with per-connection detail (ports, protocols, direction, bytes, retransmissions, TCP RTT).

Classic connection monitoring will be removed in Phase 3.

## Setting structure

Both monitoring modes are controlled by a single Settings 2.0 object (`builtin:network-connection-monitoring`), overridable at `environment`, `HOST_GROUP`, or `HOST` scope.

| Field | Default | Description |
|---|---|---|
| `enabled` | `true` | Enable new OneAgent network connection monitoring (Grail events) |
| `enabledClassic` | `false` | Enable classic process connection monitoring (not Grail-compatible) |
| `reportedConnections` | `auto` | Which connections to report: `auto` (critical only: connection refused / reset), `all`, or `custom` thresholds |
| `ipFilterMode` | `all` | IP scope: `all`, `private`, `public`, `inclusion`, `exclusion` |
| `aggregation.interval` | `1` | Aggregate similar connections across N minutes (range: 1–10) |
| `aggregation.rateLimit` | `100` | Max connections reported per host per minute |

> Tenants with classic monitoring enabled will have `enabled: false, enabledClassic: true` as their live state, overriding the schema defaults shown above.

## Read current state

```
dtctl get settings --schema builtin:network-connection-monitoring -o json
```

Typical pre-migration output:

```json
{
  "objectId": "<base64-encoded-id>",
  "schemaId": "builtin:network-connection-monitoring",
  "scope": "",
  "value": {
    "enabled": false,
    "enabledClassic": true
  }
}
```

## Apply migration

Export the current setting, edit it, and apply back:

```
dtctl get settings --schema builtin:network-connection-monitoring -o yaml > network-connection-monitoring.yaml
```

Edit `network-connection-monitoring.yaml` to set the target values:

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

Run a dry-run and show the result to the customer. Confirm they are ready to proceed before applying:

```
dtctl apply -f network-connection-monitoring.yaml --dry-run
```

Then apply:

```
dtctl apply -f network-connection-monitoring.yaml
```

Host-group or host overrides follow the same pattern — set `scope` to the HOST_GROUP or HOST entity ID.

### Parallel monitoring

During migration it is valid to run both modes simultaneously: set `enabled: true` and `enabledClassic: true`. This lets you validate that new flow events are arriving in Grail before cutting classic off. Disable classic once the new data is confirmed.

## Best practice: start with `reportedConnections: all`

Classic process connection monitoring was limited and not configurable. New monitoring provides significantly more breadth and depth: every connection is recorded with port, protocol, direction, bytes, packet retransmissions, TCP RTT, and new/reset/timeout session counts — all queryable via DQL. The schema default of `auto` (critical connections only: connection refused / reset) captures a narrow subset of that capability.

Start with `reportedConnections: all` to take full advantage of the new monitoring:

- All connections are recorded, giving complete visibility into process communication patterns, service dependencies, and topology.
- The richer data set enables troubleshooting, capacity analysis, and security use cases that classic monitoring could not support.
- Grail event pricing for network flows is very economical — the cost of `all` is not a reason to restrict.
- The `aggregation.rateLimit` (default: 100/host/min) provides a natural volume cap. Raise it on high-connection-count hosts if events are being dropped.

Tune down to `auto` or `custom` thresholds only after the customer has explored the data and decided they do not need the full connection set.

## Validate new events are flowing

After enabling new monitoring, confirm flow events appear in Grail:

```dql
fetch events, bucket:{"default_network_flows"}, from:now()-1h
| fields flow.start, flow.end, dt.entity.host, dt.entity.process_group_instance,
    network_flow.source.address, network_flow.destination.address,
    network_flow.destination.port, network_flow.network.transport,
    network_flow.bytes.rx, network_flow.bytes.tx
| limit 10
```

If the query returns empty after ~15 minutes, check:
- OneAgents are running and at version 1.337 or later (minimum required for new connection monitoring).
- No HOST or HOST_GROUP scope override is re-disabling new monitoring or re-enabling classic for specific hosts.

## Customer actions

1. Run `dtctl get settings --schema builtin:network-connection-monitoring -o json` to confirm current state.
2. Export, edit, and apply: set `enabled: true`, `enabledClassic: false`, `reportedConnections: all`.
   - Optionally run in parallel first (`enabledClassic: true` alongside `enabled: true`) to validate new data before cutting classic off.
3. Validate new events appear in Grail with the DQL above.
4. After validation, disable classic (`enabledClassic: false`). Tune `reportedConnections` and `ipFilterMode` only if the customer has explored the data and decided they don't need the full connection set.
5. Out-of-the-box dashboards and alerts for connection monitoring ship with standard apps — no manual creation required.

## Tracking queries

Verify the setting state — new enabled, classic disabled:

```
dtctl get settings --schema builtin:network-connection-monitoring -o json
```

Expected post-migration output:

```json
{
  "objectId": "<base64-encoded-id>",
  "schemaId": "builtin:network-connection-monitoring",
  "scope": "",
  "value": {
    "enabled": true,
    "enabledClassic": false,
    "reportedConnections": "all",
    "ipFilterMode": "all",
    "aggregation": {
      "interval": 1,
      "rateLimit": 100
    }
  }
}
```

## References

- [OneAgent network connection monitoring](https://docs.dynatrace.com/docs/shortlink/oneagent-network-connection-monitoring)
