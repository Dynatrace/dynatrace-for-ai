# Shared scan scripts

Code reused by more than one `dt-upgrade` topic reference. Stdlib only — nothing here needs an
install step.

| File | Role |
|---|---|
| `config_scan.py` | The shared configuration-scan layer: transports, the agreed configuration sources, per-source coverage state, cached-result stripping, tenant-URL derivation, links |

## `config_scan.py`

Every Phase 3 topic asks the same question of a tenant — *which of the agreed configuration sources
reference the thing I care about?* — and differs only in the detector applied to the bodies. This
module is that common half, so a topic scanner only writes its detector and its report.

- **Sources.** Dashboards, notebooks, SLOs, Site Reliability Guardians, and custom alerts, fetched
  whole so a caller can match anything. Two of those types are several sources each — SLOs are the
  Service-Level Objectives app (`dynatrace.service.level.objectives`, read through the platform SLO
  API) *and* the classic `builtin:monitoring.slo` settings schema, and the alerts are
  `builtin:anomaly-detection.metric-events` *and* `builtin:davis.anomaly-detectors` — so
  `gather_sources(client)` returns seven `SourceResult`s across those five configuration types.
  Pass `include={...}` to restrict a scan; the default reads everything.
  `builtin:logmonitoring.log-events`, the third schema on the Settings app's *all alerts* page, is
  deliberately **not** a source: it holds a log-record matcher and event text, with no metric or
  entity selector for any topic to match.
- **Second-generation configurations are in scope.** Classic SLOs are reported, not skipped: nobody
  migrates them on the customer's behalf, so a Gen2 object reading a retired metric or entity is
  work the customer has to schedule.
- **Shared field allowlists.** `SHARED_SETTINGS_FIELDS` maps a source name to the fields that
  actually carry a metric or entity selector, and `is_shared_settings_field(source, path)` applies
  it. A topic detector delegates with one branch — `if source in SHARED_SETTINGS_FIELDS: return
  is_shared_settings_field(source, path)` — so adding a shared source later needs no scanner
  change and the rule cannot drift between topics.
- **Coverage state.** Every fetch returns a `SourceResult` carrying `complete` / `partial` /
  `failed`. Usage-gated reporting depends on this: an unreadable source must never be presentable
  as "no usage". dtctl 0.30.3 drops an SLO's `sliReference`, so template-based SLOs are counted as
  unread and degrade the source to `partial` instead of being scanned as empty.
- **Transports.** `DtctlClient` reuses the CLI's current context, so a scan needs no token or tenant
  URL. `HttpClient` takes a platform (`dt0s16.*`) token. Platform APIs use Bearer authentication;
  classic Environment/Configuration APIs use Api-Token authentication. Configuration API v1 rejects
  a platform token outright, so `HttpClient` sends `cfg.classic_token` (or `DT_CLASSIC_TOKEN`) when
  one is supplied and falls back to the platform token otherwise. Both transports request
  tenant-wide document access and report visible-only fallback as partial. Both expose the same
  surface: `dql`, `fetch_settings_source`, `fetch_documents`, `fetch_slos`.
- **Links.** `artifact_link(base_url, kind, artifact_id)` turns any fetched artifact into a URL
  that opens it in the tenant, built from the app intents the tenant itself registers. A
  settings object opens in the classic Settings app, except for the schemas that app has no
  page for - those are listed in `_SCHEMA_INTENTS` and open in the platform app that owns them:
  Davis custom alerts in Anomaly Detection, guardians in Site Reliability Guardian.

Capabilities only one transport can offer are exposed as optional methods, not on both clients —
`HttpClient.calculated_service_metrics_on_grail()` is the current example. Probe for one with
`getattr(client, "<name>", None)` and degrade the source when it is absent, the way
`calculated-service-metrics/scanner/src/calculated_service_metric_scanner/inventory.py` does; never assume the method is there.

The `cfg` object a client takes is duck-typed; it needs `timeout` and `max_workers`, plus
`dtctl_context` (dtctl) or `platform_url` / `classic_url` / `platform_token` (http).

```python
import sys; sys.path.insert(0, "<...>/shared-scripts")
from config_scan import DtctlClient, gather_sources, artifact_link, preflight

preflight(cfg.dtctl_context)
for source in gather_sources(DtctlClient(cfg)):
    print(source.name, source.state, source.items_checked)
    for item in source.items:
        ...  # item: source, kind, id, name, scope, body — apply your detector here
```

`calculated-service-metrics/scanner` consumes it through a single import seam,
`calculated_service_metric_scanner/shared.py`, which also honours `DT_UPGRADE_SHARED_SCRIPTS`;
copy that pattern rather than re-deriving the path in every module.

## Not here

The external-service scanner is **not** shared code. It lives with its own topic, in
`external-services/src/`. It predates this layer, carries its own
copy of the fetch code, and hardcodes a `SERVICE-*` substring detector. Do not import from it and
do not treat its `report.json` as a shared contract.
