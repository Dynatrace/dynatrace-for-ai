# Dynatrace Operator

**Gen3 replacement**: Dynatrace Operator 1.10.2+ with Platform token and supported OneAgent deployment mode

**Phase 2 required**: yes

## Contents

- [What changes](#what-changes)
- [Prerequisites](#prerequisites)
- [Instructions](#instructions)
- [Migration mapping](#migration-mapping)
- [Examples](#examples)
- [Outcome](#outcome)
- [Validation](#validation)
  - [Operator version](#operator-version)
  - [CRD stored versions](#crd-stored-versions)
  - [OneAgent deployment mode](#oneagent-deployment-mode)
  - [Token type](#token-type)
  - [Operand artifacts](#operand-artifacts)
- [Customer actions](#customer-actions)
- [References](#references)

## What changes

An installation is non-compliant for Phase 3 if any of the following are true:

| Criterion                | Non-compliant                         | Required for Phase 3                                                 |
|--------------------------|---------------------------------------|----------------------------------------------------------------------|
| Operator version         | < 1.10.2                              | ≥ 1.10.2                                                             |
| Token type               | Classic API token (`dt0c01.*` prefix) | Platform token (`dt0s16.*` prefix)                                   |
| OneAgent deployment mode | `classicFullStack`                    | `cloudNativeFullStack`, `hostMonitoring`, or `applicationMonitoring` |
| Operand artifacts        | Dynatrace SaaS (zip)                  | Public ECR (container image)                                         |

Criteria are related: a Platform token automatically enables public ECR artifact delivery. `classicFullStack` is incompatible with Platform tokens and MUST be migrated before the token is changed.

## Prerequisites

- DQL execution access on the tenant

## Instructions

1. Run the tracking queries in the [Validation](#validation) section to identify non-compliant items across all four criteria.
2. Remediate **in this order**:
   1. Per DynaKube: if `spec.oneAgent.classicFullStack` is set → replace with a supported mode: `cloudNativeFullStack` (host and application monitoring), `hostMonitoring` (host-level monitoring only), or `applicationMonitoring` (application-level monitoring only). See [Classic to Cloud Native](https://docs.dynatrace.com/docs/ingest-from/setup-on-k8s/guides/migration/classic-to-cloud-native) or [Classic to Application Monitoring](https://docs.dynatrace.com/docs/ingest-from/setup-on-k8s/guides/migration/classic-to-app-monitoring).
   2. Per cluster: if operator version < 1.10.2 → upgrade the operator to 1.10.2+ using the original installation method; see [Dynatrace Operator releases](https://github.com/Dynatrace/dynatrace-operator/releases) for version-specific upgrade notes. **Before upgrading, determine the required upgrade path for every cluster** using the [CRD stored versions](#crd-stored-versions) queries and their lookup table. For clusters that are missing from those results, or report no stored versions, do not guess the path — direct the user to the [upgrade path documentation](https://docs.dynatrace.com/docs/ingest-from/setup-on-k8s/guides/deployment-and-configuration/updates-and-maintenance/update-uninstall-operator#upgrade-path).
   3. Per DynaKube: if token is classic → replace `apiToken` in the referenced Kubernetes Secret with a [Platform token](https://docs.dynatrace.com/docs/manage/identity-access-management/access-tokens-and-oauth-clients/platform-tokens#create-a-new-platform-token) (see [Examples](#examples)); required token scopes and Secret update steps are in [Tokens and permissions](https://docs.dynatrace.com/docs/ingest-from/setup-on-k8s/deployment/tokens-permissions).
   4. If the operand artifact filter still returns rows after step 3 → a Platform token with no explicit image fields activates [automatic image resolution](https://docs.dynatrace.com/docs/ingest-from/setup-on-k8s/guides/container-registries/use-public-registry#automatic-image-resolution) from the public ECR; re-run the tracking query to confirm. No additional configuration or feature flags are needed.
   5. Per DynaKube: if Platform token is active and any of `spec.oneAgent.<mode>.image`, `spec.oneAgent.<mode>.codeModulesImage`, or `spec.activeGate.image` is explicitly set → check whether all pinned image references come from a [supported public registry](https://docs.dynatrace.com/docs/ingest-from/setup-on-k8s/guides/container-registries/use-public-registry#supported-public-registries) (`public.ecr.aws` or `registry-1.docker.io`). If yes, recommend removing the explicit image fields to delegate artifact sourcing to [automatic image resolution](https://docs.dynatrace.com/docs/ingest-from/setup-on-k8s/guides/container-registries/use-public-registry#automatic-image-resolution) and receive automatic operator-managed updates. If any image references a private or non-public registry, do not recommend removal — those users must continue managing images explicitly via their private registry. This does not affect compliance in either case.
3. Present the required changes to the user and instruct them to apply the changes using their preferred method (`kubectl apply`, Helm, Monaco, Terraform).
4. Instruct the user to re-run the tracking queries in [Validation](#validation) to confirm compliance; all four filters must return empty.

## Migration mapping

| Non-compliant | Compliant | Notes |
|---|---|---|
| `spec.oneAgent.classicFullStack` | `spec.oneAgent.cloudNativeFullStack` | Host and application monitoring |
| `spec.oneAgent.classicFullStack` | `spec.oneAgent.hostMonitoring` | Host-level monitoring only |
| `spec.oneAgent.classicFullStack` | `spec.oneAgent.applicationMonitoring` | Application-level monitoring only |
| Classic API token (`dt0c01.*`) in Secret | Platform token (`dt0s16.*`) in Secret | Update `apiToken` key; automatic image resolution activates automatically |
| Operator version < 1.10.2 | Operator version ≥ 1.10.2 | Upgrade via original installation method |

A Platform token enables [automatic image resolution](https://docs.dynatrace.com/docs/ingest-from/setup-on-k8s/guides/container-registries/use-public-registry#automatic-image-resolution) and is the recommended migration path — no feature flags or explicit image configuration are required. DynaKubes with explicit image fields in the spec are compliant but will not benefit from automatic operator-managed updates; removing explicit image fields is advisory — see step 2.5 in the instructions above for when to recommend it.

## Examples

### Classic token → Platform token

The `spec.tokens` field names a Kubernetes Secret in the same namespace. The Secret MUST have an `apiToken` key. If `spec.tokens` is not set, the Secret name defaults to the DynaKube resource name.

**Before:**

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: my-dynakube-token
  namespace: dynatrace
type: Opaque
stringData:
  apiToken: "dt0c01.XXXX.YYYY"   # classic API token
```

**After:**

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: my-dynakube-token
  namespace: dynatrace
type: Opaque
stringData:
  apiToken: "dt0s16.XXXX.YYYY"  # Platform token
```

[Generate a Platform token](https://docs.dynatrace.com/docs/manage/identity-access-management/access-tokens-and-oauth-clients/platform-tokens#create-a-new-platform-token) in the Dynatrace UI; see [Tokens and permissions](https://docs.dynatrace.com/docs/ingest-from/setup-on-k8s/deployment/tokens-permissions) for the scope list.

## Outcome

A compliant Dynatrace Operator installation satisfies all the following, regardless of deployment tool:

- Operator version ≥ 1.10.2 on every cluster
- No DynaKube has `spec.oneAgent.classicFullStack` set
- Every DynaKube's referenced Secret contains a Platform token (`dt0s16.*`) as `apiToken`
- `status.apiToken.platform: true` on every DynaKube CR
- Automatic image resolution is active (automatic consequence of Platform token)

Output a compliance summary table per DynaKube, cross-referencing the tracking query results. `operator_version` comes from the operator deployment query; `deployment_mode`, `token_type`, and `platform_token` come from the DynaKube-scoped queries:

| k8s.cluster.name | dynakube | operator_version | deployment_mode | token_type | platform_token | action |
|---|---|---|---|---|---|---|
| prod-eu | prod-dynakube | v1.10.2 | cloudNativeFullStack | Platform | true | None |
| staging | staging-dynakube | v1.8.3 | classicFullStack | Classic | false | Migrate classicFullStack; upgrade operator; replace token |

## Validation

Run these queries to identify non-compliant items before remediation and to confirm compliance after.

### Operator version

List all operator deployments with their installed version:

```dql
smartscapeNodes K8S_DEPLOYMENT
| filter tags[`app.kubernetes.io/name`] == "dynatrace-operator"
       and tags[`app.kubernetes.io/component`] == "operator"
| fields k8s.cluster.name, k8s.namespace.name,
         operator_version = tags[`app.kubernetes.io/version`]
| sort k8s.cluster.name
```

List only non-compliant operator deployments (version < 1.10.2):

```dql
smartscapeNodes K8S_DEPLOYMENT
| filter tags[`app.kubernetes.io/name`] == "dynatrace-operator"
       and tags[`app.kubernetes.io/component`] == "operator"
| fieldsAdd operator_version = tags[`app.kubernetes.io/version`]
| fieldsAdd ver = if(startsWith(operator_version, "v"), substring(operator_version, from: 1), else: operator_version)
| parse ver, "LONG:major '.' LONG:minor"
| fieldsAdd major = coalesce(major, 0), minor = coalesce(minor, 0)
| filter major < 1 or (major == 1 and minor < 10)
| fields k8s.cluster.name, k8s.namespace.name, operator_version
```

An empty result means all operators meet the version requirement. Nightly and pre-release builds (e.g. `0.0.0-nightly-*`) parse as `0.0` and appear as non-compliant — verify them manually using the full list query above.

### CRD stored versions

Needed only for clusters running operator version below the current floor (1.10.2), to determine whether the upgrade requires one or more intermediate stopover releases. The `K8S_CUSTOMRESOURCEDEFINITION` entity carries the full CRD object — including `status.storedVersions` — for every cluster where kubernetes-monitoring reports it, so this covers all reporting clusters in a single query. Clusters that do not report it are handed off to the upgrade path documentation (see below).

Establish the cluster baseline first — this is the list the CRD query further below gets cross-referenced against:

```dql
smartscapeNodes K8S_CLUSTER
| fields k8s.cluster.name
| sort k8s.cluster.name
```

#### Stopover table

This mirrors the operator's own [upgrade path documentation](https://docs.dynatrace.com/docs/ingest-from/setup-on-k8s/guides/deployment-and-configuration/updates-and-maintenance/update-uninstall-operator#upgrade-path), keyed by the DynaKube's stored CRD schema version (`status.storedVersions`) rather than the operator version currently running — that's what lets one DQL query classify every cluster in a single pass, without first knowing what version each cluster is on.

**Rule: the lowest version in `stored_versions` decides the next hop.** `status.storedVersions` lists every schema version still persisted, so it can hold several entries. Order them `v1beta1` < `v1beta2` < `v1beta3` < … < `v1beta6`, take the lowest, and use only its row — ignore every higher entry in the same array. Passing through the stopover release cleans up the old entries.

| Current Version | Storage Version | Max Direct Upgrade |
|-----------------|-----------------|--------------------|
| ≤ 1.3           | `v1beta1`       | 1.7.3              |
| ≤ 1.3           | `v1beta2`       | 1.7.3              |
| 1.4.x           | `v1beta3`       | 1.8.1              |
| 1.5.x           | `v1beta4`       | 1.10.2             |
| ≥ 1.6           | `v1beta5`       | latest             |
| ≥ 1.8           | `v1beta6`       | latest             |

Match the cluster's lowest `stored_versions` entry against the **Storage Version** column.

To get the complete path, chain the lookups: a stopover release belongs to a row of this table itself (use the **Current Version** column), and that row gives the hop after it. Repeat until a row's Max Direct Upgrade reaches this skill's floor (1.10.2) — the `v1beta4` row and newer do. For example, 1.7.3 sits in the "≥ 1.6" row (Max Direct Upgrade: latest) and 1.8.1 sits in the "≥ 1.8" row (also latest), so both go straight to 1.10.2 afterwards. See **Chaining stopovers** below for verifying each hop.

Example with several entries: `["v1beta2","v1beta3"]` → lowest is `v1beta2` → 1.7.3 → 1.10.2. The `v1beta3` entry is ignored, so there is no 1.8.x stopover.

This table is the single source of truth for the DQL query below — update it first, then mirror the change into the DQL `if`/`else` chain. The chain tests the lowest version first, which is what implements the lowest-wins rule — keep that order. Don't edit the query independently of this table.

List all clusters with their CRD stored versions and the resulting upgrade path:

```dql
smartscapeNodes K8S_CUSTOMRESOURCEDEFINITION
| filter k8s.customresourcedefinition.name == "dynakubes.dynatrace.com"
| parse k8s.object, "JSON:config"
| fieldsAdd stored_versions = config[`status`][`storedVersions`]
| fieldsAdd upgrade_path = if(isNull(stored_versions) or arraySize(stored_versions) == 0, "Unknown — verify in upgrade path documentation",
    else: if(in(stored_versions, {"v1beta1", "v1beta2"}), "1.7.3 -> 1.10.2",
    else: if(in(stored_versions, {"v1beta3"}), "1.8.1 -> 1.10.2",
    else: "Direct to 1.10.2")))
| fields k8s.cluster.name, stored_versions, upgrade_path
| sort k8s.cluster.name
```

Cross-reference the `K8S_CUSTOMRESOURCEDEFINITION` result against the `K8S_CLUSTER` cluster list and treat **two** situations the same way — direct the user to the [upgrade path documentation](https://docs.dynatrace.com/docs/ingest-from/setup-on-k8s/guides/deployment-and-configuration/updates-and-maintenance/update-uninstall-operator#upgrade-path) to verify `storedVersions` and the upgrade path on their own:

- **Cluster missing entirely in `K8S_CUSTOMRESOURCEDEFINITION`**: present in the `K8S_CLUSTER` list but absent from this query's results — no CRD data in Dynatrace at all (for example, kubernetes-monitoring is not enabled or the operator version predates CRD status reporting). Do not infer the stored version from the cluster name or any other heuristic.
- **Cluster present with an empty/null `stored_versions`**: the row exists (`upgrade_path` reads `"Unknown — verify in upgrade path documentation"`) but the CRD entity hasn't reported `status.storedVersions` yet. Do not treat this the same as a genuinely empty-but-safe result — an empty field is a data gap, not evidence the cluster is on `v1beta4` or newer.

For these clusters, do not determine or recommend an upgrade path, and do not ask the user to run `kubectl` or any other command against the cluster. Tell the user the path cannot be determined from Dynatrace data, point them to the documentation above, and have them apply the same lookup (lowest stored version decides the next hop) to the values they find there. Clusters with a populated `stored_versions` are unaffected and keep the DQL-derived path.

**Chaining stopovers**: after a cluster completes a stopover, re-run this query against that cluster before continuing toward the floor. Take the lowest entry of the new `stored_versions` and look it up in the stopover table again; if its maximum direct upgrade is below the floor, that is the next stopover, and if it reaches the floor, upgrade to the floor. Repeat until the floor is reached. The `upgrade_path` column of the query above shows the full expected path; this re-check confirms each hop landed as expected, and if a re-read contradicts the expected path, trust the re-read.

After completing a stopover upgrade, allow a few minutes for kubernetes-monitoring to report the updated `storedVersions` before re-running this query — a stale read looks identical to a failed migration.

### OneAgent deployment mode

The deployment mode is read directly from the DynaKube CR spec (`spec.oneAgent.<mode>`). A DynaKube is non-compliant if `spec.oneAgent.classicFullStack` is set.

List all DynaKubes with their deployment mode:

```dql
smartscapeNodes K8S_DYNAKUBE
| parse k8s.object, "JSON:config"
| fieldsAdd deployment_mode = coalesce(
    if(isNotNull(config[`spec`][`oneAgent`][`classicFullStack`]), "classicFullStack"),
    if(isNotNull(config[`spec`][`oneAgent`][`cloudNativeFullStack`]), "cloudNativeFullStack"),
    if(isNotNull(config[`spec`][`oneAgent`][`hostMonitoring`]), "hostMonitoring"),
    if(isNotNull(config[`spec`][`oneAgent`][`applicationMonitoring`]), "applicationMonitoring"),
    "none")
| fields k8s.cluster.name, name, deployment_mode
| sort k8s.cluster.name
```

List only non-compliant DynaKubes (`classicFullStack`):

```dql
smartscapeNodes K8S_DYNAKUBE
| parse k8s.object, "JSON:config"
| filter isNotNull(config[`spec`][`oneAgent`][`classicFullStack`])
| fields k8s.cluster.name, name
```

### Token type

The DynaKube CR status field `status.apiToken.platform` is available via `k8s.object` on `K8S_DYNAKUBE` entities in Grail.

List all DynaKubes with their token type:

```dql
smartscapeNodes K8S_DYNAKUBE
| parse k8s.object, "JSON:config"
| fieldsAdd is_platform_token = config[`status`][`apiToken`][`platform`]
| fields k8s.cluster.name, name, is_platform_token
| sort k8s.cluster.name
```

List only non-compliant DynaKubes (classic API token):

```dql
smartscapeNodes K8S_DYNAKUBE
| parse k8s.object, "JSON:config"
| fieldsAdd is_platform_token = config[`status`][`apiToken`][`platform`]
| filter isFalseOrNull(is_platform_token)
| fields k8s.cluster.name, name
```

### Operand artifacts

A DynaKube is compliant if explicit image fields are already configured in the spec, or the Platform token is active — in which case the operator uses [automatic image resolution](https://docs.dynatrace.com/docs/ingest-from/setup-on-k8s/guides/container-registries/use-public-registry#automatic-image-resolution) from the public ECR without requiring explicit image configuration.

List all DynaKubes with their automatic image resolution status:

```dql
smartscapeNodes K8S_DYNAKUBE
| parse k8s.object, "JSON:config"
| fieldsAdd oa_configured = if(isNull(config[`spec`][`oneAgent`]) or toString(config[`spec`][`oneAgent`]) == "{}", false, else: true)
| fieldsAdd oa_image_configured = coalesce(
    if(isNotNull(config[`spec`][`oneAgent`][`classicFullStack`][`image`]), true),
    if(isNotNull(config[`spec`][`oneAgent`][`cloudNativeFullStack`][`image`]) and isNotNull(config[`spec`][`oneAgent`][`cloudNativeFullStack`][`codeModulesImage`]), true), // both fields required: image pins OneAgent, codeModulesImage pins injected modules
    if(isNotNull(config[`spec`][`oneAgent`][`applicationMonitoring`][`codeModulesImage`]), true),
    if(isNotNull(config[`spec`][`oneAgent`][`hostMonitoring`][`image`]), true),
    false)
| fieldsAdd ag_configured = if(isNull(config[`spec`][`activeGate`]) or toString(config[`spec`][`activeGate`]) == "{}", false, else: true)
| fieldsAdd ag_image_configured = coalesce(
    if(isNotNull(config[`spec`][`activeGate`][`image`]), true),
    false)
| fieldsAdd uses_image_fields = (oa_configured == false or oa_image_configured == true)
                             and (ag_configured == false or ag_image_configured == true)
| fieldsAdd platform_token = config[`status`][`apiToken`][`platform`] == true
| fields k8s.cluster.name, name, uses_image_fields, platform_token
| sort k8s.cluster.name
```

List only non-compliant DynaKubes (automatic image resolution not active):

```dql
smartscapeNodes K8S_DYNAKUBE
| parse k8s.object, "JSON:config"
| fieldsAdd oa_configured = if(isNull(config[`spec`][`oneAgent`]) or toString(config[`spec`][`oneAgent`]) == "{}", false, else: true)
| fieldsAdd oa_image_configured = coalesce(
    if(isNotNull(config[`spec`][`oneAgent`][`classicFullStack`][`image`]), true),
    if(isNotNull(config[`spec`][`oneAgent`][`cloudNativeFullStack`][`image`]) and isNotNull(config[`spec`][`oneAgent`][`cloudNativeFullStack`][`codeModulesImage`]), true), // both fields required: image pins OneAgent, codeModulesImage pins injected modules
    if(isNotNull(config[`spec`][`oneAgent`][`applicationMonitoring`][`codeModulesImage`]), true),
    if(isNotNull(config[`spec`][`oneAgent`][`hostMonitoring`][`image`]), true),
    false)
| fieldsAdd ag_configured = if(isNull(config[`spec`][`activeGate`]) or toString(config[`spec`][`activeGate`]) == "{}", false, else: true)
| fieldsAdd ag_image_configured = coalesce(
    if(isNotNull(config[`spec`][`activeGate`][`image`]), true),
    false)
| fieldsAdd uses_image_fields = (oa_configured == false or oa_image_configured == true)
                             and (ag_configured == false or ag_image_configured == true)
| fieldsAdd platform_token = config[`status`][`apiToken`][`platform`] == true
| filter uses_image_fields != true and isFalseOrNull(platform_token)
| fields k8s.cluster.name, name
```

List DynaKubes with Platform token active and explicit image fields still set (advisory — remove image fields to enable automatic updates):

```dql
smartscapeNodes K8S_DYNAKUBE
| parse k8s.object, "JSON:config"
| fieldsAdd platform_token = config[`status`][`apiToken`][`platform`] == true
| fieldsAdd oa_image_configured = coalesce(
    if(isNotNull(config[`spec`][`oneAgent`][`classicFullStack`][`image`]), true),
    if(isNotNull(config[`spec`][`oneAgent`][`cloudNativeFullStack`][`image`]) or isNotNull(config[`spec`][`oneAgent`][`cloudNativeFullStack`][`codeModulesImage`]), true), // either field pins a version; flag both independently
    if(isNotNull(config[`spec`][`oneAgent`][`applicationMonitoring`][`codeModulesImage`]), true),
    if(isNotNull(config[`spec`][`oneAgent`][`hostMonitoring`][`image`]), true),
    false)
| fieldsAdd ag_image_configured = coalesce(
    if(isNotNull(config[`spec`][`activeGate`][`image`]), true),
    false)
| filter platform_token == true and (oa_image_configured == true or ag_image_configured == true)
| fields k8s.cluster.name, name
```

Remediation is complete when:

- The non-compliant operator version filter returns no rows.
- The `classicFullStack` DynaKube filter returns no rows.
- The non-compliant token type filter returns no rows.
- The non-compliant operand artifact filter returns no rows (all DynaKubes have `platform_token = true` or explicit image fields).
- Advisory: the explicit image fields filter returns no rows (see step 2.5 in the instructions for when removal applies).

## Customer actions

- Run the operator version queries to identify clusters below 1.10.2 and upgrade them via the original installation method (Helm, OLM, or direct manifest)
- Run the CRD stored-versions queries, starting with the cluster baseline, to determine the upgrade path (direct, or via a 1.7.3/1.8.1 stopover) for each cluster below 1.10.2; for clusters missing from the CRD query results (or with empty `stored_versions`), verify `storedVersions` and the upgrade path in the [upgrade path documentation](https://docs.dynatrace.com/docs/ingest-from/setup-on-k8s/guides/deployment-and-configuration/updates-and-maintenance/update-uninstall-operator#upgrade-path)
- Run the deployment mode query to identify DynaKubes using `classicFullStack` and migrate them to `cloudNativeFullStack`, `hostMonitoring`, or `applicationMonitoring`
- Run the token type tracking queries to identify DynaKubes using classic API tokens and replace them with [Platform tokens](https://docs.dynatrace.com/docs/manage/identity-access-management/access-tokens-and-oauth-clients/platform-tokens#create-a-new-platform-token) in the referenced Kubernetes Secret (see [Tokens and permissions](https://docs.dynatrace.com/docs/ingest-from/setup-on-k8s/deployment/tokens-permissions))
- Run the operand artifact tracking queries to confirm automatic image resolution is active; a Platform token satisfies this automatically, but verify if explicit image fields are configured instead
- For DynaKubes where a Platform token is active and explicit image fields are still set: consider removing them to enable automatic image resolution and operator-managed updates (advisory — see step 2.5 in the instructions for when removal applies)
- Re-run all tracking queries after remediation to confirm compliance

## References

- [Operator upgrade path](https://docs.dynatrace.com/docs/ingest-from/setup-on-k8s/guides/deployment-and-configuration/updates-and-maintenance/update-uninstall-operator#upgrade-path)
- [Classic to Cloud Native migration](https://docs.dynatrace.com/docs/ingest-from/setup-on-k8s/guides/migration/classic-to-cloud-native)
- [Classic to Application Monitoring migration](https://docs.dynatrace.com/docs/ingest-from/setup-on-k8s/guides/migration/classic-to-app-monitoring)
- [DynaKube migration guide](https://docs.dynatrace.com/docs/ingest-from/setup-on-k8s/guides/migration/dynakube)
- [Tokens and permissions (K8s deployment)](https://docs.dynatrace.com/docs/ingest-from/setup-on-k8s/deployment/tokens-permissions)
- [Create a Platform token](https://docs.dynatrace.com/docs/manage/identity-access-management/access-tokens-and-oauth-clients/platform-tokens#create-a-new-platform-token)
- [Dynatrace Operator on GitHub](https://github.com/Dynatrace/dynatrace-operator)
- [DynaKube API reference](https://github.com/Dynatrace/dynatrace-operator/blob/main/doc/api/dynakube-api-ref.md)
