---
name: dt-obs-log-semantic-mapping
description: "Suggest and validate semantic dictionary (SD) mappings for audit log integrations using raw vendor log payloads or live ingested events. Use when: mapping a vendor audit log feed, authentication logs, user activity logs to the Dynatrace SD; checking required semantic fields; proposing OpenPipeline processor extraction rules based on DQL; running runtime validation (fetches live logs by log.source, then applies static validation)."
license: Apache-2.0
---

# dt-obs-log-semantic-mapping

Build and validate semantic-dictionary-aligned mappings for audit log integrations.

## Purpose

Use this skill when a user wants to:

- **Suggest** a mapping from a raw vendor audit log payload to Dynatrace `fetch logs` fields (Workflow A).
- **Validate** a mapping against a pasted ingested log event (Workflow B1 — static).
- **Validate** against live tenant data via live tenant access (Workflow B2 — runtime: fetches logs by `log.source`, then runs B1 on the result).

## Log Classes

| Class | Description | Key namespaces | Example sources |
|---|---|---|---|
| `authentication` | Login, logout, MFA, token | `audit.*`, `actor.*`, `browser.*`, `device.*` | CyberArk, Okta, Azure SignInLogs |
| `authorization` | Access decisions, permission changes | `audit.*`, `actor.*`, `object.*` | CyberArk, Okta |
| `user_action` | CRUD on platform resources | `audit.*`, `actor.*`, `object.*`, `product.*` | Okta, GitHub, Sonatype |
| `http` | HTTP request/response (WAF, network devices) | `http.*`, `url.*`, `server.*`, `geo.*`, `client.*` | Akamai SIEM, Cloudflare |

## Workflows

| Mode | Input | Source |
|---|---|---|
| **Workflow A** — Suggest mapping | Raw vendor log payload | `references/mapping-workflow.md § Workflow A` |
| **Workflow B1** — Static validation | Pasted ingested log event | `references/mapping-workflow.md § Workflow B1` |
| **Workflow B2** — Runtime validation | `log.source` value + live tenant access | `references/runtime-validation.md` — fetches logs, then runs B1 |

## Key Concepts

**Content field burial:** The primary validation concern. Fields in `content` (the raw vendor payload) that could be promoted to top-level semantic attributes but are not. The skill always inventories buried vs promoted fields and proposes OpenPipeline extraction rules to fix gaps.

> **Prerequisite:** When proposing OpenPipeline processor extraction rules, load the `dt-dql-essentials` skill first. OpenPipeline processors use DQL functions (`parse`, `fieldsAdd`, `splitString`, etc.) — using non-DQL syntax produces invalid rules.

**Sparse mappings are valid:** Integrations like GitHub or Sonatype may only populate core fields. Minimum required: `timestamp`, `log.source`, `content`, `loglevel`, `audit.action`, `audit.identity`.

## References

- `references/data-model-notes.md` — Log SD field taxonomy, audit namespace, enums, sample-derived patterns and known discrepancies
- `references/mapping-workflow.md` — Intake checklist, Workflow A and B1 procedures, content field analysis, field priority order
- `references/validation-rules.md` — Required fields, content/enum/type rules, discrepancy severity
- `references/openpipeline-constraints.md` — OpenPipeline processor command/function/operator/matcher restrictions; `parseJson` unavailability + `parse`→`fieldsFlatten` alternative; iterative operators for array casting
- `references/report-format.md` — Mapping table, diff table, OpenPipeline sketch, Validation Summary templates
- `references/runtime-validation.md` — Workflow B2: fetch live records, then run B1
- `samples/audit-logs.json` — Mapped samples: CyberArk, Okta, Azure SignInLogs, Sonatype, GitHub
- `samples/http-logs.json` — Mapped samples: Akamai SIEM (WAF/HTTP class)
- [Dynatrace Log Semantic Dictionary](https://docs.dynatrace.com/docs/semantic-dictionary/model/log)
