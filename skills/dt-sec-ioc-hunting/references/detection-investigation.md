# Detection Investigation (repeat and fan-out patterns)

Behavior-based investigation of `DETECTION_FINDING` events — no IoC list required. Use after a hunt
or triage surfaces an attacker IP, a noisy rule, or a suspicious target, to ask: is one source
hitting many targets, is one kind of attack hitting a target repeatedly, is one rule re-firing
on one object?

## Contents

- [Ownership boundary — read first](#ownership-boundary--read-first)
- [Same source IP attacking multiple targets (cross-provider)](#same-source-ip-attacking-multiple-targets-cross-provider)
- [Repeated attack patterns by source IP + attack type (cross-provider)](#repeated-attack-patterns-by-source-ip--attack-type-cross-provider)
- [Same rule / attack firing on the same object repeatedly (cross-provider)](#same-rule--attack-firing-on-the-same-object-repeatedly-cross-provider)

## Ownership boundary — read first

Detection field semantics, provider routing, and the **Top attacker IPs** base query are owned by
**dt-sec-insights** `detections.md` (§ Top attacker IPs, § Scope variants). Load it and build on that
query; this file only adds the investigation shapes on top. Detections are one-shot events, but the
**same kind** can repeat: the same `finding.id` re-arriving (rare; some external providers re-ingest
unchanged findings), or — typically — the same attack pattern (`finding.type`, or `detection.id` for
Automated Detections) hitting the same target repeatedly.

Default window follows the base query (`24h`). To narrow the source or provider, apply a
**Scope variant** from `detections.md` — never by default.

## Same source IP attacking multiple targets (cross-provider)

Fan-out: one IP hitting many distinct targets (reconnaissance / wide-scan). Take the **Top attacker IPs**
query from `detections.md`, **drop its trailing `| sort Detections desc | limit 25`** (a `limit` before the
filter would keep only the 25 busiest IPs and miss a low-volume source that hits many targets), add
`SampleTargets = arraySlice(collectDistinct(object.name), from: 0, to: 10)` to the summarize, then append:

```dql-snippet
| filter DistinctTargets >= 2
| fieldsAdd DurationMin = round((toLong(LastSeen) - toLong(FirstSeen)) / 1000000000.0 / 60, decimals: 1)
| sort DistinctTargets desc, Detections desc
| limit 25
```

`>= 2` is the threshold; raise to `>= 5` for wide-scan recon. Long `DurationMin` + high `Detections` = slow-burn;
short = automated burst. Groups by `object.id` (cross-provider target id), not a classic process-group id (null for external).

## Repeated attack patterns by source IP + attack type (cross-provider)

Distinct from "Same IP attacking multiple targets": group by **both** IP and attack type to surface one kind of attack
hitting infrastructure repeatedly. Take the **Top attacker IPs** query from `detections.md`, change its `by:` to
`{SourceIP = ip, AttackType = finding.type}`, **drop its trailing `| sort Detections desc | limit 25`**
(the same truncation applies: the filter below must see every group), then append:

```dql-snippet
| filter Detections >= 5
| fieldsAdd DurationMin = round((toLong(LastSeen) - toLong(FirstSeen)) / 1000000000.0 / 60, decimals: 1)
| sort Detections desc
```

`>= 5` is a noise-floor heuristic — adjust. Long duration + high count = slow-burn campaign; short = automated burst.

## Same rule / attack firing on the same object repeatedly (cross-provider)

Groups by the rule or attack identity and `object.id` to surface "this kind of detection keeps hitting the
same target" — RAP attacks against a process group, Automated Detections rules re-firing on a K8s pod, external
findings re-arriving against one cloud resource. `finding.type` is an attack **class**, not a rule: two different
Automated Detections rules with the same type, each firing once on one object, would otherwise add up to
`Fires >= 3` as if one rule fired repeatedly. So the identity is `detection.id` (stable rule UUID, populated for
Automated Detections) and falls back to `finding.type` for providers without it.

```dql
fetch security.events, from:now()-7d
| filter event.type == "DETECTION_FINDING"
| filter isNotNull(finding.type) AND isNotNull(object.id)
| fieldsAdd RuleKey = coalesce(detection.id, finding.type)
| summarize {
    Fires = count(),
    Providers = collectDistinct(event.provider),
    Products = collectDistinct(product.name),
    SampleTitle = takeFirst(finding.title),
    Kind = takeFirst(finding.type),
    ObjectName = takeFirst(object.name),
    ObjectType = takeFirst(object.type),
    FirstSeen = takeMin(timestamp),
    LastSeen = takeMax(timestamp)
  }, by: {
    RuleKey,
    ObjectID = object.id
  }
| filter Fires >= 3
| fieldsAdd DurationHours = round((toLong(LastSeen) - toLong(FirstSeen)) / 1000000000.0 / 3600, decimals: 1)
| sort Fires desc
| limit 50
```

`Fires >= 3` is a noise-floor — adjust. **Long duration + high fires** = unaddressed persistent issue; **short
duration + high fires** = tuning issue (noisy rule or attack pattern). The rollup groups by the stable
`{RuleKey, ObjectID}`; the object name and type are carried with `takeFirst`, so a target renamed inside the window
is still one group. To narrow to a target type (e.g. pods), insert this line **before the `summarize`** (right after
the `isNotNull` filter): the rollup output keeps none of the pod fields, so the same line after the `summarize` would
drop every row:

```dql-snippet
| filter isNotNull(dt.smartscape.k8s_pod) OR isNotNull(k8s.pod.uid) OR isNotNull(k8s.pod.name)
```

`object.type` is not a reliable pod discriminator for detections (RAP reports `PROCESS`; `KUBERNETES_POD` and
`k8spod` never occur there). Pod identity lives in the Smartscape and `k8s.*` fields: Dynatrace RAP carries all of them
(`dt.smartscape.k8s_pod` / `.k8s_namespace` / `.k8s_node` / `.k8s_deployment`, `k8s.pod.name` / `.uid`,
`k8s.cluster.name`, `k8s.namespace.name`, `k8s.workload.name`); some external detections carry only a subset
(for example `k8s.pod.name` without the Smartscape pod id) and most carry none, so match any of the three.

To narrow to a source, apply a scope variant from `detections.md`.
