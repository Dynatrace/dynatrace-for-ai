# `extensions_2_0Client`

> For new code, prefer the platform client instead:
> [`@dynatrace-sdk/client-extensions-v2`](../extensions-v2/README.md). This
> classic client's own docstrings mark `updateExtensionEnvironmentConfiguration`
> and `activateExtensionEnvironmentConfiguration` (below) `@deprecated` --
> "Deprecated since version 1.342. Use the successor API
> `/platform/extensions/v2` instead" -- and most Extensions 2.0 scope
> declarations in this repo already assume the platform client's scopes
> (`extensions:definitions:read`), not this client's classic
> `environment-api:extensions:*` scopes.

Manage Extensions 2.0 — extension lifecycle, monitoring configurations, schemas. Import:

```ts
import { extensions_2_0Client } from "@dynatrace-sdk/client-classic-environment-v2";
```

## Extension lifecycle

| Method | Purpose |
|---|---|
| `listExtensions` / `listExtensionInfos` | List installed extensions / their info. |
| `listExtensionVersions` | List versions of an extension. |
| `extensionDetails` | Get details of an extension version. |
| `uploadExtension` | Upload an extension bundle. |
| `installExtension` | Install a previously uploaded extension version. |
| `removeExtension` | Remove an extension. |
| `getExtensionStatus` | Get extension status. |

## Monitoring configurations

| Method | Purpose |
|---|---|
| `extensionMonitoringConfigurations` | List monitoring configurations of an extension. |
| `createMonitoringConfiguration` | Create a monitoring configuration. |
| `monitoringConfigurationDetails` | Get a monitoring configuration. |
| `updateMonitoringConfiguration` | Update a monitoring configuration. |
| `removeMonitoringConfiguration` | Remove a monitoring configuration. |
| `getExtensionMonitoringConfigurationStatus` | Get configuration status. |
| `getExtensionMonitoringConfigurationEvents` | Get configuration events. |
| `monitoringConfigurationAudit` | Get configuration audit. |
| `executeExtensionMonitoringConfigurationActions` | Execute configuration actions. |

## Environment configuration & schemas

| Method | Purpose |
|---|---|
| `getActiveEnvironmentConfiguration` | Get active environment configuration. |
| `activateExtensionEnvironmentConfiguration` | Activate environment configuration. |
| `updateExtensionEnvironmentConfiguration` | Update environment configuration. |
| `deleteEnvironmentConfiguration` | Delete environment configuration. |
| `getEnvironmentConfigurationEvents` | Get environment configuration events. |
| `getEnvironmentConfigurationAssetsInfo` | Get environment configuration assets info. |
| `extensionConfigurationSchema` | Get configuration schema for an extension. |
| `getSchemaFile` / `listSchemaFiles` / `listSchemas` | Schema file/listing helpers. |
| `getActiveGateGroupsInfo` | ActiveGate groups info for extensions. |
| `getAlertTemplate` | Get an alert template. |
