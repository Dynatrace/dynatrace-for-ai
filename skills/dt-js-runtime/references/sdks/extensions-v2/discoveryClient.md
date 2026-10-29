# `discoveryClient`

JMX process discovery for metric collection. Both methods are
`maturity=EARLY_ADOPTER`. Import:

```ts
import { discoveryClient } from "@dynatrace-sdk/client-extensions-v2";
```

| Method | Scope | Purpose |
|---|---|---|
| `listJmxProcesses({ filter? })` | `extensions:discovery.jmx:read` | List Java processes discovered in the environment for JMX metric collection. `filter` supports `hostId` (e.g. `hostId = 'HOST-1234ABCD5678EFAB'`); omit to return all processes. |
| `getJmxProcess({ processId })` | `extensions:discovery.jmx:read` | Details of one discovered Java process by ID. |

## Example

```ts
import { discoveryClient } from "@dynatrace-sdk/client-extensions-v2";

const processes = await discoveryClient.listJmxProcesses({ filter: "hostId = 'HOST-1234ABCD5678EFAB'" });
```
