# Inferred Host Behavior Change

**Gen3 replacement**: No inferred hosts — processes in containers without a host-level agent have no parent HOST entity in Smartscape.

**Phase 2 required**: no (behavior difference, no migration action required)

## What changes

In Gen2 (classic), when OneAgent monitors a process inside a container but the underlying host has no OneAgent installed, Dynatrace synthesizes an **inferred host** entity. The inferred host appears in the entity model and host inventory so that topology relationships remain visible even without a host-level agent. Customer feedback suggested this caused more confusion than help.

In Gen3 (Smartscape on Grail), inferred hosts are not created. When OneAgent monitors only a process running inside a container on an unmonitored host, that process entity exists in `smartscapeNodes "PROCESS"` but it has no parent `HOST` node. The host does not appear in `smartscapeNodes "HOST"`.

## Impact

- Host inventory queries (`smartscapeNodes "HOST"`) will show fewer hosts than the Gen2 classic entity API if the tenant had inferred hosts.
- Topology traversals from process to host (e.g., `traverse edgeTypes: {runs_on}, targetTypes: {HOST}`) return no result for processes on unmonitored container hosts.
- Host-level metrics (`dt.host.cpu.*`, `dt.host.memory.*`) are not available for inferred hosts — in Gen3. In Gen2 the container's CPU and memory metrics were used in place of unknown host metrics.

## Customer actions

No migration action is required. This is a topology difference customers should be aware of when comparing Gen2 entity counts to Gen3 Smartscape counts.

If a customer needs visibility into the underlying container host:

- **Preferred:** Install OneAgent on the host in `FULL_STACK` mode. This creates a real `HOST` entity with full metrics.
- **Alternative:** Use `DISCOVERY` or `INFRASTRUCTURE` mode OneAgent — creates the host entity and basic topology without code-level monitoring.

## Identifying affected processes

Find processes that have no parent host (likely running on unmonitored container hosts):

```dql
smartscapeNodes "PROCESS"
| fieldsAdd host_ref = references[runs_on.host]
| filter isNull(host_ref) or arraySize(host_ref) == 0
| summarize process_count = count(), by: {name}
| sort process_count desc
```

`references[runs_on.host]` resolves the HOST entity ID directly from any PROCESS — including containerized ones, where the logical path is PROCESS → CONTAINER → HOST. Processes where this is null or empty have no monitored parent host.
