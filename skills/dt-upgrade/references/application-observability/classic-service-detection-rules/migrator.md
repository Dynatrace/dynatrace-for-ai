# Running the `sdr-migrator`

Load this only after the tracking query in
[classic-service-detection-rules.md](classic-service-detection-rules.md) found affected rules
**and** the user asked to migrate them.

The tool reads each rule, queries live spans and process groups in Grail to find
surviving-attribute conditions that select **exactly** the same target set, verifies the match
against live data, and writes a ready-to-deploy Config v1 replacement body for every coverable
rule. It is read-only: it has no `apply` command and cannot write to the tenant. Deploying the
result is the customer's step and is out of scope here.

## Prerequisites

- **Python 3.12+**.
- The migrator lives in `./migrator/` (same folder as this file). One-time setup, needs network
  access to fetch `httpx` and `pydantic`:

  ```bash
  cd migrator
  python3 -m venv .venv
  .venv/bin/pip install -e .
  ```

  All commands below run as `.venv/bin/sdr-migrator <command>` from `migrator/`.
- **Two tokens** — the tool reads the classic Config v1 API *and* Grail:
  - `DT_PLATFORM_TOKEN` — platform token (`dt0s16.*`) with `storage:*:read` + `ReadConfig`, for
    all DQL.
  - `DT_CLASSIC_TOKEN` — classic token (`dt0c01.*`) with **Read configuration**, for
    `GET /api/config/v1/service/detectionRules`.
  - Each prefix is enforced; swapping them fails immediately with a clear error. Do not request
    any write scope.
- `DT_TENANT` — the tenant URL, either the classic host or the `.apps` platform host. The
  migrator derives the other.
- **Live traffic during the run.** Replacements are derived from observed spans; a rule whose
  endpoints are dormant cannot be resolved.

## Steps

1. Confirm `DT_TENANT`, `DT_PLATFORM_TOKEN`, and `DT_CLASSIC_TOKEN` are set. Ask the customer
   for any missing token with the scopes above.
2. Check connectivity and inventory (both read-only):

   ```bash
   .venv/bin/sdr-migrator dql-smoke --tenant https://<env>.dynatrace.com
   .venv/bin/sdr-migrator list-rules --tenant https://<env>.dynatrace.com
   ```

3. Generate replacements. Note the workdir from the printed report path:

   ```bash
   .venv/bin/sdr-migrator run --tenant https://<env>.dynatrace.com
   ```

   Use the **default window** (`now()-2h`). Widen `--window` only reactively, for rules that
   came back as *Not observed in live traffic*; re-run just those with `--rule-ids <id> ...`.
4. Read `<workdir>/summary.json` for the counts and `<workdir>/report/report.html` for per-rule
   detail. Classify every rule by bucket (see below).
5. The workdir **is** the upgrade package — keep it as-is. Each `report/<rule-id>.json` is one
   complete Config v1 create payload. Do not re-assemble or hand-edit them.
6. Report to the user: the workdir path, the per-bucket counts, and the named rules needing
   manual rework or review. Then stop — deployment is theirs.

## Output

```
workdir/run-20260714-071812/
├── summary.json                        # verdict counts + cache stats
├── report/
│   ├── report.html                     # bucketed, per-rule human report
│   └── <rule-id>.json                  # one POST-ready body per migrated rule
└── cache/                              # DQL response cache, not part of the package
```

`summary.json` is keyed by verdict:

```json
{
  "migrated": 1,
  "no_replacement": 1,
  "skipped_not_deprecated": 2,
  "unknown_rule_ids": [],
  "cache": { "total": 7, "hits": 0, "misses": 7 }
}
```

