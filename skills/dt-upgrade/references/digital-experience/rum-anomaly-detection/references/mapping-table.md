# Alerts: Classic to 3rd gen mapping table

- [Frontend level — Anomaly detection alerts](#frontend-level--anomaly-detection-alerts)
- [Frontend level — Crash rate increase](#frontend-level--crash-rate-increase)
- [Environment level](#environment-level)
- [Response time alerts](#response-time-alerts)
- [Metrics used in performance alerts baselining](#metrics-used-in-performance-alerts-baselining)
- [Field mapping details](#field-mapping-details)

## Frontend level — Anomaly detection alerts

| Classic alert | 2nd gen config options | alertKey (3rd gen) | 3rd gen translation | Schema |
|---|---|---|---|---|
| Response time alerts - user action response time + slowest 10% | Auto or Fixed, per KPM | health alert (when able) / custom alert | Health alert if KPM available in 3rd gen; custom alert via `dt.frontend.*` otherwise. "All actions" and "slowest 10%" collapse into a single alert — 3rd gen has no slowest-10% equivalent. See response time section below. | `builtin:anomaly-detection.rum-web` |
| JS error rate | Auto (abs + rel) or Fixed + sensitivity | `errorRateExceptions` | auto → SeasonalBaseline defaults; fixed → StaticThreshold with user value | `builtin:anomaly-detection.rum-web` |
| Traffic drops | % below expected + minutes in abnormal state | `trafficDrop` | always SeasonalBaseline defaults (no auto/static choice in 2nd gen) | `builtin:anomaly-detection.rum-web` |
| Traffic spikes | % above expected + minutes in abnormal state | `trafficSpike` | always SeasonalBaseline defaults (no auto/static choice in 2nd gen) | `builtin:anomaly-detection.rum-web` |
| Error rate increase | Auto (abs + rel) or Fixed + sensitivity | `errorRateExceptions` | auto → SeasonalBaseline defaults; fixed → StaticThreshold with user value | `builtin:anomaly-detection.rum-mobile` |
| Slow user actions | Auto or Fixed + sensitivity | `userActionDuration` | auto → AutoAdaptive defaults; fixed → StaticThreshold with user value | `builtin:anomaly-detection.rum-mobile` |
| Low load | % below expected | `trafficDrop` | always SeasonalBaseline defaults (Default analyzer, same as web traffic drops) | `builtin:anomaly-detection.rum-mobile` |
| High load | % above expected | `trafficSpike` | always SeasonalBaseline defaults (Default analyzer, same as web traffic spikes) | `builtin:anomaly-detection.rum-mobile` |

## Frontend level — Crash rate increase

| Classic alert | 2nd gen config options | alertKey (3rd gen) | 3rd gen translation | Schema |
|---|---|---|---|---|
| Crash rate increase - mobile | Auto or Fixed | `mobileCrash` | auto → SeasonalBaseline defaults; fixed → StaticThreshold with user value | `builtin:anomaly-detection.rum-mobile-crash-rate-increase` |

## Environment level

No health alerting on environment level in 3rd gen. Must create a 1:N relationship:
one settings object per application per alert type, using the same translation rules above.

Priority order (as in 2nd gen). Each alert type resolves independently, so one app can draw
different alert types from different tiers:

1. App-specific settings object, if one exists → `explicit`
2. Otherwise the environment-level object → `environment-fallback`
3. Otherwise the schema's own defaults → `schema-default`

All three tiers produce objects. Tier 3 is not "no upgrade needed" — an app with no explicit
and no environment object still runs on the schema defaults in 2nd gen, so it needs an
equivalent 3rd gen object. Schema defaults are read from the live schema definitions at
runtime, never hardcoded.

`responseTime` resolves along two axes, because KPMs are configured per application and never
on environment scope. For an app on tier 2 or 3 the alert config (enabled, detection mode,
thresholds) comes from the environment object or schema defaults, while the KPM is still read
from that app's own KPM object — falling back to the schema default `VISUALLY_COMPLETE` when
it has none. This is the same resolution an app on tier 1 gets, so response time behaves
identically on every tier.

## Response time alerts

The `responseTime` field in `rum-web` covers both "All user actions" and "Slowest 10%".
Translation logic:

1. Read the 2nd gen config — check which KPM is configured for **load actions** and **XHR actions**.
   An app with no KPM settings object of its own runs on the schema default, `VISUALLY_COMPLETE`,
   which has no 3rd gen metric — so those apps produce a skipped response time row.
2. Are both KPMs the same?
   - **Yes** → create a single alert (the 2nd gen "all actions" + "slowest 10%" split has no 3rd gen equivalent).
   - **No** → create two alerts (one per KPM).
3. Is the KPM available in 3rd gen as a health alert?
   - **Yes** → use the corresponding `alertKey` (`userActionDuration`, `webVitalsLcp`, `webVitalsCls`).
   - **No, but a `dt.frontend.*` metric exists** → create a `builtin:davis.anomaly-detectors` custom alert using `percentile(metric, 75)` filtered by `dt.smartscape_source.id`. Note: classic measured either all actions (an average) or the slowest 10% (roughly p90) — never p75. p75 was chosen for consistency with how 3rd gen health alerts already baseline, not as a like-for-like match to either classic measurement.
   - **No metric available** → skip (`LOAD_EVENT_START`, `SPEED_INDEX`, `VISUALLY_COMPLETE`).

Detection mode: auto → AutoAdaptive (health) or auto-adaptive analyzer (custom); fixed → StaticThreshold with `degradationMilliseconds` as threshold.

### Auto-adaptive sensitivity

`numberOfSignalFluctuations` is set to **1** for both health and custom alerts, from
`AUTO_ADAPTIVE_DEFAULTS` in `migrator/translate.py`.

1 is `builtin:health-experience.frontend-alert`'s declared schema default for
`AutoAdaptiveAnalyzerInput`, and also the minimum of its `1–10` range, so it is the most
sensitive end. **That default applies to health alerts only.**

Custom alerts use a different schema, `builtin:davis.anomaly-detectors`, whose analyzer input
is a generic `{key, value}` list — there is no field named `numberOfSignalFluctuations` in that
schema at all, so there is no schema default for custom alerts to point to. Before this was sent
explicitly, custom alerts omitted the field entirely, and the UI still showed `1` — that was the
Davis `AutoAdaptiveAnomalyDetectionAnalyzer`'s own undocumented runtime default, not a value
declared anywhere we can verify. It happened to match the health-alert schema default, which is
what made this easy to overlook.

Custom alerts now send `1` **explicitly**, from the same `AUTO_ADAPTIVE_DEFAULTS` constant, so
both paths use the same value on purpose rather than by coincidence of two unrelated defaults.

Whether `1` — maximum sensitivity — is actually the right choice for alerts upgraded in bulk
with no per-app review is an open question, not a settled one. It is kept at this value on the
grounds that an upgrade should reproduce default behaviour rather than invent a tolerance the
user never chose, but there is no confirmed recommendation from the alerting/Davis side on
what value suits upgraded alerts specifically. If one is obtained, or if this proves too noisy
in practice, changing `AUTO_ADAPTIVE_DEFAULTS["numberOfSignalFluctuations"]` in
`migrator/translate.py` is the only place that needs to change.

## Metrics used in performance alerts baselining

### Web — Load action KPIs

Keyed by the `LoadKpm` enum value, not the UI label — the script matches on the enum value.
This table must stay in sync with `KPM_TO_HEALTH_ALERT_KEY` and `KPM_TO_CUSTOM_ALERT_METRIC`
in `migrator/translate.py`.

| `LoadKpm` value | UI label | 3rd gen |
|---|---|---|
| `CUMULATIVE_LAYOUT_SHIFT` | Cumulative layout shift | health alert → `webVitalsCls` |
| `DOM_INTERACTIVE` | DOM interactive | custom alert → `dt.frontend.web.navigation.dom_interactive` |
| `FIRST_INPUT_DELAY` | First input delay | custom alert → `dt.frontend.web.page.first_input_delay` |
| `LARGEST_CONTENTFUL_PAINT` | Largest contentful paint | health alert → `webVitalsLcp` |
| `LOAD_EVENT_END` | Load event end | custom alert → `dt.frontend.web.navigation.load_event_end` |
| `LOAD_EVENT_START` | Load event start | not available |
| `RESPONSE_END` | Response end | not available |
| `RESPONSE_START` | Time to first byte | custom alert → `dt.frontend.web.navigation.time_to_first_byte` |
| `SPEED_INDEX` | Speed index | not available |
| `USER_ACTION_DURATION` | User action duration | health alert → `userActionDuration` |
| `VISUALLY_COMPLETE` | Visually complete | not available |

There is no `TIME_TO_FIRST_BYTE` enum value — "Time to first byte" in the UI is
`RESPONSE_START`. There is no `HTML_DOWNLOADED` value either, despite the wiki listing one.

`RESPONSE_END` is **not** a TTFB synonym: it measures when the response completed, not when
the first byte arrived. No 3rd gen metric covers it, so it is skipped.

### Web — XHR action KPIs

| `XhrKpm` value | UI label | 3rd gen |
|---|---|---|
| `RESPONSE_END` | Response end | not available |
| `RESPONSE_START` | Time to first byte | custom alert → `dt.frontend.web.navigation.time_to_first_byte` |
| `USER_ACTION_DURATION` | User action duration | health alert → `userActionDuration` |
| `VISUALLY_COMPLETE` | Visually complete | not available |

## Field mapping details

### rum-web.errorRate → errorRateExceptions

| Source field | Target field |
|---|---|
| `errorRate.enabled` | `value.enabled` |
| `errorRateDetectionMode: "auto"` | `analyzerType: "SeasonalBaseline"` + defaults |
| `errorRateDetectionMode: "fixed"` | `analyzerType: "StaticThreshold"` |
| `errorRateFixed.maxFailureRateIncrease` | `staticThresholdAnalyzerInput.threshold` |

### rum-web.trafficDrops → trafficDrop

| Source field | Target field |
|---|---|
| `trafficDrops.enabled` | `value.enabled` |
| always | `analyzerType: "SeasonalBaseline"` + defaults (no analyzer choice in 2nd gen) |

### rum-web.trafficSpikes → trafficSpike

| Source field | Target field |
|---|---|
| `trafficSpikes.enabled` | `value.enabled` |
| always | `analyzerType: "SeasonalBaseline"` + defaults (no analyzer choice in 2nd gen) |

### rum-mobile.errorRateIncrease → errorRateExceptions

| Source field | Target field |
|---|---|
| `errorRateIncrease.enabled` | `value.enabled` |
| `detectionMode: "auto"` | `analyzerType: "SeasonalBaseline"` + defaults |
| `detectionMode: "fixed"` | `analyzerType: "StaticThreshold"` |
| `errorRateIncreaseFixed.thresholdAbsolute` | `staticThresholdAnalyzerInput.threshold` |

### rum-mobile.slowUserActions → userActionDuration

| Source field | Target field |
|---|---|
| `slowUserActions.enabled` | `value.enabled` |
| `detectionMode: "auto"` | `analyzerType: "AutoAdaptive"` + defaults |
| `detectionMode: "fixed"` | `analyzerType: "StaticThreshold"` |
| `slowUserActionsFixed.durationThresholdAllFixed.durationThreshold` | `staticThresholdAnalyzerInput.threshold` |

### rum-mobile.unexpectedLowLoad → trafficDrop

| Source field | Target field |
|---|---|
| `unexpectedLowLoad.enabled` | `value.enabled` |
| always | `analyzerType: "SeasonalBaseline"` + defaults |

### rum-mobile.unexpectedHighLoad → trafficSpike

| Source field | Target field |
|---|---|
| `unexpectedHighLoad.enabled` | `value.enabled` |
| always | `analyzerType: "SeasonalBaseline"` + defaults |
