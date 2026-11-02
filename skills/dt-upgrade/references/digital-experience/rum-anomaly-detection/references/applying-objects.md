# Applying generated objects to a tenant

The migrator's `--apply` step (see the main reference) does this via `dtctl create settings`,
entirely in memory — no intermediate file is ever written or read back. This file documents
what that step does under the hood, for anyone creating the equivalent objects some other way
(`monaco`, `terraform`, a direct API call, etc.).

## Target API

The platform Settings API — `dtctl create settings -f <file> --schema <schema-id> --scope
<scope> [--validate-only]`. This is **not** the classic Environment API used for reading
2nd gen configuration; that API is read-only for these classic schemas.

Required scopes for the actor used in creation: `davis:analyzers:execute` (custom alerts run
as Davis analyzers).

## Before applying

- `_meta` is traceability only, attached to each object in memory during the upgrade, and
  is stripped before creation — it is not part of either schema.
- Validate first. `--validate-only` on the create call checks the object against the API
  without creating anything. Fix any shape errors before creating for real.
- Health alert objects (`builtin:health-experience.frontend-alert`) carry no `scope`; the
  target frontend lives in `value.frontends`. Custom metric alert objects
  (`builtin:davis.anomaly-detectors`) are created at `scope: "environment"` — the schema also
  accepts `scope: "tenant"`, but existing objects on a live tenant were observed using
  `environment`, so the migrator matches that.
- Duplicate detection already runs before any create call, matching on alertKey + frontend
  for health alerts and on the analyzer's DQL expression for custom alerts — regardless of
  whether the existing object is enabled or tuned differently. Nothing the migrator creates
  should collide with an existing object. A retry after a partial failure is safe.

## Example (using dtctl directly)

```bash
TOKEN=$(dtctl ctx token <context-name>)

dtctl create settings \
  -f <(echo '{"alertKey": "errorRateExceptions", "analyzerType": "SeasonalBaseline", "enabled": true, "frontends": ["FRONTEND-<ID>"], "actor": "<uuid>", "title": "..."}') \
  --schema builtin:health-experience.frontend-alert \
  --scope environment \
  --validate-only
```

For bulk creation across many objects, use the migrator's own `--apply` flag rather than
scripting `dtctl create settings` per object by hand — it already handles stripping `_meta`,
batching, and reporting per-object results (see the main reference).

## Scale

A full-tenant upgrade can produce several hundred objects (777 health alerts + a handful of
custom alerts observed on one tenant). Creation is one API call per object; the migrator
reports per-object errors rather than assuming an all-or-nothing result. This is also why the
main reference recommends creating incrementally (one or more apps at a time, validated
before continuing) rather than defaulting to a single whole-tenant create.
