---
name: dt-js-runtime
description: Dynatrace server-side JS runtime — function contract, runtime limits, Web APIs, Node.js modules, fetch with credential vault, and the @dynatrace-sdk/* catalog.
license: Apache-2.0
---

# Dynatrace JavaScript Runtime

The Dynatrace JS runtime is a server-side AppEngine sandbox that executes JavaScript/TypeScript.

## Function contract

Every entry point must export a default async function:

```js
export default async function () {
  // ...
  return result;
}
```

ES module syntax required. TypeScript accepted (type annotations, interfaces, generics). No other export shape is supported.

## References

Start here, then load only the file you need.

| File | When to load |
|------|-------------|
| [references/limits-and-restrictions.md](references/limits-and-restrictions.md) | Timeout / memory / I/O quotas; what's forbidden (`eval`, WebSocket, sockets, filesystem) |
| [references/apis-and-modules.md](references/apis-and-modules.md) | Which Web APIs and Node.js compat modules are available (fetch, crypto, streams, buffer, …) |
| [references/fetch.md](references/fetch.md) | Calling internal `/platform/...` APIs or external URLs, credential vault, outbound allowlist |
| [references/sdk.md](references/sdk.md) | Any `@dynatrace-sdk/*` package — the index routes you to the right per-SDK file |

## Running a function with dtctl

Use `dtctl exec function` to run JS runtime code without deploying an app.

```dtctl
# Run inline code
dtctl exec function --code 'export default async function() { return "hello" }'

# Run from file
dtctl exec function -f script.js

# Pass JSON input — the parsed object is the function's argument
dtctl exec function -f script.js --payload '{"key":"value"}'
```

The function may accept an optional parameter. `--payload` is parsed and passed
as that argument directly — it is not wrapped in an `event.payload` field:

```js
export default async function(payload) {
  // with --payload '{"key":"value"}', payload is {"key": "value"}
  return payload.key;
}
```

Load the **`dynatrace-control`** skill for authentication setup, context switching, and the full `exec function` reference.
