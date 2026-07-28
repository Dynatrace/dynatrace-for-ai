---
name: dt-sec-contextualization
description: >-
  Resolve security signals, IoC matches, or Smartscape nodes to runtime
  Dynatrace entities and connect findings on different entity levels through a
  shared runtime entity. Covers identity-to-Smartscape mapping (incl.
  container-image digest/ID to workload), cross-level topology (K8s pod
  detection vs. node CVE via pod-to-node), per-entity risk summarization, and
  coverage match recipes shared by dt-sec-insights. Trigger: "map these findings
  to workloads/hosts", "which workload does this container image run as", "do
  these findings relate through the same runtime entity", "enrich this IoC match
  with entity context", "which threat report mentions this IoC". Queries
  security.events ONLY for THREAT_REPORT IoC enrichment (matched IoC to
  attributing reports); Do NOT use for broad security.events posture/overview
  (use dt-sec-insights), general DQL (use dt-dql-essentials), IoC hunting in
  logs/spans (use dt-sec-ioc-hunting), or K8s observability outside the security
  cross-level context (use dt-obs-kubernetes).
license: Apache-2.0
---

# Security Contextualization Skill

Resolve security signals and entity attribute sets to runtime Dynatrace
Smartscape entities, summarize findings across entity levels, and connect
signals that land on different levels (e.g. a detection on a `K8S_POD` vs.
a CVE on a `KUBERNETES_NODE`) via a shared runtime entity.

## What This Skill Covers

- **Identity → Smartscape mapping** — given a row carrying any of
  `dt.smartscape_source.id`, `container_image.digest`, `container_image.id`,
  `host.ip`, `dt.entity.*`, or `k8s.*` fields, resolve it to a Smartscape
  entity at any requested level (CONTAINER / K8S_POD / workload /
  K8S_NODE / HOST / cloud / `GENAI_SERVICE` — AI/GenAI workloads).
- **Artifact → runtime bridge** — `container_image.digest` →
  `smartscapeNodes CONTAINER` → `is_part_of.*` → parent workload or
  `runs_on.host` → HOST. Works without pre-enriched `dt.smartscape_source.id`.
- **Cross-level correlation** — tiered entity matching to determine whether
  two findings (e.g. a detection and a CVE from different legs) relate through
  a shared runtime entity. Tier 1: exact entity id match; Tier 2: same
  workload/pod/host by name; Tier 3: same namespace/cluster (context-only —
  does not contribute to scoring).
- **Pod → node topology** — resolve `K8S_POD` to its `K8S_NODE` via
  `k8s.node.name` (co-projected field) or Smartscape edge traversal. Enables
  "detection hit pod X — does that pod run on a vulnerable node?"
- **Coverage match recipes** — 2-way and 3-way container→workload match
  patterns shared across dt-sec-insights coverage counting queries.
- **Entity enrichment** — given findings, IoC matches, or raw Smartscape
  nodes, produce per-entity risk-level breakdowns and entity-key bundles for
  downstream scoring.
- **IoC enrichment** — attribute an already-matched IoC (IP / domain / URL /
  email / CVE / hash / MITRE TTP) with adversary context (actor, malware family,
  MITRE technique, targeting, provider) by reverse-looking-up the ingested
  `THREAT_REPORT` events whose observable arrays contain that IoC.

## When to Use This Skill

| Intent / trigger | Reference |
|---|---|
| Map findings / IoC matches to workloads, hosts, or cloud entities | `identity-mapping.md` -> `entity-enrichment.md` |
| Which Smartscape entity does this container image / digest run as? | `identity-mapping.md` § Mapping Primitive (Path 2 - container digest) |
| Do this detection and this CVE relate via a shared entity? | `correlation-and-coverage.md` § Correlation |
| Pod X fired - does it run on a vulnerable node? | `correlation-and-coverage.md` § Correlation (Pod->Node Topology) |
| Per-entity risk summary (Critical/High/Medium/Low) | `entity-enrichment.md` |
| Coverage match recipe - which workloads are covered by product Y? | `correlation-and-coverage.md` § Coverage |
| Which entity-identity fields are relevant to a finding type? | `identity-mapping.md` § Data Model |
| Enrich a matched IoC (IP/domain/hash/CVE/...) with threat-report adversary context | `ioc-enrichment.md` |
| Scope findings to AI/GenAI workloads; which processes belong to an AI service; resolve a process to its AI service | `identity-mapping.md` § Mapping Primitive (Path 4 - `GENAI_SERVICE -> SERVICE -> PROCESS`) |

