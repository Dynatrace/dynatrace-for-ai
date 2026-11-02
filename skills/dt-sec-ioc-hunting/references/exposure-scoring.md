# Exposure Scoring

Synthesize hunt evidence into a 0-100 AI threat exposure score and produce a
structured exposure report.

## Contents

- [Score Bands (deterministic)](#score-bands-deterministic)
- [AI Fine-tuning Inside the Band](#ai-fine-tuning-inside-the-band)
- [Report Structure](#report-structure)
  - [Section 1 template](#section-1-template)
  - [Section 5 tables](#section-5-tables)
  - [Section 6 entity rendering](#section-6-entity-rendering)
  - [Section 8 - Filtered IoCs (last section)](#section-8---filtered-iocs-last-section)
- [Output Guidance](#output-guidance)

## Score Bands (deterministic)

| Evidence present | Score range |
|---|---|
| No matches in any source (clean zero) | 0 |
| Vulnerability match only (CVE found, no log/span/detection evidence) | 20-79 |
| Any log, span, or detection match | >= 80 |
| Multiple evidence types (for example log+detection, span+vuln) | >= 90 |

Cross-evidence correlation adjusts position within a band but never moves score
outside its assigned band.

After assigning the base band, evaluate convergence. When two or more evidence types matched
(for example logs and spans, or detection and CVE), load `dt-sec-contextualization`
`correlation.md` and name the tier; when only one evidence type matched, no load is needed and
the rationale states `single leg: no convergence`.

- Tier-1 topology convergence (exact entity match, or pod on vulnerable node):
top of band.
- Tier-2 (same workload or namespace): upper half of band.
- Tier-3 (same cluster only): context-only, no score movement.

Incomplete legs rule:
A **mandatory leg** is a leg that `SKILL.md` Mandatory Hunt Procedure requires for the retained IoC
types (logs, spans, and detections for IP/Domain/URL; the vulnerability step for CVEs; the detections
technique lookup for MITRE TTPs; logs for emails and hashes); "leg" below always means a mandatory leg.
A leg with `FETCH_EXEC_TIME_LIMIT` is INCONCLUSIVE, not a clean zero.
A score of 0 requires every mandatory leg to complete without warnings (clean-zero rule). A hunt the user
explicitly restricted to one leg is never scored (see `SKILL.md` Mandatory Hunt Procedure).

**Clean-zero rule (mandatory):**
When every mandatory leg completes without `FETCH_EXEC_TIME_LIMIT` and returns zero matches, the score is exactly **0%**. There are no exceptions:
- A limited search window (e.g., `now()-1h` instead of `now()-7d`) is **not** evidence of exposure and must not push the score above 0.
- Threat severity, actor reputation, or the age of the report are **not** fine-tuning inputs when there is no evidence — they are next-action context only.
- State the window constraint in the score rationale and recommend expansion as a next action; do not encode the uncertainty into the score itself.

## AI Fine-tuning Inside the Band

**Precondition:** AI fine-tuning applies only when at least one leg returned a match. If every mandatory leg returned zero matches and completed cleanly, the score is 0% and fine-tuning does not apply — see the clean-zero rule above.

When evidence exists, adjust only within the assigned band using:

- Threat severity (for example exploitation status, CVSS, exploit availability).
- Number of affected entities.
- Criticality of affected entities.
- Match specificity and recency.

The Section 1 rationale must list each factor considered with its effect, and say where in the
band the score sits (floor, lower half, upper half, or top) and why, so the same evidence can be
re-scored and compared. Always include the convergence tier (Tier-1, Tier-2, Tier-3, none, or
`single leg: no convergence`) even when it does not move the score.

Rule:
Never lower a multi-evidence score below the single-evidence band, and never
raise vuln-only above 79.

## Report Structure

Output pure Markdown (no fenced markdown wrapper).

1. Section 1 - Threat Summary and Score
2. Section 2 - Evidence Summary by Category
3. Section 3 - Vulnerability Details (if CVE matches)
4. Section 4 - Matched IP/URL/Domain Details (if detections/logs/spans match)
5. Section 5 - Matched IoCs (Table A), the one coverage line, and the legs line (per-leg result, windows, optional executed-queries note)
6. Section 6 - Affected and Related Entities (render each as `name (ID)`; list every entity the rollups returned)
7. Section 7 - Cross-Evidence Correlation and Topology (if multiple legs matched)
8. Section 8 - Filtered IoCs (not hunted) — last section; include ONLY when IoC Hygiene filtered an IoC, otherwise omit it entirely (no "None filtered" note)

### Section 1 template

```text
## AI-Threat-Exposure-Score: <score>%

**Threat:** <threat name>
**Tags:** <comma-separated tags>
**Score rationale:** <base band and why, then one line per factor: effect on position>
- Convergence tier: <Tier-1/2/3, none, or single leg: no convergence> - <effect>
- Threat severity: <exploitation status, CVSS, exploit availability> - <effect>
- Entities: <count and criticality> - <effect>
- Specificity and recency: <exact vs partial match, first/last seen> - <effect>
- Position in band: <floor | lower half | upper half | top> because <reason>
```

On a clean zero, replace the factor lines with the clean-zero rule and the windows searched.

### Section 5 tables

Section 5 skeleton (Table A only when at least one IoC matched; the coverage and legs lines always appear whenever a hunt ran):

```text
Table A - Matched IoCs:

| IoC value | Type | Primary/Secondary | Sources matched | Count | Discovered via |
|---|---|---|---|---|---|

Coverage: <N> of <M> hunted IoCs had no match (not listed)
Legs: <leg> <window> - <matches | zero | INCONCLUSIVE | not run: user-restricted scope>; one entry per mandatory leg
Executed queries: <one-line note, only when the user asked for the queries or the answer cites them>
```

The legs line is the single home for which legs returned zero, the windows searched (including an
automatic widening such as detections 2h then 24h), INCONCLUSIVE legs, and legs the user excluded.
Section 5 always exists, so none of this depends on Section 8 being present. The executed-queries
note, when written, is the last line of Section 5.

Do not list or name unmatched IoCs anywhere (no IoCs-hunted list, no per-IoC no-match rows, not in
the coverage line or the legs line, not in Section 8, which is only for FILTERED IoCs). `<N>` is the unmatched count
(clean zero: N = M).

`Primary/Secondary` values:
- **Primary** — from original user/advisory input.
- **Secondary** — discovered in matched evidence during the hunt (e.g. via `X-Forwarded-For`).

For secondary IoCs, the `Discovered via` column must state which primary IoC, which
header/field, and how many lines produced it (for example `x-forwarded-for on 705 log
lines, 2026-07-16T13:19Z–13:48Z, matched by 34.93.163.48`). Secondary IoCs that did not match are
likewise only counted.

### Section 6 entity rendering

Render every affected entity as `name (ID)`, for example `easytravel-backend (PROCESS_GROUP-0123456789ABCDEF)`,
using `affected_entity.name` and `affected_entity.id` (CVE leg) or the entity name and id columns
of the detection/log/span rollups. List **every entity the rollups returned**, not a sample: use a
compact table of one row per entity and never write "the rest summarised". Fall back to the bare ID
only when no name was returned.

The rollups bound every entity collector with `maxLength:` and every result with a row `limit`
(`SKILL.md` best practice 14), so "every entity returned" can be fewer than every entity that
exists. When an entity array's size is within one slot of its `maxLength:` (99 or more of 100 for most
entity collectors; the slot can hold a `null` that `arrayRemoveNulls` removed), or a
rollup still returns exactly its `limit` after the re-run rule in its hunt reference, write under the table
`Entity list capped at <N> for this leg; more may exist` and offer the explicit-request Drill-down of that
hunt reference. Do not run extra queries to enumerate the remainder unless the user asks.

### Section 8 - Filtered IoCs (last section)

When `ioc-intake.md` § IoC Hygiene filtered any IoC, end the report with this section:

| IoC | Type | Reason |
|---|---|---|

Reasons: `invalid: unspecified IP`, `invalid: loopback IP`, `invalid: private IP`,
`invalid: link-local IP`, `invalid: multicast or broadcast IP`, `invalid: malformed hash`, `unclassifiable`,
`noise: IP range (CIDR)`, `noise: empty-input hash`, `noise: internal-only hostname`, `noise: well-known public site or CDN`,
`noise: reserved or example domain`. Close with one sentence: these IoCs were not hunted, and
if the user asks to include them they will be hunted as normal IoCs. **Nothing may follow Section 8**: the legs line and any executed-queries note already sit in Section 5, so place any other appendix before it, or omit it. List up to 25 values
individually; beyond that, group by reason with counts and show the first 10. If **every** IoC
was filtered, no hunt ran: report no score, only this section.

## Output Guidance

- Include full details. Do not truncate material findings. This applies to the
  **report**, not the raw query output: hunt legs are summarize-first (one row per
  entity/source), which already preserves every affected entity, matched
  observable, count, and first/last-seen time — so the report stays complete
  without dumping raw records. Pull raw records via a reference's drill-down only
  when a specific record's context is material to a finding.
- Always state searched windows and which mandatory legs returned zero, in the Section 5 legs line (present whether or not Section 8 is).
- Mark any leg with `FETCH_EXEC_TIME_LIMIT` as INCONCLUSIVE and explain impact.
- Mark a secondary-IP extraction whose collector was capped (`ips_capped`, `next_level_ips_capped`) as
  INCOMPLETE and give the count as a lower bound (`secondary-observable-extraction.md` § Capped
  collectors). The gap does not lower the score; present the score as provisional until it is closed or
  the user accepts it.
- Do not let incomplete legs lower the score.
- **Score 0% when every mandatory leg is a clean zero. Never raise the score to reflect window-coverage uncertainty — put that in next actions instead.**
- Pair each finding with a concrete next action.
