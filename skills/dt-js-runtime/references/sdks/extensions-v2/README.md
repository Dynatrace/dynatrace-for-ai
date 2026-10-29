# Extensions 2.0 (`@dynatrace-sdk/client-extensions-v2`)

> Env: ✅ Server runtime
> Status: current

Extension 2.0 lifecycle -- install/upload/validate/delete versions, activate
or switch the version running in the environment, create and manage
monitoring configurations, and read JMX discovery data and configuration
schemas. This is the **platform** Extensions 2.0 API
(`/platform/extensions/v2/...`), distinct from the classic
`extensions_2_0Client` in [classic-environment-v2](../classic-environment-v2/extensions.md)
-- prefer this client for new code; see that file's note on when the classic
client is still the right choice.

## Clients & key methods

| Client | Methods | Purpose |
|---|---|---|
| `extensionsClient` | `listExtensions`, `installExtension`, `getActiveExtensionEnvironmentConfiguration`, `updateExtensionEnvironmentConfiguration`, `listExtensionMonitoringConfigurations`, `updateExtensionMonitoringConfiguration`, +17 more | Extension lifecycle, environment configuration (which version is active), monitoring configurations |
| `discoveryClient` | `listJmxProcesses`, `getJmxProcess` | JMX process discovery for metric collection -- both `maturity=EARLY_ADOPTER` |
| `schemasClient` | `listSchemaVersions`, `listSchemaVersionFiles`, `getSchemaVersionFile` | Extension 2.0 schema versions and files |

Full method/type detail: [extensionsClient.md](extensionsClient.md),
[discoveryClient.md](discoveryClient.md), [schemasClient.md](schemasClient.md)
(per-method returns, scopes, examples) · [types.md](types.md) (types + enums).

## Required scopes

- `extensions:definitions:read` / `extensions:definitions:write` -- installed
  versions, environment configuration (activation).
- `extensions:configurations:read` / `extensions:configurations:write` --
  monitoring configurations.
- `extensions:configuration.actions:write` -- executing data-source actions
  on ActiveGate/Host for a monitoring configuration.
- `extensions:discovery.jmx:read` -- JMX process discovery.

Most read/write pairs are independent -- e.g. reading monitoring
configurations does not require the definitions scope, and vice versa. Check
the per-method scope in [extensionsClient.md](extensionsClient.md) rather
than assuming one scope covers the whole client.

## Example

```ts
import { extensionsClient } from "@dynatrace-sdk/client-extensions-v2";

const page = await extensionsClient.listExtensions({ pageSize: 100, addFields: "activeVersion" });
```

## Notes

- `listExtensions` defaults to `pageSize: 20` (max 100) -- paginate via
  `nextPageKey` for tenants with more installed extensions than that; once
  `pageKey` is set, every other query parameter must be omitted.
- There is no `dtctl` command to activate a version in the environment --
  `dtctl create extension --hub-extension` only installs. Use
  `updateExtensionEnvironmentConfiguration` (a version has been active
  before) or `activateExtensionEnvironmentConfiguration` (no version has
  ever been active) for that step.
- `deleteExtensionEnvironmentConfiguration`'s name is misleading -- its own
  docstring says "Deactivates the environment configuration for Extension
  2.0," not delete-the-extension.

Canonical reference: https://developer.dynatrace.com/develop/sdks/client-extensions-v2/
