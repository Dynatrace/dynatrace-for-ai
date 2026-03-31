# Ingress

Query `K8S_INGRESS` entities, parse routing rules, and audit TLS
configuration.

## Relationships

```
K8S_INGRESS --(routes_to)--> K8S_SERVICE
K8S_INGRESS --(belongs_to)--> K8S_NAMESPACE
K8S_INGRESS --(belongs_to)--> K8S_CLUSTER
```

## List Ingresses

```dql
smartscapeNodes K8S_INGRESS
| fields k8s.cluster.name, k8s.namespace.name, k8s.ingress.name
| sort k8s.cluster.name, k8s.namespace.name
```

## Parse Routing Rules

`spec.rules` maps host + path patterns to backend services and ports.

```dql
smartscapeNodes K8S_INGRESS
| parse k8s.object, "JSON:config"
| fieldsAdd rules = config[`spec`][`rules`]
| expand rule = rules
| fieldsAdd
    host = rule[`host`],
    paths = rule[`http`][`paths`]
| expand path_entry = paths
| fieldsAdd
    path = path_entry[`path`],
    backend_svc = path_entry[`backend`][`service`][`name`],
    backend_port = path_entry[`backend`][`service`][`port`][`number`]
| fields k8s.cluster.name, k8s.namespace.name, k8s.ingress.name,
    host, path, backend_svc, backend_port
```

Output is a routing map: `host/path → service:port`.

## TLS Audit

Ingresses without TLS (cleartext):

```dql
smartscapeNodes K8S_INGRESS
| parse k8s.object, "JSON:config"
| fieldsAdd tls = config[`spec`][`tls`]
| filter isNull(tls)
| fields k8s.cluster.name, k8s.namespace.name, k8s.ingress.name
```

Ingresses with TLS — certificate secrets in use:

```dql
smartscapeNodes K8S_INGRESS
| parse k8s.object, "JSON:config"
| expand tls_entry = config[`spec`][`tls`]
| fieldsAdd
    tls_hosts = tls_entry[`hosts`],
    tls_secret = tls_entry[`secretName`]
| fields k8s.cluster.name, k8s.namespace.name, k8s.ingress.name,
    tls_hosts, tls_secret
```