| Bucket in `report.html` | Verdict | Meaning | Action |
|---|---|---|---|
| Fully Resolved | `migrated` | Exact match verified against live data (possibly after negation, demotion, or a window retry — the result is still exact). | Ship as-is. |
| Approximate — review before applying | `migrated` (best-effort) | An under-selecting candidate was accepted after a retry; may not match everything the original did. | Ship, flag for review. |
| Not Coverable — manual migration required | `no_replacement` (with data), `untranslatable` | Traffic seen but no safe replacement (over-selection or no viable candidates), or a condition inexpressible against spans. | Hand off for manual rework. |
| Not observed in live traffic | `no_replacement` (empty target set) | Nothing failed — nothing to measure. Scope resolved to zero process groups, or no spans in the window. | Re-run wider `--window`, or ask whether the rule is still needed. |
| Processing error — contact Dynatrace Support | `error` | The rule crashed during evaluation. A genuine defect, not a coverage gap. | Report with the card's reason. |
| Skipped / out of scope | `skipped_disabled`, `skipped_not_deprecated` | Disabled, or no deprecated conditions. | Nothing to do. |

The report also lists **duplicate rule groups** — rules with identical type, conditions, and
management zones. Surface these; they are consolidation candidates.

## Example replacement body

Original: a `FULL_WEB_REQUEST` scoped to management zone `Payments PROD`, with a surviving
`SERVER_NAME` condition and a deprecated `PG_TAG` on the non-primary key `team`. Generated
`report/<rule-id>.json`:

```json
{
  "type": "FULL_WEB_REQUEST",
  "name": "payment-api detection",
  "description": null,
  "enabled": false,
  "conditions": [
    {
      "attributeType": "SERVER_NAME",
      "compareOperations": [
        { "type": "STRING_EQUALS", "negate": false, "ignoreCase": false,
          "values": ["ApacheProxy:8081"] }
      ]
    },
    {
      "attributeType": "URL_PATH",
      "compareOperations": [
        { "type": "STARTS_WITH", "negate": false, "ignoreCase": false,
          "values": ["/api/payments"] }
      ]
    }
  ]
}
```

What that shows about every generated body:

- `managementZones` and the non-primary `PG_TAG` condition — the deprecated parts — are gone.
- The verified replacement (`URL_PATH STARTS_WITH /api/payments`) was appended; surviving
  conditions like `SERVER_NAME` are preserved verbatim.
- `id`, `metadata`, and `order` are stripped — server-assigned or read-only, and a `POST`
  carrying them is rejected. This is a **create** payload, not a copy of the source rule.
- `enabled` is always `false`, regardless of the original.

A `PG_TAG` on a *primary* Grail tag survives and is emitted as a structured tag condition rather
than a string comparison:

```json
{
  "attributeType": "PG_TAG",
  "compareOperations": [
    { "type": "TAG", "compareKeyOnly": false,
      "tags": [{ "context": "CONTEXTLESS", "key": "primary_tags.app", "value": "apache" }] }
  ]
}
```

Note these bodies use the **Config v1** shape (`attributeType`, `compareOperations`), which
differs from the Settings 2.0 shape (`attribute`, `compareOperationType`) that the tracking
query reads. Same rules, two representations — do not mix them.

## Validation

- **Tool self-verification** — a body is emitted only when the replacement conditions select the
  original target set exactly, checked with live queries. Bodies exist *only* for `migrated`
  rules; there is no file for any other verdict.
- **Agent checks** — every `migrated` count in `summary.json` has a matching
  `report/<rule-id>.json`; the verdict counts sum to the rule total; no emitted body contains
  `id`, `metadata`, or `order`, and every one has `"enabled": false`.
- **Hand-off** — report the workdir path and per-bucket counts, and confirm nothing was
  uploaded. Deployment (Monaco, Terraform, `dtctl`, or a direct `POST` to
  `/api/config/v1/service/detectionRules/FULL_WEB_REQUEST` or `.../FULL_WEB_SERVICE`) is the
  customer's step. Nothing in the tenant changes until they take it, so do not re-run the
  tracking query as a check — it will return exactly the same rules it did before the run.
