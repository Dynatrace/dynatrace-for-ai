# Kubernetes — Dynatrace Operator and DynaKube

Operator install via Helm or manifest, the dynakube secret, a cloud-native full-stack DynaKube CR, and an ordered uninstall.

Part of the `dt-setup-oneagent` skill — see [../SKILL.md](../SKILL.md) for the hard rules, URL normalization and token guidance that apply to every target.

---

The Operator runs in the `dynatrace` namespace and reconciles a `DynaKube` CR. Both the operator and the CR are needed.

### 1. Install the operator

**Helm (recommended, Helm 3+):**

```bash
helm upgrade --install dynatrace-operator oci://public.ecr.aws/dynatrace/dynatrace-operator \
  --version 1.9.0 \
  --create-namespace --namespace dynatrace --atomic
```

Note OCI chart tags are unprefixed (`1.9.0`), but GitHub release tags use `v1.9.0`.

Both forms pin a **version**, not a digest. A published GitHub release asset is stable in practice, but an OCI tag can in principle be re-pushed, so `--version 1.9.0` is a weaker guarantee than a content hash. If your environment requires immutability, resolve the chart to a digest with `helm pull` and reference that, and mirror the CSI manifest into a location you control rather than fetching it from github.com at apply time. Pin the operator version deliberately either way — leaving it unset installs whatever is newest, which is not what you want in a cluster you intend to reproduce.

**Manifest fallback (no Helm):**

```bash
kubectl create namespace dynatrace
kubectl apply -f https://github.com/Dynatrace/dynatrace-operator/releases/download/v1.9.0/kubernetes-csi.yaml
kubectl -n dynatrace wait pod \
  --for=condition=ready \
  --selector=app.kubernetes.io/name=dynatrace-operator,app.kubernetes.io/component=webhook \
  --timeout=300s
```

### 2. Create the `dynakube` secret

Do **not** use `kubectl create secret --from-literal=apiToken=$DT_API_TOKEN`: that places the token in kubectl's own command line, where any local user can read it from the process list for the duration of the call. Pipe a manifest instead — `printf` is a shell builtin and `base64` reads stdin, so the value never becomes an argument:

```bash
kubectl -n dynatrace apply -f - <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: dynakube
  namespace: dynatrace
type: Opaque
data:
  apiToken: $(printf '%s' "$DT_API_TOKEN" | base64 | tr -d '\n')
  dataIngestToken: $(printf '%s' "$DT_DATA_INGEST_TOKEN" | base64 | tr -d '\n')
EOF
```

`dataIngestToken` can equal `apiToken` if you don't have a separate ingest token. Applying the manifest is also idempotent — re-running it rotates the stored token rather than failing on an existing secret.

### 3. Apply a DynaKube CR (cloud-native full-stack mode)

```yaml
apiVersion: dynatrace.com/v1beta5     # storage version in operator v1.9.0; check the CRD if you've upgraded
kind: DynaKube
metadata:
  name: dynakube
  namespace: dynatrace
  annotations:
    feature.dynatrace.com/k8s-app-enabled: "true"
    feature.dynatrace.com/injection-readonly-volume: "true"
spec:
  apiUrl: ${DT_ENV_URL_NORMALIZED}/api      # note the trailing /api
  metadataEnrichment:
    enabled: true
  oneAgent:
    cloudNativeFullStack:
      tolerations:
        - effect: NoSchedule
          key: node-role.kubernetes.io/master
          operator: Exists
        - effect: NoSchedule
          key: node-role.kubernetes.io/control-plane
          operator: Exists
  activeGate:
    capabilities: [routing, kubernetes-monitoring]
    resources:
      requests: { cpu: 500m, memory: 512Mi }
      limits:   { cpu: 1000m, memory: 1.5Gi }
```

Always run `kubectl apply --dry-run=server -f dynakube.yaml` first — the operator webhook produces meaningful validation errors.

### AWS EKS specifics

On standard EKS with EC2 or bare-metal nodes there is nothing to do differently — Dynatrace documents *"No specific configuration is required for EKS."* Same operator install, same secret, same DynaKube. The differences are all driven by **node type**:

| Node type | What works |
|---|---|
| EC2 / bare-metal | Everything. Full-stack, CSI driver, no special config |
| **Fargate** | `applicationMonitoring` **only**, without the CSI driver. No DaemonSet is possible — Fargate gives you no nodes to place one on |
| **Bottlerocket** | `applicationMonitoring` only. Platform Observability via OneAgent is not supported; `cloudNativeFullStack` and `classicFullStack` are unavailable |

Bottlerocket needs two DynaKube annotations that no other distribution does — a read-only root filesystem forces the CSI driver into read-only mode, and platform observability has to come from an ActiveGate instead of the agent:

```yaml
metadata:
  annotations:
    feature.dynatrace.com/injection-readonly-volume: "true"
    feature.dynatrace.com/automatic-kubernetes-api-monitoring: "true"
```

The Dynatrace quickstart wizard enforces this: pick EKS-on-Bottlerocket (or GKE Autopilot) and full-stack is not offered at all.

**No AWS IAM setup is required.** The operator authenticates to Dynatrace with the API token in the `dynakube` secret, not with cloud credentials — there is no IRSA role, no service-account annotation, nothing to attach.

**An EKS-only install path exists.** Dynatrace ships as an AWS Marketplace EKS add-on, which provisions the namespace and operator in place of `helm install`:

```bash
aws eks create-addon --cluster-name <cluster> --addon-name dynatrace_dynatrace-operator
```

Everything after that — creating the secret, applying the DynaKube — is identical to the steps above.

**EKS Auto Mode has no Dynatrace documentation.** It appears in neither the support matrix, the supported-technologies page nor the quickstart. Auto Mode provisions Bottlerocket nodes by default, so expect the Bottlerocket restrictions above to apply — plan for `applicationMonitoring` rather than full-stack.

### Uninstall (in order)

The order matters: deleting the namespace or the CRDs before the DynaKube finalizers have drained strands agent pods and can leave the namespace stuck `Terminating`.

```bash
kubectl -n dynatrace delete dynakube --all                       # let operator unwind agent pods
kubectl -n dynatrace wait --for=delete dynakube --all --timeout=60s  # finalizers must drain first
helm uninstall dynatrace-operator -n dynatrace                   # or kubectl delete -f the manifest
kubectl get crd -o name | grep 'dynatrace\.com$' | xargs -r kubectl delete
kubectl delete namespace dynatrace
```

---
