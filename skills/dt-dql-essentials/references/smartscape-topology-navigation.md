# Smartscape Topology Navigation

Navigate entity relationships using `traverse`, `smartscapeNodes` and `smartscapeEdges`.

## Table of Contents

- [Method Selection](#method-selection)
- [Node Types](#node-types)
- [Relationship Types](#relationship-types)
- [Traverse Syntax](#traverse-syntax)
- [Task: Multi-Hop Traversal](#task-multi-hop-traversal)
- [Task: Quick Relationship Lookup](#task-quick-relationship-lookup)
- [Task: Discover Edge Types](#task-discover-edge-types)
- [Task: Debug Empty Traversal Results](#task-debug-empty-traversal-results)
- [Common Patterns](#common-patterns)
- [Guidelines](#guidelines)

## Method Selection

| Task                            | Method            | Query Pattern                                                            |
| ------------------------------- | ----------------- | ------------------------------------------------------------------------ |
| Entity lookup / traversal start | `smartscapeNodes` | `smartscapeNodes "<TYPE>"` → `filter` / `traverse`                       |
| Discover node types             | `smartscapeNodes` | `smartscapeNodes "*"` → `dedup type`                                     |
| Discover edge types per node    | `smartscapeEdges` | `smartscapeEdges "*"` → `filter source_type` → `dedup type, target_type` |
| Multi-hop walk                  | `traverse`        | Chain multiple `traverse` commands                                       |
| Discover / verify edge types    | `smartscapeEdges` | Query before traverse                                                    |
| Empty results debug             | `smartscapeEdges` | Verify edge types exist                                                  |

**CRITICAL:** Wrong edge types return empty results (no error). Always validate for unfamiliar entities.

______________________________________________________________________

## Node Types

Node types are uppercase strings (e.g. `"HOST"`, `"SERVICE"`, `"K8S_POD"`). Entity IDs follow the pattern `<TYPE>-<HEX>` (e.g. `HOST-ABC123`).

- Use wildcard `*` to select all types of `smartscapeNodes`.
- Use partial wildcard matching such as
  - `AWS_*` to select all types starting with "AWS_" (AWS resources)
  - `*_CLUSTER` to select all types ending with "_CLUSTER"
  - `*_ELASTIC*` to select all types containing the substring "_ELASTIC".
  - Wildcard `*` is non-exclusive, i.e. also matches if there's no symbol preceding/following.

**Discover all node types in the environment:**

```dql
smartscapeNodes "*"
| dedup type
| fields type
```

**CRITICAL:** Wrong node types return empty results (no error). Always validate for unfamiliar entities.

### Tags and Labels

All cloud tags and Kubernetes labels/annotations are available on nodes via the `tags` field. Use backticks for label keys containing special characters (dots, slashes). For comprehensive Kubernetes label/annotation query patterns, see the [`dt-obs-kubernetes` skill's `labels-annotations` reference](../../../skills/dt-obs-kubernetes/references/labels-annotations.md).

## Relationship/Edge Types

The first argument to `smartscapeEdges` is the edge type name (e.g., `"calls"`, `"runs_on"`) or `"*"` (also supports partial wildcard matching) for all edge types — unlike `smartscapeNodes` where the argument is the node type. An edge type describes a type of relationship or dependency between two `smartscapeNodes`. The table below provides common edge types. However, note that there may be more edge types available in the environment. Always explore available edge types if uncertain.

| Edge Type        | Description                                                       | Opposite       | Examples                                                                              |
| ---------------- | ----------------------------------------------------------------- | -------------- | ------------------------------------------------------------------------------------- |
| `balanced_by`    | Load balancer relationship                                        | `balances`     |                                                                                       |
| `balances`       | Target balances source                                            | `balanced_by`  |                                                                                       |
| `belongs_to`     | Many-to-many without existential dependency (UML aggregation)     | `contains`     | SERVICE → K8S_CLUSTER, K8S_POD → K8S_NAMESPACE                                        |
| `calls`          | Horizontal communication between entities, no structural relation | —              | SERVICE → SERVICE, SERVICE → DATABASE                                                 |
| `contains`       | Parent contains children                                          | `belongs_to`   |                                                                                       |
| `instance_of`    | Instance-of-template relationship                                 | `instantiates` |                                                                                       |
| `is_attached_to` | Exclusively attached (1-to-many)                                  | —              | AWS_EBS_VOLUME → AWS_EC2_INSTANCE, AZURE_NETWORK_INTERFACE → AZURE_VIRTUAL_SUBNETWORK |
| `is_part_of`     | Composition (UML); child cannot exist without parent              | —              | AWS_EC2_INSTANCE → AWS_AUTOSCALING_GROUP, K8S_POD → K8S_DEPLOYMENT                    |
| `monitors`       | Monitoring OneAgent observes a monitored entity                   | —              | ONEAGENT → HOST                                                                       |
| `routes_to`      | Network routing relationship                                      | —              | ROUTE_TABLE → NAT_GATEWAY, VPC_PEERING → VPC, K8S_INGRESS → K8S_SERVICE               |
| `runs_on`        | Vertical "runs on" association, no composition implied            | —              | SERVICE → K8S_POD, CONTAINER → HOST                                                   |
| `uses`           | Loose usage dependency (opposite direction of `is_attached_to`)   | —              | K8S_POD → K8S_CONFIGMAP, ASG → LAUNCH_TEMPLATE                                        |

### Static vs Dynamic Edges

Edges are either **static** (infrastructure/config-based) or **dynamic** (observed at runtime). Use the hidden field `dt.system.edge_kind` via `fieldsAdd` on `smartscapeEdges` to verify whether an edge is `"static"` or `"dynamic"` in your environment.

**Get an overview of all Smartscape edges for all node types:**

```dql
smartscapeEdges "*"
| summarize count(), by:{ source_type, type, target_type, dt.system.edge_kind }
```

**List all edge types for a given node type:**

```dql
smartscapeEdges "*"
| filter source_type == "HOST" or target_type == "HOST"
| dedup type, source_type, target_type
| fields source_type, type, target_type
```

______________________________________________________________________

## Traverse Syntax

Parameters should always be wrapped in curly braces `{}`.

**Full syntax:**

```dql-template
smartscapeNodes <SOURCE_TYPE>
| traverse edgeTypes: {<EDGE_TYPE>}, targetTypes: {<TARGET_TYPE>}, direction: <forward|backward>
```

**Short syntax:**

The `edgeTypes:` and `targetTypes:` keywords can be omitted. `direction` defaults to `forward`.

```dql-snippet
smartscapeNodes "<SOURCE_TYPE>"
| traverse {"<EDGE_TYPE>"}, {"<TARGET_TYPE>"}
```

**CRITICAL:** Always prefer the full syntax for clarity.


| Parameter     | Values                                           | Usage                                             |
| ------------- | ------------------------------------------------ | ------------------------------------------------- |
| `edgeTypes`   | `{EDGE_TYPE}` or `{"*"}` or partial wildcard     | Edge type to follow                               |
| `targetTypes` | `{NODE_TYPE}` or `{"*"}` or partial wildcard     | Target node type                                  |
| `direction`   | `forward` or `backward`                          | forward = source→target, backward = source←target |
| `fieldsKeep`  | `{field1, field2}`                               | Preserve fields across hops                       |


**Multiple Node Types and/or Edge Types:**

Multiple node types and edge types can be used in a single query. Results contain all possible combinations of `<SOURCE_TYPE_*>`, `<EDGE_TYPE_*>`, `<TARGET_TYPE_*>`.

```dql-template
smartscapeNodes <SOURCE_TYPE_1>, <SOURCE_TYPE_2>
| traverse edgeTypes: {<EDGE_TYPE_1>, <EDGE_TYPE_2}, targetTypes: {<TARGET_TYPE_3>, <TARGET_TYPE_4>}, direction: <forward|backward>
```

**Accessing Traversal History/Path:**

Use the `dt.traverse.history` array of records to access the history of a traversal. For example:

- `dt.traverse.history[1]` returns the edge (`id`, `edge_type`, `direction`) of the first hop in a potential sequence of hops,
- ``dt.traverse.history[-1][`id`]`` returns the id of the target smartscape node of the last edge,
- ``dt.traverse.history[-2][`edge_type`]`` returns the edge type of the last but one edge.

### Direction Patterns

The following table provides examples of directional patterns:

| Pattern                    | Direction         | Use Case                                               |
| -------------------------- | ----------------- | ------------------------------------------------------ |
| Instance → Security Groups | `forward`         | What does this use?                                    |
| Security Group ← Instances | `backward`        | What uses this?                                        |
| Instance → Subnet → VPC    | `forward` (chain) | Follow dependencies                                    |
| VPC ← Resources            | `backward`        | Find all in VPC                                        |
| Service → Service          | `forward`         | Find horizontal Service-to-Service "calls" connections |

______________________________________________________________________

## Task: Multi-Hop Traversal

Same-direction 2-hop traversal:

```dql
smartscapeNodes "AWS_EC2_INSTANCE"
| filter aws.resource.id == "i-ABC123"
| traverse edgeTypes: {is_attached_to}, targetTypes: {AWS_EC2_SUBNET}
| traverse edgeTypes: {is_attached_to}, targetTypes: {AWS_EC2_VPC}
| fields vpc_id = id, vpc_name = name
```

In order to find entities that share a common dependency with the source node, combine `forward` and `backward` in a single chain (mixed-direction 2-hop query e.g. forward → backward).

**Preserve source fields:**

Use `fieldsKeep` to preserve fields from the origin of the traverse.

```dql
smartscapeNodes "AWS_EC2_INSTANCE"
| traverse edgeTypes: {is_attached_to}, targetTypes: {AWS_EC2_SUBNET}, fieldsKeep: {lifetime}
| fields id, ec2_lifetime=lifetime
```

**Access history (previous hops):**

```dql
smartscapeNodes "AWS_ELASTICLOADBALANCINGV2_LOADBALANCER"
| traverse edgeTypes: {balanced_by}, targetTypes: {AWS_ELASTICLOADBALANCINGV2_TARGETGROUP}, direction: backward
| traverse edgeTypes: {balances}, targetTypes: {AWS_EC2_INSTANCE}
| fields dt.traverse.history[-1], dt.traverse.history[-2]
```

______________________________________________________________________

## Task: Forward Static Relationship Lookup without Traversal

**CRITICAL:**
- The `references` field only contains **forward, static** edges (e.g. infrastructure config-based relationships like PROCESS `runs_on` HOST).
- It does **not** contain **dynamic** edges (e.g. SERVICE `calls` SERVICE) or **backward** edges (where the node is the target). For discovering dynamic or backward edges, use `traverse` or `smartscapeEdges` instead.

To verify whether an edge is static or dynamic before relying on `references`, query `dt.system.edge_kind`:

```dql
smartscapeEdges "<EDGE_TYPE>"
| summarize count(), by: {dt.system.edge_kind}
```

**Method:** `references` field

**Key syntax:**
- Nested fields in `references` follow the pattern ``references[`<edge_type>.<target_type>`]`` where `<edge_type>` is the relationship (e.g. `runs_on`) and `<target_type>` is the lowercase target node type (e.g. `host`).
  - Example: ``references[`runs_on.host`]``.
  - Reference keys use the format `<edge_type>.<target_type>` (lowercase). Use backticks for keys with dots: ``references[`runs_on.host`]``, ``references[`uses.aws_ec2_securitygroup`]``.
- `references` always returns arrays. Use `[0]` when the relationship is known to be 1:1.

**Discover structure:**

```dql
smartscapeNodes "K8S_POD" | limit 1 | fieldsAdd references
```

**Extract specific relationships:**

```dql
smartscapeNodes "HOST"
| fieldsAdd references
| fields
    id,
    vm = references[`runs_on.aws_ec2_instance`]
```

**Look up the name of a referenced node:**

`getNodeName` can be used on any smartscape ID object to retrieve the more human-friendly name.

```dql
smartscapeNodes "HOST"
| fields
    id,
    vm_name = getNodeName(references[`runs_on.aws_ec2_instance`][0])
```

**Expand to rows:**

```dql
smartscapeNodes "AWS_EC2_INSTANCE"
| fieldsAdd sg_ids = references[`uses.aws_ec2_securitygroup`]
| expand sg_ids
```

**Count relationships:**

```dql
smartscapeNodes "AWS_EC2_INSTANCE"
| fieldsAdd sg_count = arraySize(references[`uses.aws_ec2_securitygroup`])
| summarize avg_sgs = avg(sg_count)
```

______________________________________________________________________

## Task: Discover Edge Types

**Find outgoing edges (FROM entity):**

```dql
smartscapeEdges "calls"
| filter source_id == toSmartscapeId("SERVICE-XYZ")
| fields type, target_type
```

**Find incoming edges (TO entity):**

```dql
smartscapeEdges "calls"
| filter target_id == toSmartscapeId("SERVICE-XYZ")
| fields type, source_type
```

______________________________________________________________________

## Task: Debug Empty Traversal Results

| Issue           | Check             | Solution                                               |
| --------------- | ----------------- | ------------------------------------------------------ |
| Empty results   | Edge type exists? | Query `smartscapeEdges` first                          |
| Wrong direction | Try opposite      | Switch `forward` ↔ `backward`                          |
| Typo            | Spelling          | Check reference markdowns to understand field spelling |
| Wrong target    | Entity type       | Verify with `smartscapeNodes`                          |

______________________________________________________________________

## Common Patterns

### Process → Container → K8S Pod (Process to Kubernetes Pod)

```dql
smartscapeNodes "PROCESS"
| filter id == toSmartscapeId("PROCESS-XYZ")
| traverse edgeTypes: {runs_on}, targetTypes: {CONTAINER}
| traverse edgeTypes: {is_part_of}, targetTypes: {K8S_POD}
```

### Service Dependency Chain

```dql
smartscapeNodes "SERVICE"
| filter id == toSmartscapeId("SERVICE-XYZ")
| traverse edgeTypes: {calls}, targetTypes: {SERVICE}
| fields downstream_id = id, downstream_name = name
```

### Kubernetes: Pod → Node → Cluster

```dql
smartscapeNodes "K8S_POD"
| filter id == toSmartscapeId("K8S_POD-XYZ")
| traverse edgeTypes: {runs_on}, targetTypes: {K8S_NODE}
| traverse edgeTypes: {belongs_to}, targetTypes: {K8S_CLUSTER}
| fields cluster_id = id, cluster_name = name
```

### Load Balancer → Instances

```dql
smartscapeNodes "AWS_ELASTICLOADBALANCINGV2_LOADBALANCER"
| traverse edgeTypes: {balanced_by}, targetTypes: {AWS_ELASTICLOADBALANCINGV2_TARGETGROUP}, direction: backward
| traverse edgeTypes: {balances}, targetTypes: {AWS_EC2_INSTANCE}
```

### All Resources in VPC

```dql
smartscapeNodes "AWS_EC2_VPC"
| filter aws.vpc.id == "vpc-abc123"
| traverse edgeTypes: {is_attached_to}, targetTypes: {"AWS_*"}, direction: backward
| summarize count = count(), by: {type}
```

### Blast Radius (Security Group Impact)

```dql
smartscapeNodes "AWS_EC2_SECURITYGROUP"
| filter aws.resource.id == "sg-CRITICAL"
| traverse edgeTypes: {uses}, targetTypes: {"*"}, direction: backward
| summarize count = count(), by: {type}
```

### Cross-Account Usage

```dql
smartscapeNodes "AWS_IAM_ROLE"
| traverse edgeTypes: {uses}, targetTypes: {"AWS_*"}, direction: backward
| filter aws.account.id != "123456789012"
| fields role_id = dt.traverse.history[-1][`id`], resource_type = type, aws.account.id
```

### Network Topology (3-hop)

```dql
smartscapeNodes "AWS_EC2_NETWORKINTERFACE"
| traverse edgeTypes: {is_attached_to}, targetTypes: {AWS_EC2_INSTANCE}
| traverse edgeTypes: {is_attached_to}, targetTypes: {AWS_EC2_SUBNET}
| traverse edgeTypes: {is_attached_to}, targetTypes: {AWS_EC2_VPC}
| fields
    eni = dt.traverse.history[-3],
    instance = dt.traverse.history[-2],
    subnet = dt.traverse.history[-1],
    vpc = aws.resource.id
```

### Variable-Depth Search (All Reachable Nodes)

Chained `traverse` only returns nodes at an exact hop depth. To find all reachable nodes at any depth, use `append` to combine results from 1-hop, 2-hop, and 3-hop traversals:

```dql
smartscapeNodes "SERVICE"
| filter id == toSmartscapeId("SERVICE-XYZ")
| traverse edgeTypes: {calls}, targetTypes: {SERVICE}
| append [
    smartscapeNodes "SERVICE"
    | filter id == toSmartscapeId("SERVICE-XYZ")
    | traverse edgeTypes: {calls}, targetTypes: {SERVICE}
    | traverse edgeTypes: {calls}, targetTypes: {SERVICE}
  ]
| append [
    smartscapeNodes "SERVICE"
    | filter id == toSmartscapeId("SERVICE-XYZ")
    | traverse edgeTypes: {calls}, targetTypes: {SERVICE}
    | traverse edgeTypes: {calls}, targetTypes: {SERVICE}
    | traverse edgeTypes: {calls}, targetTypes: {SERVICE}
  ]
| dedup id
```

### Inferred Horizontal Edges (Deployment → Deployment via Service Calls)

Some entity types (e.g. K8S_POD, K8S_CLUSTER) have no explicit smartscape edge connecting to related SERVICE nodes. You can infer these relationships by navigating to the SERVICE layer, following `calls`, and navigating back:

```dql
smartscapeNodes "K8S_DEPLOYMENT"
| traverse edgeTypes: {belongs_to}, targetTypes: {SERVICE}, direction: backward, fieldsKeep: {type, name}
| traverse edgeTypes: {calls}, targetTypes: {SERVICE}
| traverse edgeTypes: {belongs_to}, targetTypes: {K8S_DEPLOYMENT}
| fields
    source_name = dt.traverse.history[0][name],
    target_name = name
```

______________________________________________________________________

## Guidelines

### `toSmartscapeId()` Usage

Do not use strings to filter Smartscape Ids. Strings representing SmartscapeId objects must be converted to data type SmartscapeId first. For example:

- When filtering by ID in `smartscapeEdges` or `smartscapeNodes`, or comparing IDs across hops, you must convert string IDs using `toSmartscapeId()`.
- Filtering `id` on `smartscapeNodes`
- Filtering `source_id` or `target_id` in `smartscapeEdges` queries
- Comparing IDs returned from `dt.traverse.history` against known values

**Example:**

```dql
smartscapeEdges "calls"
| filter source_id == toSmartscapeId("SERVICE-XYZ")
```

```dql
smartscapeNodes "SERVICE"
| filter id == toSmartscapeId("SERVICE-XYZ")
```

______________________________________________________________________

### Performance

1. **Filter before traverse** - Reduce dataset size early
1. **Use specific types** - Try to avoid `{"*"}` if not necessary
1. **Limit wildcards** - Add `| limit 100` for exploration
1. **Use references for counting** - No traversal overhead
1. **Use traverse for details** - When you need entity fields
1. **Select only needed fields** - `smartscapeNodes` includes large object fields by default that significantly increase result size. Avoid selecting these fields unless specifically required:
   - `k8s.object` — full Kubernetes object JSON
   - `aws.object` — full AWS resource description JSON
   - `azure.object` — full Azure resource JSON
   - `references` — nested object with all static forward edges

   Use `fields` to select only required columns, or `fieldsRemove k8s.object, aws.object` to drop them explicitly.
