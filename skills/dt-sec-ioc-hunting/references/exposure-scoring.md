# Exposure Scoring

Synthesize hunt evidence into a 0-100 AI threat exposure score and produce a
structured exposure report.

## Score Bands (deterministic)

| Evidence present | Score range |
|---|---|
| No matches in any source (clean zero) | 0 |
| Vulnerability match only (CVE found, no log/span/detection evidence) | 20-79 |
| Any log, span, or detection match | >= 80 |
| Multiple evidence types (for example log+detection, span+vuln) | >= 90 |

Cross-evidence correlation adjusts position within a band but never moves score
outside its assigned band.

After assigning the base band, load `dt-sec-contextualization` `correlation-and-coverage.md`
to evaluate convergence:

- Tier-1 topology convergence (exact entity match, or pod on vulnerable node):
top of band.
- Tier-2 (same workload or namespace): upper half of band.
- Tier-3 (same cluster only): context-only, no score movement.

Incomplete legs rule:
A leg with `FETCH_EXEC_TIME_LIMIT` is INCONCLUSIVE, not a clean zero.
A score of 0 requires all legs to complete without warnings (clean-zero rule).

**Clean-zero rule (mandatory):**
When every planned leg completes without `FETCH_EXEC_TIME_LIMIT` and returns zero matches, the score is exactly **0%**. There are no exceptions:
- A limited search window (e.g., `now()-1h` instead of `now()-7d`) is **not** evidence of exposure and must not push the score above 0.
- Threat severity, actor reputation, or the age of the report are **not** fine-tuning inputs when there is no evidence — they are next-action context only.
- State the window constraint in the score rationale and recommend expansion as a next action; do not encode the uncertainty into the score itself.

## AI Fine-tuning Inside the Band

**Precondition:** AI fine-tuning applies only when at least one leg returned a match. If all legs returned zero matches and completed cleanly, the score is 0% and fine-tuning does not apply — see the clean-zero rule above.

When evidence exists, adjust only within the assigned band using:

- Threat severity (for example exploitation status, CVSS, exploit availability).
- Number of affected entities.
- Criticality of affected entities.
- Match specificity and recency.

Rule:
Never lower a multi-evidence score below the single-evidence band, and never
raise vuln-only above 79.

## Report Structure

Output pure Markdown (no fenced markdown wrapper).

1. Section 1 - Threat Summary and Score
2. Section 2 - Evidence Summary by Category
3. Section 3 - Vulnerability Details (if CVE matches)
4. Section 4 - Matched IP/URL/Domain Details (if detections/logs/spans match)
5. Section 5 - IoC Coverage Tables
6. Section 6 - Affected and Related Entities
7. Section 7 - Cross-Evidence Correlation and Topology (if multiple legs matched)

### Section 1 template

```text
## AI-Threat-Exposure-Score: <score>%

**Threat:** <threat name>
**Tags:** <comma-separated tags>
**Score rationale:** <1-2 sentences>
```

### Section 5 tables

Table A - Matched IoCs:

| IoC value | Type | Primary/Secondary | Sources matched | Count | Discovered via |
|---|---|---|---|---|---|

`Primary/Secondary` values:
- **Primary** — from original user/advisory input.
- **Secondary** — discovered in matched evidence during the hunt (e.g. via `X-Forwarded-For`).

For secondary IoCs, the `Discovered via` column must state which primary record
and which header/field produced it (for example `X-Forwarded-For in log record
2026-07-16T13:19Z matched by 34.93.163.48`). Unmatched IoCs (primary or secondary)
are not included in this table and are not reported.

## Output Guidance

- Include full details. Do not truncate material findings. This applies to the
  **report**, not the raw query output: hunt legs are summarize-first (one row per
  entity/source), which already preserves every affected entity, matched
  observable, count, and first/last-seen time — so the report stays complete
  without dumping raw records. Pull raw records via a reference's drill-down only
  when a specific record's context is material to a finding.
- Always state searched windows and which legs returned zero.
- Mark any leg with `FETCH_EXEC_TIME_LIMIT` as INCONCLUSIVE and explain impact.
- Do not let incomplete legs lower the score.
- **Score 0% when all legs are clean zeros. Never raise the score to reflect window-coverage uncertainty — put that in next actions instead.**
- Pair each finding with a concrete next action.
