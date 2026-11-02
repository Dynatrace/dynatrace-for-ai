# Running the `ra-migrator`

Load this only after the tracking query in
[request-attributes.md](request-attributes.md) found affected request attributes **and** the user
asked to migrate them.

The tool reads each Request Attribute, queries live spans and topology entities in Grail to
reconstruct the **Target Set** each affected Data Source selected, finds surviving-attribute
replacement Scopes that select **exactly** that set, verifies the match against live data, and
writes a ready-to-deploy Config v1 replacement body for every coverable Request Attribute. It is
read-only: it has no `apply` command and cannot write to the tenant. Deploying the result is the
customer's step and is out of scope here.

## Prerequisites

- **Python 3.12+**.
- The migrator lives in `./migrator/` (same folder as this file). One-time setup, needs network
  access to fetch `httpx` and `pydantic`:

  ```bash
  cd migrator
  python3 -m venv .venv
  .venv/bin/pip install -e .
  ```

  All commands below run as `.venv/bin/ra-migrator <command>` from `migrator/`.
- **One token** — unlike some sibling migrators, this tool uses a single credential for both the
  classic Config v1 API *and* Grail:
  - `DT_PLATFORM_TOKEN` — a platform token (`dt0s16.*`) with scopes
    **`ReadConfig, storage:spans:read, storage:entities:read`**. The same token is sent as
    `Api-Token` to the classic host to read request attributes and as `Bearer` to the platform
    host for all DQL.
  - The prefix is enforced: a classic Api-Token (`dt0c01.*`) is rejected immediately with a clear
    error. Do not request any write scope — none is needed or used.
  - There is deliberately **no `--token` flag**; the credential comes from `DT_PLATFORM_TOKEN`
    only, so it cannot leak through the process list or shell history.
- `DT_TENANT` — the tenant URL, either the classic host or the `.apps` platform host. The migrator
  derives the other. (`DT_CLASSIC_URL` / `DT_PLATFORM_URL`, or `--classic-url` / `--platform-url`,
  override derivation when both hosts must be given explicitly.)
- **Live traffic during the run.** Replacements are reconstructed from observed spans; a Data
  Source whose members are dormant cannot be verified and comes back needing a re-run.

## Steps

1. Confirm `DT_TENANT` and `DT_PLATFORM_TOKEN` are set. Ask the customer for the token with the
   scopes above if it is missing.
2. Check connectivity and grants (read-only — five probes: request attribute list, one body read,
   an entity query, a span query, and span field metadata):

   ```bash
   .venv/bin/ra-migrator check-connection --tenant https://<env>.dynatrace.com
   ```

3. Generate replacements. Note the workdir from the printed report path:

   ```bash
   .venv/bin/ra-migrator run-migration --tenant https://<env>.dynatrace.com
   ```

   Use the **default window** (`2h`). Widen `--window` (a whole number and `m`, `h` or `d`) only
   reactively, for Request Attributes that came back **No verdict** — dormant members or a silent
   Target Set — then re-run.
4. Read `<workdir>/summary.json` for the funnel counts, health flags and per-unit verdicts, and
   `<workdir>/report.html` for the bucketed, per-Data-Source detail. Classify every Request
   Attribute by bucket (see below).
5. The workdir **is** the upgrade package — keep it as-is. Each `artifacts/<id>.json` is one
   complete Config v1 create payload. Do not re-assemble or hand-edit them.
6. Report to the user: the workdir path, the per-bucket counts, and the named Request Attributes
   needing manual rework, deletion, or a re-run. Then stop — deployment is theirs.

## Output

```
workdir/run-20260714T071812Z/
├── summary.json                     # scan funnel, health flags, per-unit verdicts — the machine contract
├── report.html                      # bucketed, per-Data-Source human report
├── artifacts/
│   └── <request-attribute-id>.json  # one Config v1 create body per emitted Request Attribute
└── cache/                           # DQL response cache, not part of the package
```

`summary.json` is the contract a consuming skill classifies on — every field it branches on is a
value, never prose (`detail` is free text and nothing parses it):

```json
{
  "run": {
    "tenant": "https://<env>.apps.dynatrace.com",
    "window": { "requested": "2h", "timeframe": "from:\"...\", to:\"...\"" }
  },
  "health": {
    "primary_tag_discovery_unavailable": false,
    "some_read_capped": false,
    "some_attribute_unreadable": false
  },
  "scan": {
    "scanned": 12,
    "enabled": 9,
    "obsolete": 1,
    "affected": 4,
    "disabled": 3,
    "unprocessable": 0,
    "affected_by_reason": {
      "service-technology": 2,
      "non-primary-process-group-tag": 3
    },
    "disabled_carrying_deprecated": 1
  },
  "request_attributes": [
    {
      "id": "REQUEST_ATTRIBUTE-ABC",
      "verdict": "covered",
      "reason": "every-data-source-covered",
      "detail": "",
      "artifact": "artifacts/REQUEST_ATTRIBUTE-ABC.json",
      "data_sources": [
        { "index": 0, "verdict": "covered", "reason": "the-verification-read", "detail": "" }
      ]
    }
  ]
}
```

