# `extensionsClient`

Browse Hub extensions. All methods require scope `hub:catalog:read`. Import:

```ts
import { extensionsClient } from "@dynatrace-sdk/client-hub";
```

| Method | Returns | Purpose |
|---|---|---|
| `getExtensionOverviewList({ onlyCompatible?, addFields? })` | `OverviewsList` | List overview info of **all** extensions -- no pagination, no server-side filter. Each `Overview` carries `id`, `name`, `description`, and `keywords[]`; matching by technology/keyword is client-side over the full list. `onlyCompatible` (default `true`) restricts to versions compatible with this tenant -- set `false` to also see incompatible Hub extensions, which is often exactly what an upgrade-readiness check needs to find. |
| `getExtensionDetails({ id })` | `Detail` | Detailed information about one extension. `Detail extends Overview` and adds `relatedItems: Overview[]` -- neighbors worth checking once you have one close match. |
| `getExtensionReleases({ id })` | `ReleasesList` | List releases published for an extension (including revoked releases). |

## Example

```ts
import { extensionsClient } from "@dynatrace-sdk/client-hub";

const detail = await extensionsClient.getExtensionDetails({ id: "..." });
```
