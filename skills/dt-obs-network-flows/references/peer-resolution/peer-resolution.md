# Peer / IP Resolution

Resolve a raw IP address — and, when known, a port — to a monitored Dynatrace entity (host, process, Kubernetes pod, or Kubernetes service), or classify it as external. Flow records identify endpoints by IP; this is how you map those IPs back to Smartscape entities.

> All DQL in this file was validated against a live tenant with `dtctl query`.

## When to use this

Any flow source that carries raw IP endpoints needs this:

- **OneAgent flows** — the flow record has a smartscape ID only for the *capturing* entity; the *peer* (remote endpoint) is a raw IP. See [oneagent-flows.md → Peer Resolution](../oneagent-flows/oneagent-flows.md#peer-resolution) for choosing **which side** is the peer, then resolve that IP with the lookups below.
- **NetFlow / IPFIX / sFlow** — both endpoints are raw IPs with no entity context. See [netflow.md](../netflow/netflow.md).
- **Cloud flow logs (AWS)** — endpoints are raw cloud IPs (`pkt_srcaddr`/`pkt_dstaddr`) with no entity context. See [aws.md](../cloud-flows/aws/aws.md).

## Inputs and casting

The lookups take an IP (`<IP>`) and, for the process lookup, a port (`<PORT>`).

> Smartscape `ip` fields are typed `ip_address` — always wrap the literal with `toIp("<IP>")`. This is true even when the *flow* field you took the IP from was a plain string (as in NetFlow): the cast is on the Smartscape side.

## Resolution order

Try these tiers in order and **stop at the first that resolves**: **host → unique pod → service → external**. The tiers are mutually exclusive, so a match ends the search — don't fall through to a later tier.

**Process is a refinement of the host tier, not a separate tier.** When the peer resolves to a host *and* you know the server's listening port, refine that host match to the specific **process** on it (next section). If you don't have a listening port, leave it at the host — do not continue on to pods.

Check **hosts first**: a node IP is shared by all host-network pods, so trying pods before hosts would mis-attribute node traffic to an arbitrary pod. Fall through to the pod tier only when **no** host matches.

## Peer is a monitored host

```dql-template
smartscapeNodes HOST
| filter in(toIp("<IP>"), ip)
| fields id, name, ip, os.type, cloud.provider
```

Hosts expose their IPs in a top-level `ip` array.

## Peer is a monitored process (host IP + listening port)

```dql-template
smartscapeNodes HOST
| filter in(toIp("<IP>"), ip)
| traverse {runs_on}, {PROCESS}, direction:"backward"
| filter in(toLong(<PORT>), port)
| fields id, name, dt.process_group.detected_name, port
```

This matches on a **listening port**, so it only resolves when the IP:port you pass is a **server's listening port** — pass the server side's IP and port. A client's ephemeral port will not match a listening process; resolve a client peer to a host or pod by IP only, not to a specific process.

- **OneAgent flows:** the server side is `destination` when `process_is_server == false`; the client side (`process_is_server == true`) uses an ephemeral source port (usually `null`).
- **NetFlow:** use the well-known / listening-port side of the conversation.

## Peer is a Kubernetes pod

Pods expose their IPs in a top-level `ip` array:

```dql
smartscapeNodes { K8S_POD }
| filter isNotNull(ip)
| fields podId = id, podName = name, ip
```

> `ip` is an array (dual-stack pods have IPv4 + IPv6). Expand or build a client-side `Map<ip, pod>`. An IP mapped by more than one distinct pod is **ambiguous** (pod-network churn or host-network) — drop it from the pod map and fall back to host or external rather than assert a wrong pod.

## Peer is a Kubernetes Service (ClusterIP)

Service VIPs live in the parsed `k8s.object`:

```dql
smartscapeNodes { K8S_SERVICE }
| parse k8s.object, "JSON:k8s.object"
| fieldsAdd clusterIPs = k8s.object[spec][clusterIPs][]
| filter isNotNull(clusterIPs)
| fields svcId = id, k8s.service.name, k8s.namespace.name, clusterIPs
```
