# Network Policies

Audit `K8S_NETWORKPOLICY` entities for namespace isolation coverage and
inspect policy rules.

## List All Network Policies

```dql
smartscapeNodes K8S_NETWORKPOLICY
| fields k8s.cluster.name, k8s.namespace.name, k8s.networkpolicy.name
| sort k8s.cluster.name, k8s.namespace.name
```

## Namespaces Without Any Network Policy

Namespaces with no NetworkPolicy allow all ingress and egress by default —
a default-allow posture.

```dql
smartscapeNodes K8S_NAMESPACE
| filterOut k8s.namespace.name in [
    smartscapeNodes K8S_NETWORKPOLICY
    | dedup k8s.namespace.name
    | fields k8s.namespace.name
  ]
| fields k8s.cluster.name, k8s.namespace.name
```

## Policy Count per Namespace

```dql
smartscapeNodes K8S_NETWORKPOLICY
| summarize policy_count = count(), by: {k8s.cluster.name, k8s.namespace.name}
| sort policy_count desc
```

## Policy Rule Inspection

Parse `spec.podSelector`, `spec.policyTypes`, `spec.ingress`, and
`spec.egress` from `k8s.object`:

```dql-template
smartscapeNodes K8S_NETWORKPOLICY
| filter k8s.namespace.name == "<namespace>"
| parse k8s.object, "JSON:config"
| fieldsAdd
    pod_selector = config[`spec`][`podSelector`],
    policy_types = config[`spec`][`policyTypes`],
    ingress_rules = config[`spec`][`ingress`],
    egress_rules = config[`spec`][`egress`]
| fields k8s.cluster.name, k8s.namespace.name, k8s.networkpolicy.name,
    pod_selector, policy_types, ingress_rules, egress_rules
```
