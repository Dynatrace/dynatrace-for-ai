# Regex → DPL rewrites for tag value extraction

Companion to [autotagging.md](autotagging.md) Option C (central enrichment configuration). Use this when a classic auto-tagging rule derived its tag **value** from a regex, and you need the equivalent **DPL transformation** for a central enrichment rule.

## Contents

- [Why](#why)
- [Supported DPL matcher subset](#supported-dpl-matcher-subset)
- [Classic `valueFormat` placeholders](#classic-valueformat-placeholders)
- [Not supported](#not-supported)
- [Rewrite families](#rewrite-families)
- [Regex to DPL examples](#regex-to-dpl-examples)
- [One tag per rule](#one-tag-per-rule)
- [Caveats](#caveats)
- [Related references](#related-references)

## Why

Classic (2nd gen) auto-tagging extracted tag values with regexes. For example:

```text
{HostGroup:Name/.*K([A-Za-z0-9.\-]++)_?}
```

For a host group `aws_Kpayment_`, this captures everything after `K` up to `_` — the value `payment`.

In 3rd gen, central enrichment configuration derives the value with a **DPL transformation** on a OneAgent source attribute (`host.dt.host_group.id`, the host name, a process-group name, …; source attributes carry a `host.` / `process.` prefix — see [autotagging.md](autotagging.md#option-c--central-enrichment-configuration)). Same intent — recover a value from a structured name — but expressed in Dynatrace Pattern Language instead of a regex. The segment to keep is marked with `:value`; the enrichment rule maps that to the target key, so each rule produces exactly **one** primary tag.

## Supported DPL matcher subset

The tagging transformation uses a deliberately small DPL subset. These matchers are supported:

| Matcher | Purpose | Example |
|---|---|---|
| **Literal** | Fixed separators/markers (`'_'`, `'-'`, `'.'`, `'_E_'`) | `'_E_'` |
| **Character Group** | Token matching, with ranges and negation | `[A-Za-z0-9.-]+`, `[^_]+` |
| **Quantifiers** | Variable/repeated length | `*`, `+`, `{n}`, `{min,max}` |
| **Optional modifier** | Optional trailing marker or segment | `'_'?`, `( … )?` |
| **BOS / EOS** | Anchor to start / end of string (replaces `^` / `$`) | `BOS`, `EOS` |
| **LD** | Lazy "consume until the next required matcher" (replaces `.*?` / `.+?`) | `LD*`, `LD+` |
| **Sequence group** | Capture several matchers as one exported unit | `([A-Za-z0-9] [^_]*):value` |
| **Alternatives group** | Fixed choices, evaluated left to right (replaces `a\|b\|c`) | `('prod' \| 'uat' \| 'dev')` |
| **Export** | Mark the segment to extract as `:value` | `[^_]+:value` (the rule maps `:value` to the target primary tag key) |

Each enrichment rule extracts **one** segment (`:value`) into **one** primary tag — a transformation does not populate multiple tags at once. To derive several tags from the same input, create one rule per tag (see [One tag per rule](#one-tag-per-rule) below). There is **no partial output** — if the pattern doesn't match the input, no tag is written.

## Classic `valueFormat` placeholders

A classic auto-tagging rule's tag *value* comes from `valueFormat`, which is a
static literal, a `{Source:Attribute}` placeholder resolved against the Smartscape
entity, or a **concatenation of both**.
**Static literals are the common case** — in one reference tenant, 47 of 59
`valueFormat` values were literals and only 12 were placeholders. A literal needs
no translation: the value is known at design time, so it becomes a constant in the
enrichment rule. Only placeholders need the work below.

A **concatenation cannot be reproduced by one enrichment rule** — a rule writes
either a static value or an extracted one, not a literal joined to an extraction.
Migrate the placeholder part and drop the literal prefix, then rewrite the
downstream filters that matched the old composite value; see the worked example in
[autotagging.md](autotagging.md#option-c--central-enrichment-configuration).

Placeholders are **not regular expressions**, though a regex can be appended after
a `/` to extract part of the resolved value (`{HostGroup:Name/.*K([A-Za-z0-9.\-]++)_?}`)
— that trailing regex is what the rewrites in this file translate. The placeholder
itself resolves to a source field:

| Classic placeholder | Grail source field | Notes |
|---|---|---|
| `{HostGroup:Name}` | `dt.host_group.id` | Built-in primary field; no source-side work |
| `{Host:DetectedName}` | `host.name` | Built-in |
| `{Host:AWSNameTag}` | `aws.tags.name` (signal) / `tags:aws[name]` (entity) | Requires the AWS tag to be collected |
| `{ProcessGroup:KubernetesNamespace}` | `k8s.namespace.name` | Built-in |
| `{ProcessGroup:CloudFoundrySpaceName}` | — | No built-in equivalent; needs source-side enrichment |
| `{ProcessGroup:CloudFoundryAppId}` | — | No built-in equivalent; needs source-side enrichment |
| `{Host:Environment:<key>}` | — (enrichment source attribute `host.custom_metadata.<key>`) | Three-part form: reads **host custom metadata** named `<key>`. "Environment" here means neither a deployment stage nor a Dynatrace environment. Not a Grail field to query — it is an Option C source attribute; see the worked example in [autotagging.md](autotagging.md#option-c--central-enrichment-configuration) |
| `{ProcessGroup:Environment:<key>}` | — | Three-part form: reads process env var `<key>`. No queryable Grail field reads process environment; migrate by setting the primary tag at the source (`DT_TAGS` or `OTEL_RESOURCE_ATTRIBUTES` on the process) instead of reading it back. Whether the enrichment source attribute `process.custom_metadata.<key>` exposes this the way `host.custom_metadata.<key>` does for the host form is **not verified** — check the dropdown on the tenant before relying on it |
| `{Host:Kubernetes:label//<key>}` | `k8s.namespace.label.<key>` or `tags:k8s.labels[<key>]` | See [mass-data-filtering-strategy.md](../entity-queries/mass-data-filtering-strategy.md) |

**The list is open.** Classic exposes more placeholder sources than appear here, and
an unrecognised one is not a reason to skip the rule. Resolve it the same way: name
the entity attribute it reads, find that attribute in
[auto-tagging-field-mapping.md](../entity-queries/auto-tagging-field-mapping.md), and
report it if there is no equivalent.

**Where the four rows with no Grail equivalent lead.** A placeholder reading an
attribute that no Grail field carries cannot be reproduced by rewriting a rule — the
value has to be put on the data at the source. That is Option A or B in
[autotagging.md](autotagging.md), not a DPL problem. Say which of the two it is
rather than leaving the rule unmapped.

## Not supported

Do not rely on these — they are outside the shipped subset:

- **Lookbehind** and **backreferences** — not available.
- **Positive / negative lookahead** and **ENUM** — later-phase "nice to add"; many lookahead patterns can be rewritten with `LD` + a literal instead (see Family: lookahead-driven below).
- **`DATA`, `ARRAY`, `STRUCTURE`, `JSON`** and specialized time / IP / numeric matchers — out of scope for tagging transformations.

## Rewrite families

Most auto-tagging regexes fall into a handful of shapes. Match your regex to a family, then adapt the canonical DPL shape.

| Family | Regex shape | Canonical DPL |
|---|---|---|
| Single token by char class | `[^.]+`, `\d+`, `^[A-Z]{3}` | `[^.]+:value` · `[0-9]+:value` · `BOS [A-Z]{3}:value` |
| Prefix until delimiter | `^(.*?)_` | `BOS LD*:value '_'` |
| Nth delimiter-separated token | `^[^_]++_([^_]++)` | `BOS [^_]+ '_' [^_]+:value` |
| Capture after literal marker | `.*_E_([A-Za-z0-9.\-]++)_?` | `LD '_E_' [A-Za-z0-9.-]+:value '_'?` |
| Token before trailing delimiter | `([A-Za-z0-9].*?)_` | `([A-Za-z0-9] [^_]*):value '_'` |
| Last token from the right | `.*_([^_]++)` | `LD* '_' [^_]+:value` |
| Full shape with optional suffix | `^([^.]+?)(?:\.example\.biz)?$` | `BOS [^.]+:value ('.example.biz')? EOS` |
| Alternatives / enum | `prod\|uat\|dev` | `('prod' \| 'uat' \| 'dev'):value` |
| Fixed-position substring | `^....(.)` | `BOS [[:print:]]{4} [[:print:]]:value` |
| Lookahead-driven prefix | `.+?(?=\.)` | `LD+:value '.'` |

## Regex to DPL examples

A curated subset of the canonical rewrites, chosen for auto-tagging relevance. These are **guidance**, not copy-paste-tested production patterns.

| Classic regex | DPL rewrite |
|---|---|
| `.*_I_([A-Za-z0-9.\-]++)_?` | `LD '_I_' [A-Za-z0-9.-]+:value '_'?` |
| `^[^_]++_([^_]++)` | `BOS [^_]+ '_' [^_]+:value` |
| `^[^_]++_[^_]++_([^_]++)` | `BOS [^_]+ '_' [^_]+ '_' [^_]+:value` |
| `^(.*?)_` | `BOS LD*:value '_'` |
| `^(.*?)-` | `BOS LD*:value '-'` |
| `^([^_]++)` | `BOS [^_]+:value` |
| `[^.]+` | `[^.]+:value` |
| `\d+` | `[0-9]+:value` |
| `A_([A-Za-z1-9.\-]++)_` | `'A_' [A-Za-z1-9.-]+:value '_'` |
| `.*_E_([A-Za-z0-9.\-]++)_?` | `LD '_E_' [A-Za-z0-9.-]+:value '_'?` |
| `[^-]+$` | `(LD* '-')? [^-]+:value EOS` |
| `^([^.]+?)(?:\.example\.biz)?$` | `BOS [^.]+:value ('.example.biz')? EOS` |
| `Windows\|AIX\|Linux\|z/OS` | `('Windows' \| 'AIX' \| 'Linux' \| 'z/OS'):value` |
| `^....(.)` | `BOS [[:print:]]{4} [[:print:]]:value` |

## One tag per rule

A DPL transformation extracts a single value, so each primary tag needs its own rule. When several tags come from the same input, create one rule per tag — all sharing the same **source attribute** and **condition** — and move the `:value` marker to the segment each rule should capture.

For a host name `<env>-<team>-<region>-<role>-<index>` (e.g. `prod-payments-eu-web-01`), with the host-name source attribute and condition `matchesPhrase(host.name, "*-*-*-*-*")` (conditions use the unprefixed field name):

```text
primary_tags.environment:  LD:value '-' LD '-' LD '-' LD '-' LD EOS
primary_tags.team:         LD '-' LD:value '-' LD '-' LD '-' LD EOS
primary_tags.region:       LD '-' LD '-' LD:value '-' LD '-' LD EOS
primary_tags.role:         LD '-' LD '-' LD '-' LD:value '-' LD EOS
primary_tags.index:        LD '-' LD '-' LD '-' LD '-' LD:value EOS
```

If `host.name` doesn't match the 5-segment pattern, the extraction fails and no tag is applied for that rule — there is no partial output.

## Caveats

- These rewrites are **translation guidance**, not tested production patterns — validate each against your own host, host-group, and process-group names before rolling it out.
- `LD` must be followed by a required matcher (a literal, character group, or `EOS`) so it knows where to stop.
- Alternatives are evaluated left to right and stop at the first match — order longer/more-specific options first where they overlap.
- Cloud tags **collected by OneAgent** on AWS and Azure hosts are available as source attributes, but without DPL extraction — they map 1:1 only. GCP labels, and cloud-provider tags that only ever appear on records, are not available at all; use OpenPipeline (Option D) for those. See the Option C limitations in [autotagging.md](autotagging.md#option-c--central-enrichment-configuration).

## Related references

- [autotagging.md](autotagging.md) — the enrichment options; DPL transformations are used by Option C (central enrichment configuration)
- [autotagging.md — Never infer a source from a name](autotagging.md#never-infer-a-source-from-a-name) — resolve a placeholder from the attribute it reads, never from what the rule or key is called
- [mz-classification.md](../management-zones/mz-classification.md) — which auto-tag/MZ rules rely on infrastructure attributes (the best fit for central enrichment)
- [mz-export-schema.md](../management-zones/mz-export-schema.md) — reading the classic rule conditions you are translating
