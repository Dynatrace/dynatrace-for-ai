# `schemasClient`

Extension 2.0 schema versions and files. Import:

```ts
import { schemasClient } from "@dynatrace-sdk/client-extensions-v2";
```

| Method | Scope | Purpose |
|---|---|---|
| `listSchemaVersions()` | `extensions:definitions:read` | List all Extension 2.0 schema versions available in the environment. |
| `listSchemaVersionFiles({ schemaVersion, acceptType })` | `extensions:definitions:read` | List schema files for a version. `acceptType` is `'application/json; charset=utf-8'` (returns `SchemaFileList`) or `'application/octet-stream'` (returns `Binary`). |
| `getSchemaVersionFile({ schemaVersion, fileName })` | `extensions:definitions:read` | Retrieve one schema file's content. |

## Example

```ts
import { schemasClient } from "@dynatrace-sdk/client-extensions-v2";

const versions = await schemasClient.listSchemaVersions();
```
