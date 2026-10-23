# Hub — Types & Enums

Full field definitions: https://developer.dynatrace.com/develop/sdks/client-hub/#types

## Overview / detail / release types

`Overview` (`id`, `name`, `description`, `keywords[]`, `type` -- e.g.
`'EXTENSION_2'` -- plus `version`, `author`, `links`), `OverviewsList`
(`{ items: Overview[] }`), `Detail` (extends `Overview`, adds
`detailSections` and `relatedItems: Overview[]` for finding neighbors of a
match), `DetailSection`, `MarkdownSection`, `GallerySection`, `GalleryImage`, `GalleryImageResolutions`, `Release`, `ReleasesList`, `Manifest`, `ManifestScope`, `ExtensionMetadata`, `Link`, `Author`, `Dependency`, `AssetCount`, `ContentCount`, `DocumentCount`, `DocumentCountTypes`, `Revocation`, `ResourceContext`.

## Category types

`Categories`, `Category`, `CategoryPage`, `CategoryPageContent`, `CategoryPageContentBlock`.

## Error types

`Error`, `ErrorDetails`, `ErrorEnvelope`, `ConstraintViolation`.

## Enums

`CategoryPageContentContentType`, `Compatibility`, `ItemType`, `LinkType`, `RevocationReason`, `RevocationSeverity`, `ResourceContextOperationsItem`, and the optional-field enums (`OptionalAppDetailField`, `OptionalAppOverviewField`, `OptionalAppReleaseField`, `OptionalExtensionDetailField`, `OptionalExtensionReleaseField`, `OptionalOverviewField`, `OptionalTechnologyDetailField`).