The scan funnel narrows `scanned → enabled → obsolete → affected` and each Request Attribute is
counted once. `affected_by_reason` always carries both reasons, so a run that found none of one
still says `0`; a Request Attribute carrying both reasons contributes to both. The three `health`
flags let a consumer qualify its report rather than overstate the run.

The `report.html` groups Request Attributes by the **action** their verdict implies. Buckets:

| Section in `report.html` | Request Attribute verdict | Meaning | Action |
|---|---|---|---|
| Deploy the Artifact | `covered` | Every Data Source was covered (its replacement verified exact against live data) or had a service technology that narrowed nothing dropped. | Ship `artifacts/<id>.json` as-is. |
| Deploy the Artifact | `partially-covered` | At least one Data Source is covered and at least one was Neutralised. The body deploys at a named cost: covered sources capture, Neutralised ones ship disabled. | Ship, flag the disabled Data Sources for hand rework. |
| Rework by hand | `not-coverable` | Every Data Source was Neutralised — traffic seen but no safe replacement (over-selection, no viable candidate, or a refutation). No Artifact is written. | Hand off for manual rework. |
| Delete | `obsolete` | Captures nothing Phase 3 keeps: every enabled Data Source captures only onto external service calls, or there is no enabled Data Source at all. | Delete the Request Attribute. |
| Delete | `selects-nothing` | Every Data Source's Scope resolved an empty Target Set in the window. | Re-run wider first; if still empty, delete. |
| Re-run | `no-verdict` | The run could not measure it — dormant members, a capped read, or the tenant emits no Primary Tag key. Never a claim it cannot be covered. | Re-run (wider `--window`, or once traffic returns) before deciding. |
| Re-run | `unprocessable` | The Request Attribute body could not be read or parsed. One poisoned config costs one row; the run continues. | Re-run; if it persists, inspect the config. |

## Example replacement body

Original: a Request Attribute with one Data Source scoped by a deprecated `serviceTechnology` and a
deprecated non-primary `tagOfProcessGroup` (`team:payments`), over a surviving `processGroup`. The
migrator reconstructed the Target Set, harvested a Primary Tag that reproduces it, and verified it
against live spans. Generated `artifacts/<id>.json` (a **complete** `RequestAttributeDto`, not a
diff):

```json
{
  "name": "payment.customer",
  "enabled": true,
  "dataSources": [
    {
      "enabled": true,
      "source": "REQUEST_ATTRIBUTE",
      "scope": {
        "processGroup": "PROCESS_GROUP-0123456789ABCDEF",
        "tagOfProcessGroup": "primary_tags.app:apache"
      }
    }
  ]
}
```

What that shows about every generated body:

- The deprecated parts — `serviceTechnology` and the non-primary `tagOfProcessGroup` — are gone.
- Surviving conditions (`processGroup` here) are carried through verbatim, and the verified
  replacement (the Primary Tag `primary_tags.app:apache`) fills a free Scope slot. Where the
  replacement fans out — one Data Source per process group, or one per Primary Tag value — the
  original Data Source becomes several identical but for their Scope.
- A covered Data Source is emitted `"enabled": true`. A Neutralised one (in a `partially-covered`
  body) is emitted `"enabled": false` keeping its **original** Scope, so a human sees what it did
  and recovery is a single `enabled` edit.
- `metadata` is stripped — it is server-owned (`@Schema(READ_ONLY)`) and a body carrying it is
  rejected. Everything else on the original body is copied through untouched.

A surviving **Primary** Tag (already `primary_tags.`-prefixed) is preserved as its original wire
string; only reconstructed tags are written fresh, colons in the value escaped so they round-trip.

## Validation

- **Tool self-verification** — a body is emitted only for `covered` and `partially-covered`
  Request Attributes, and a covered Data Source's replacement is shipped enabled only when it was
  proven to select the Target Set exactly (by the fan-out construction, a host-group full-membership
  read, a service-closure read, or the verification read). No file exists for any other verdict.
- **Agent checks** — every Request Attribute whose `summary.json` verdict is `covered` or
  `partially-covered` has a matching `artifacts/<id>.json` (and no other verdict does); the scan
  funnel is disjoint (`scanned ≥ enabled ≥ obsolete + affected`); no emitted body contains
  `metadata`; and the `health` flags are clear (or, if not, the report is qualified accordingly —
  a capped read or an unreadable attribute means the run undercounts).
- **Hand-off** — report the workdir path and per-bucket counts, and confirm nothing was uploaded.
  Deployment (Monaco, Terraform, `dtctl`, or a direct `POST` to `/api/config/v1/service/requestAttributes`)
  is the customer's step. They ship enabled per Data Source as generated — review, then remove the
  originals so both do not capture at once. Nothing in the tenant changes until they take it, so do
  not re-run the tracking query as a check: it will return exactly the same request attributes it
  did before the run.
```