## How This Skill Is Organized

1. **SKILL.md** (this file) — entry point and routing.
2. **references/**
   - [**identity-mapping.md**](references/identity-mapping.md) — generalized
     identity->Smartscape resolver (mapping primitive Paths 1/2/3/4), pre-flight
     identifier checks, level selection, and entity-identity field guidance.
   - [**entity-enrichment.md**](references/entity-enrichment.md) — consumers of
     the mapping primitive: cloud (Path 1), K8s workload (3-way), host-by-IP,
     host-by-entity, natural-language fallback, problem->entities->findings chain.
     Per-entity risk-level breakdowns (Critical/High/Medium/Low).
   - [**correlation-and-coverage.md**](references/correlation-and-coverage.md) —
     cross-level entity convergence, pod->node topology resolution, scoring contract,
     and 2-way/3-way coverage match recipes shared with dt-sec-insights.
   - [**ioc-enrichment.md**](references/ioc-enrichment.md) — reverse-lookup IoC
     enrichment: attribute a matched IoC to ingested `THREAT_REPORT` events and
     surface adversary context (actor / malware / MITRE / targeting). Single and
     batch (per-IoC) templates; supported-IoC taxonomy.

## Universal Best Practices

1. **Always load `dt-dql-essentials` first** — DQL syntax and function names
   differ from SQL. Confirm all functions before generating queries.
2. **Ground every query in a named template** — do not improvise Smartscape joins.
   The 3-way match, digest→CONTAINER→workload, and pod→node traversal patterns
   are precise; deviating produces silent zero-row results.
3. **Run the pre-flight check before the full 3-way enrichment** — external
   providers vary widely. Confirm at least one identifier path is populated
   before running the expensive append chain.
4. **Check `dt.smartscape_source.type` before trusting Path 1** — a non-null
   `dt.smartscape_source.id` is not proof of workload-level resolution; the
   field may point to a namespace, cluster, or cloud resource. Only K8s workload
   types (`K8S_DEPLOYMENT`, `K8S_DAEMONSET`, `K8S_STATEFULSET`, `K8S_CRONJOB`,
   `K8S_JOB`, `K8S_REPLICASET`) are eligible for workload enrichment via Path 1.
5. **Dedup early and after `append`** — dedup before joins to collapse
   re-ingested duplicates; dedup again after `append` because the same finding
   can match multiple paths.
6. **Tier 3 correlation is context only** — same namespace/cluster shared by
   two findings does not raise the exposure score. Never treat a cluster-level
   shared attribute as proof of entity-level relatedness.
7. **Route topology queries to `dt-obs-kubernetes`** — pod→node placement and
   Smartscape edge traversal patterns live in
   `dt-obs-kubernetes/references/pod-node-placement.md`. Do not re-author
   them here; reference them and apply the output in `correlation-and-coverage.md`.
8. **No `dt.system.bucket` filters** — security event data may live in any
   bucket; filtering by bucket risks hiding findings.
9. **THREAT_REPORT is the one `security.events` query allowed here — reverse
   lookup only.** `ioc-enrichment.md` attributes a *matched IoC* to reports
   (IoC → report). Broad THREAT_REPORT overviews, IOC rollups, and forward
   report → environment correlation stay in `dt-sec-insights`
   (`threat-intelligence.md`). Never author finding/posture queries here.

## Related Skills

| Skill | Role |
|---|---|
| `dt-dql-essentials` | **Load first.** Core DQL syntax, functions, Smartscape patterns. |
| `dt-sec-insights` | Consumer of mapping primitive; owns finding-schema queries and coverage counting logic. Owns **forward** threat-intel (report → environment correlation, overviews, IOC rollups) in `threat-intelligence.md`; this skill owns only the **reverse** IoC → report enrichment (`ioc-enrichment.md`). |
| `dt-sec-ioc-hunting` | Routes cross-evidence correlation and entity enrichment to this skill. |
| `dt-obs-kubernetes` | Pod→node topology; K8s entity placement patterns. |
| `dt-obs-hosts` | Host inventory; process-level context for HOST/PROCESS_GROUP findings. |
| `dt-obs-aws` / `dt-obs-azure` / `dt-obs-gcp` | Cloud Smartscape topology for cloud-entity enrichment. |
