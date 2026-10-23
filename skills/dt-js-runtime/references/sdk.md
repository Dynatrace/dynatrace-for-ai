# Dynatrace SDK for TypeScript — Index

The `@dynatrace-sdk/*` packages expose Dynatrace platform services to runtime code. Two layers:

- **Generic / utility** packages — convenience helpers (e.g. `units` for formatting, `app-environment` for app/user context).
- **Low-level `client-*`** packages — direct, scope-gated access to individual platform services.

**Rules of thumb**
- The app/function must **declare the OAuth scopes** for every service it touches (each SDK file lists them).
- **Error handling:** wrap calls in `try/catch`, treat the error as `unknown`, narrow with type guards, handle only what you can act on, and rethrow the rest so monitoring detects it.
- Prefer a typed client over a hand-rolled relative `fetch` (see [fetch.md](fetch.md)).

## Catalog

Load the per-SDK file for methods, scopes, and examples.

| SDK file | npm package | Purpose | Env | Status |
|---|---|---|---|---|
| [query](sdks/query/README.md) | `@dynatrace-sdk/client-query` | Run DQL against Grail (execute + poll) | ✅ server | current |
| [classic-environment-v1](sdks/classic-environment-v1/README.md) | `@dynatrace-sdk/client-classic-environment-v1` | Classic Env API v1 — installers, synthetic, RUM JS, USQL | ✅ server | current |
| [classic-environment-v2](sdks/classic-environment-v2/README.md) | `@dynatrace-sdk/client-classic-environment-v2` | Classic Env API v2 — settings, tokens, events, **credential vault**, audit | ✅ server | current |
| [document](sdks/document/README.md) | `@dynatrace-sdk/client-document` | Create/share/lock documents (dashboards, notebooks) | ✅ server | current |
| [state](sdks/state/README.md) | `@dynatrace-sdk/client-state` | Key-value app/user state with TTL | ✅ server | current |
| [automation](sdks/automation/README.md) | `@dynatrace-sdk/client-automation` | Workflows, executions, schedules, triggers, calendars | ✅ server | current |
| [automation-utils](sdks/automation-utils/README.md) | `@dynatrace-sdk/automation-utils` | Helpers inside workflow Run JavaScript actions | ✅ server | current |
| [app-environment](sdks/app-environment/README.md) | `@dynatrace-sdk/app-environment` | App id/name/version, current user, environment id/url | ✅ server | current |
| [app-utils](sdks/app-utils/README.md) | `@dynatrace-sdk/app-utils` | Call named app functions (`functions.call`) | ✅ server | current |
| [app-settings-v2](sdks/app-settings-v2/README.md) | `@dynatrace-sdk/client-app-settings-v2` | App settings objects CRUD + permissions | ✅ server | current |
| [app-settings-v1](sdks/app-settings-v1/README.md) | `@dynatrace-sdk/client-app-settings` | App settings (v1) | ✅ server | ⚠ deprecated → v2 |
| [bucket-management](sdks/bucket-management/README.md) | `@dynatrace-sdk/client-bucket-management` | Grail storage buckets (retention) | ✅ server | current |
| [resource-store](sdks/resource-store/README.md) | `@dynatrace-sdk/client-resource-store` | Grail lookup data files (DPL parsing) | ✅ server | current |
| [filter-segments](sdks/filter-segments/README.md) | `@dynatrace-sdk/client-filter-segment-management` | Grail filter-segments | ✅ server | current |
| [davis-analyzers](sdks/davis-analyzers/README.md) | `@dynatrace-sdk/client-davis-analyzers` | Davis AI predictive/causal analyzers | ✅ server | current |
| [notification-v2](sdks/notification-v2/README.md) | `@dynatrace-sdk/client-notification-v2` | Event & resource notifications | ✅ server | current |
| [notification-v1](sdks/notification-v1/README.md) | `@dynatrace-sdk/client-notification` | Self-notifications (v1) | ✅ server | ⚠ deprecated → v2 |
| [iam](sdks/iam/README.md) | `@dynatrace-sdk/client-iam` | Query users, groups, service users | ✅ server | current |
| [app-engine-registry](sdks/app-engine-registry/README.md) | `@dynatrace-sdk/client-app-engine-registry` | Install / list / uninstall apps | ✅ server | current |
| [edge-connect](sdks/edge-connect/README.md) | `@dynatrace-sdk/client-app-engine-edge-connect` | EdgeConnect configs for private-network forwarding | ✅ server | current |
| [hub](sdks/hub/README.md) | `@dynatrace-sdk/client-hub` | Hub catalog — apps, extensions, technologies | ✅ server | current |
| [extensions-v2](sdks/extensions-v2/README.md) | `@dynatrace-sdk/client-extensions-v2` | Extensions 2.0 — lifecycle, environment configuration, monitoring configs, schemas (platform API) | ✅ server | current |
| [platform-management](sdks/platform-management/README.md) | `@dynatrace-sdk/client-platform-management-service` | Env info, license, effective permissions | ✅ server | current |
| [units](sdks/units/README.md) | `@dynatrace-sdk/units` | Convert/format units, numbers, dates | ✅ server | current |
| [navigation](sdks/navigation/README.md) | `@dynatrace-sdk/navigation` | App navigation & intents — **browser-only, not available in server runtime** | ⚠️ browser | current |
| [react-hooks](sdks/react-hooks/README.md) | `@dynatrace-sdk/react-hooks` | React hooks (`useDql`, …) — **browser-only, not available in server runtime** | ⚠️ browser | current |
| [user-preferences](sdks/user-preferences/README.md) | `@dynatrace-sdk/user-preferences` | Logged-in user theme/language/timezone — **browser-only, not available in server runtime** | ⚠️ browser | current |

Full SDK reference: https://developer.dynatrace.com/develop/sdks/
