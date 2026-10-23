# Extensions 2.0 -- Types & Enums

Full field definitions: https://developer.dynatrace.com/develop/sdks/client-extensions-v2/#types

## Extension lifecycle types

`Extension`, `ExtensionInfo` (id, `activeVersion`, `version` = highest
installed, `keywords`, `markedForDeletion`), `ExtensionInfoList` (`items:
ExtensionInfo[]`, paginated via `nextPageKey`/`totalCount`), `ExtensionList`
(`items: MinimalExtension[]`), `MinimalExtension`, `ExtensionStatus`,
`ExtensionStatusWithId`, `ExtensionStatusWithIdList`, `ExtensionUploadResponse`,
`RegisteredExtensionResult` (`extensionName`, `extensionVersion` -- returned
202 Accepted from `installExtension`), `AssetInfo`, `AssetSchemaDetails`,
`AuditLog`, `AuditLogEntry`, `ModificationInfo`.

## Environment configuration types

`EnvironmentConfiguration` (`assets`, `errors`, `status: "PENDING" |
"UP_TO_DATE"`, `version`), `ExtensionEnvironmentConfigurationVersion` (just
`{ version: string }` -- the body for both `updateExtensionEnvironmentConfiguration`
and `activateExtensionEnvironmentConfiguration`), `ActiveGateGroupInfo`,
`ActiveGateGroupInfoList`, `ActiveGateInfo`, `AlertTemplate`.

## Monitoring configuration types

`MonitoringConfiguration` (`scope`, `value`), `MonitoringConfigurationUpdate`
(`value?: JsonNode`), `MonitoringConfigurationResponse` (`code`, `objectId`),
`ExtensionMonitoringConfiguration` (`objectId`, `scope`, `value`,
`modificationInfo`), `ExtensionMonitoringConfigurationList` (`items`,
paginated), `ExtensionMonitoringConfigurationValue` (alias for
`Record<string, any>` -- the version a config targets lives at
`value.version`, verified live), `ExecuteActions`,
`ExecuteActionsActions`, `ExecuteActionsResponse`.

## Schema types

`SchemaVersionList`, `SchemaFileList`, `SchemaDefinitionRestDto` and its
`Enums`/`Metadata`/`Properties`/`TableColumns`/`Types` sub-shapes,
`SchemaConstraintRestDto`, `SchemaType`, `SchemaTypeProperties`, `TableColumn`,
`PropertyDefinitionMetadata`, `FeatureSetDetails`,
`ExtensionFeatureSetsDetails`, `ExtensionUploadResponseFeatureSetsDetails`,
`DatasourceDefinition`, `Metric`, `MetricMetadata`, `Item`, `ItemMetadata`,
`RefPointer`, `EnumType`, `EnumValue`, `Constraint`, `ComplexConstraint`,
`ConstraintViolation`, `DeletionConstraint`, `Precondition`, `AnyValue`,
`JsonNode`.

## UI customization types

`UiCustomization`, `UiButtonCustomization`, `UiCallbackCustomization`,
`UiEmptyStateCustomization`, `UiExpandableCustomization`,
`UiExpandableSectionCustomization`, `UiTabGroupCustomization`,
`UiTabsCustomization`, `UiTableCustomization`, `UiTableColumnCustomization`,
`UiTableColumnItemCustomization`.

## JMX discovery types

`JavaProcessDetails`, `JavaProcessContainer`, `JavaProcessContainerList`,
`JavaProcessContainerProperties`.

## Error types

`ErrorDetails`, `ErrorEnvelope`.

## Other

`Author`, `UploadResponseAssetInfo`.
