# `extensionsClient`

Extension 2.0 lifecycle, environment configuration, and monitoring
configurations. Import:

```ts
import { extensionsClient } from "@dynatrace-sdk/client-extensions-v2";
```

## Extension lifecycle

| Method | Scope | Purpose |
|---|---|---|
| `listExtensions` | `extensions:definitions:read` | List installed extensions. Paginated -- default `pageSize` 20, max 100; use `addFields: 'activeVersion'` to include the version active in the environment alongside the highest installed one. |
| `listExtensionVersions` | `extensions:definitions:read` | List versions of one extension. |
| `getExtensionDetails` | `extensions:definitions:read` | Details of a specified version. |
| `uploadExtension` | `extensions:definitions:write` | Upload a new extension version (not from Hub). |
| `installExtension` | `extensions:definitions:write` | Install a version from Hub. Returns 202 Accepted -- installation completes asynchronously; poll `listExtensionVersions` for the version to appear before activating it. |
| `validateExtension` | `extensions:definitions:write` | Dry-run of upload -- same validation, no persisted change. |
| `deleteExtensionVersion` | `extensions:definitions:write` | Delete a specified version. |

## Environment configuration (which version is active)

There is no `dtctl` equivalent for any of these -- `dtctl create extension`
only installs, it does not set the active version.

| Method | Scope | Purpose |
|---|---|---|
| `getActiveExtensionEnvironmentConfiguration` | `extensions:definitions:read` | Get the version currently active in the environment. Throws/errors if none is active yet -- verified live: this is an `ErrorEnvelopeError` with `response.status === 404` (same status for a genuinely nonexistent extension name; a malformed request, e.g. an empty `extensionName`, instead surfaces as a 400 `ApiGatewayError`). Narrow on `response.status === 404` specifically -- don't treat every error here as "no active version", or a 403/5xx/network failure gets silently reinterpreted as one. |
| `updateExtensionEnvironmentConfiguration` | `extensions:definitions:write` | Switch the active version -- use when a version is already active. |
| `activateExtensionEnvironmentConfiguration` | `extensions:definitions:write` | Activate a version for the first time -- use when no version has ever been active for this extension (e.g. right after a first-time Hub install). |
| `deleteExtensionEnvironmentConfiguration` | `extensions:definitions:write` | **Despite the name, this deactivates** the environment configuration; it does not delete the extension. |
| `getAlertTemplate` | `extensions:definitions:read` | Get the alert template for an asset of the active environment configuration. |
| `getActiveGateGroups` | `extensions:configurations:read` | List ActiveGate groups available for a version. |
| `getExtensionConfigurationSchema` | `extensions:definitions:read` **or** `extensions:configurations:read` | Get the monitoring-configuration schema for a version -- either scope suffices. |

## Monitoring configurations

| Method | Scope | Purpose |
|---|---|---|
| `listExtensionMonitoringConfigurations` | `extensions:configurations:read` | List monitoring configurations for an extension. Paginated -- default `pageSize` 20, max 500. Filterable by `version`, `active`/`enabled`, `description`, `activationContext` (exact filter-string syntax not verified against a live tenant -- filter client-side on the returned `value` object if unsure). |
| `getExtensionMonitoringConfigurationDetails` | `extensions:configurations:read` | Get one monitoring configuration by ID. |
| `getExtensionMonitoringConfigurationStatus` | `extensions:configurations:read` | Most recent execution status of one configuration. |
| `getExtensionMonitoringConfigurationStatuses` | `extensions:configurations:read` | Most recent execution statuses of all configurations for an extension. |
| `getExtensionMonitoringConfigurationAudit` | `extensions:configurations:read` | Audit log for a configuration. |
| `createExtensionMonitoringConfiguration` | `extensions:configurations:write` | Create a new monitoring configuration. |
| `updateExtensionMonitoringConfiguration` | `extensions:configurations:write` | Update an existing configuration -- e.g. to migrate it to a new extension version once that version is active. |
| `deleteExtensionMonitoringConfiguration` | `extensions:configurations:write` | Delete a configuration. |
| `executeExtensionMonitoringConfigurationActions` | `extensions:configuration.actions:write` | Execute data-source actions on ActiveGate or Host for a configuration. |

## Example: install, activate, migrate configs (the upgrade sequence)

```ts
import { extensionsClient } from "@dynatrace-sdk/client-extensions-v2";

// 1. Install -- async; poll listExtensionVersions before proceeding.
await extensionsClient.installExtension({ extensionName, version });

// 2. Activate -- update if a version was already active, activate if not.
// Narrow the "not active yet" case to its documented shape (404) instead of
// catching everything -- an auth failure or transient error caught here would
// silently route to activateExtensionEnvironmentConfiguration instead of
// surfacing the real problem.
let hadActiveVersion: boolean;
try {
  await extensionsClient.getActiveExtensionEnvironmentConfiguration({ extensionName });
  hadActiveVersion = true;
} catch (e) {
  if ((e as { response?: { status?: unknown } })?.response?.status !== 404) throw e;
  hadActiveVersion = false;
}

await (hadActiveVersion
  ? extensionsClient.updateExtensionEnvironmentConfiguration({ extensionName, body: { version } })
  : extensionsClient.activateExtensionEnvironmentConfiguration({ extensionName, body: { version } }));

// 3. Migrate monitoring configs still pinned to the old version.
const configs = await extensionsClient.listExtensionMonitoringConfigurations({ extensionName, pageSize: 500 });
for (const config of configs.items) {
  if (config.value.version === oldVersion) {
    await extensionsClient.updateExtensionMonitoringConfiguration({
      extensionName,
      configurationId: config.objectId,
      body: { value: { ...config.value, version } },
    });
  }
}
```

This is the same sequence `dt-upgrade`'s `upgrade-ef2-extension.ts` runs --
install and activate (phases 1-2) behind a dry-run-by-default gate, and
config migration (phase 3) behind a second, separate consent flag
(`migrateConfigsConsent`).
