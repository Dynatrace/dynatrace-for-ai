# Metric Transpiler

**Shared utility** — used by multiple upgrade references (e.g.
dashboards, alerting) that need to convert
classic **2nd-gen (2G) metric selectors** to Grail **DQL**.

The Metric Transpiler converts a 2G metric selector — including one with
arithmetic across multiple metrics — into a single DQL query. Feed the **whole
expression** in one call; the transpiler assembles cross-metric arithmetic
(ratios, constants) itself and returns one complete DQL. Do not split an
expression into per-metric parts unless a whole expression fails to transpile.

Call the service through the bundled [`scripts/transpile.ts`](scripts/transpile.ts)
script — never with raw `curl` and never by pasting a token on the command line.
The script encapsulates the HTTP call, reads the credential from a `.dtmigration`
file itself, and prints a normalized JSON result. `dtctl` **cannot** proxy this
endpoint.

The `.dtmigration` file is a **hard requirement**. If the script reports it is
missing, **stop and ask the user to create it** (see the token steps below).
Never work around a missing file by sourcing a token from `dtctl`, the OS
keychain, or environment variables — the token must come from `.dtmigration`.

## Prerequisites

- **Grail onboarding** — the tenant must be onboarded to Grail
  (`isExistsInPlatform = true`). On a non-Grail Managed tenant the call succeeds
  structurally but every metric fails the Grail-presence check.
- **Node.js 22+** — the script runs with native TypeScript type-stripping and
  uses `fetch` and `node:util` `parseArgs`; no build step or dependencies.
  Invoke it as `node --experimental-strip-types scripts/transpile.ts …` (on
  Node 23.6+ the flag is optional).
- **A `.dtmigration` credential file** in the working directory (copy
  [.dtmigration.example](.dtmigration.example)). This file is **required**; the
  script parses it itself — **do not read `.dtmigration` yourself.** It defines
  a single variable, `DT_TRANSPILE_TOKEN` — an API token sent as
  `Authorization: Api-Token <token>` with scope `metrics:read`.

  If the file (or `DT_TRANSPILE_TOKEN`) is missing, **stop and ask the user** to
  create it. Tell them how to get the token: in Dynatrace, go to **Personal
  access tokens > Create token** and create a token with the **`metrics:read`**
  scope, then put it in `.dtmigration`. Do not fetch a token from anywhere else.

  The transpiler lives on the **Classic Environment API v2** (`/api/v2/`), not
  the Platform API.

- **A current `dtctl` context.** The script resolves the target environment from
  `dtctl config current-context` and then reads that context via
  `dtctl config view --context=<name> -o json`, so the environment is never
  stored in `.dtmigration`. dtctl stores the **platform** URL, but the
  transpiler is on the **classic** Environment API, so the script converts the
  host automatically (`<env>.apps.dynatrace.com` → `<env>.live.dynatrace.com`;
  `<env>.<stage>.apps.dynatracelabs.com` → `<env>.<stage>.dynatracelabs.com`;
  Managed/custom hosts are used unchanged). Ensure the right context is
  selected (`dtctl config use-context <name>` to switch) before running. For an
  unusual deployment where that conversion doesn't apply, set
  `DT_TRANSPILE_ENV_URL` in `.dtmigration` to the classic URL to override it.

## Endpoints

Both endpoints are **hidden** (`hidden = true`) — not shown in the OpenAPI spec
or the API explorer. Base path is `/api/v2/metrics`.

| Method & path                        | Purpose                                          | Script subcommand |
| ------------------------------------ | ------------------------------------------------ | ----------------- |
| `GET /api/v2/metrics/transpile`      | One selector/expression                          | `single`          |
| `POST /api/v2/metrics/transpileBulk` | Many selectors, one call (preferred for batches) | `bulk`            |

> The bulk path is `/api/v2/metrics/transpileBulk` — a sibling of `/transpile`,
> **not** `/transpile/transpileBulk`.

## Request parameters

The `single` (GET) endpoint takes query parameters. The `bulk` (POST) endpoint
takes the selectors in a JSON body plus a subset of the query parameters.

| Parameter                              |      single      |      bulk       | Default           | Notes                                                                                                                                                                                                                                                   |
| -------------------------------------- | :--------------: | :-------------: | ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `metricSelector` / `metricSelectors[]` | query (required) | body (required) | —                 | The full 2G selector/expression. Bulk body: `{ "metricSelectors": ["…","…"] }`                                                                                                                                                                          |
| `resolution`                           |        ✅        |       ✅        | `120` points      | Timestep (`1m`, `5m`, `1h`, `1w`, `4M`, `3y`), a unit-less point count ≥ 2 (`120`, `500`), or `Inf` for a single aggregated point. **`auto` is rejected with `400`** — it is not a valid resolution (unlike `scalarFunction`). Omit to use the default. |
| `from` / `to`                          |        ✅        |       ✅        | `now-2h` .. `now` | ISO-8601 or relative (`now-2h`).                                                                                                                                                                                                                        |
| `mode`                                 |        ✅        |       ✅        | `lenient`         | `lenient` or `strict` — controls diagnostic severity.                                                                                                                                                                                                   |
| `consumer`                             |        ✅        |       ✅        | `api`             | `api` or `notebook`.                                                                                                                                                                                                                                    |
| `scalarFunction`                       |        ✅        |        —        | —                 | `auto`, `avg`, `min`, `max`, `sum`, `count`, `last`, `median`, `value`, or `percentile(<n>)`.                                                                                                                                                           |
| `format`                               |        ✅        |        —        | compact           | `pretty` returns pretty-printed DQL.                                                                                                                                                                                                                    |
| `errorLocations`                       |        ✅        |        —        | `false`           | When `true`, diagnostics carry a `{start,end}` character range.                                                                                                                                                                                         |

## Response schema

Both endpoints return the same per-selector object
(`TsmMetricSelectorTranspilationDTO`); `bulk` wraps a list of them in
`transpilationResults` (one entry per input, **in input order**). Fields are
**omitted when null or empty**, so treat missing arrays as empty.

The types below mirror the service DTOs and are the same interfaces defined in
[`scripts/transpile.ts`](scripts/transpile.ts):

```ts
// GET /api/v2/metrics/transpile
type TranspilationDTO = {
  // Derived server-side: any errors → "ERROR"; else any warnings →
  // "PARTIAL_SUCCESS"; else "SUCCESS". Serialized uppercase.
  status: "SUCCESS" | "PARTIAL_SUCCESS" | "ERROR";
  dql?: string; // omitted when transpilation failed
  errors?: Diagnostic[]; // omitted when empty
  warnings?: Diagnostic[]; // omitted when empty
  infos?: string[]; // omitted when empty
  metadata?: FieldMetadata[]; // omitted when empty
};

// POST /api/v2/metrics/transpileBulk
type CollectionDTO = { transpilationResults: TranspilationDTO[] };

// A diagnostic is a PLAIN STRING by default; only when the request set
// errorLocations=true is it an object with a range.
type Diagnostic =
  | string
  | { message: string; range: { start: number; end: number } };

type FieldMetadata = {
  index: number; // index into the input selector list
  id: string; // output column name (e.g. "expression")
  scalar: boolean; // true = single value, false = series
  metricId: string; // the original selector this column derives from
  unit?: string; // omitted when unknown
  shifted: boolean; // true if a timeshift operator was applied
};
```

- `dql` — the generated query. For a multi-metric expression the value column is
  named **`expression`** (see `metadata[].id`).
- `infos[]` — non-fatal notes. **Important**: a metric missing from Grail is
  frequently _auto-substituted_ (e.g. `builtin:service.errors.server.successCount`
  → `dt.service.request.count` plus a filter) and reported here — this does
  **not** fail the transpile. Always surface `infos` to the user, as a
  substitution can change the query's semantics.

### Detecting failure

Failure detection is deterministic from `status`:

| `status`          | Meaning                            | Action                                                                           |
| ----------------- | ---------------------------------- | -------------------------------------------------------------------------------- |
| `SUCCESS`         | Clean transpile                    | Use the DQL.                                                                     |
| `PARTIAL_SUCCESS` | DQL produced, but warnings present | Use the DQL, but **review** `warnings` and `infos` — semantics may have shifted. |
| `ERROR`           | No usable DQL (`dql` absent)       | Treat as unmigratable; record `errors[]`.                                        |

Equivalently: a non-empty `errors[]` means failure; a non-empty `warnings[]`
without errors means partial success.

## The `transpile.ts` script

The script is the **only** supported way to call the transpiler. It reads
credentials from `.dtmigration`, calls the right endpoint, and emits a
**normalized** JSON array — one entry per input selector, in input order, with
the same shape whether you used `single` or `bulk`:

```ts
type TranspileResult = {
  input: string; // the original selector/expression
  status: "SUCCESS" | "PARTIAL_SUCCESS" | "ERROR";
  dql: string | null; // null on failure
  infos: string[];
  warnings: { message: string; range?: { start: number; end: number } }[];
  errors: { message: string; range?: { start: number; end: number } }[];
  metadata: FieldMetadata[];
};
```

Diagnostics are normalized to `{ message, range? }` regardless of the
`errorLocations` setting, so callers can read `.errors[].message` uniformly.

### Usage

```text
# Single selector/expression
node --experimental-strip-types scripts/transpile.ts single \
  --selector '(100)*(builtin:service.errors.server.successCount:splitBy())/(builtin:service.requestCount.server:splitBy())' \
  --resolution 1m

# Batch: --input is a JSON array ["sel1","sel2"] or {"metricSelectors":[...]},
# or "-" to read that JSON from stdin. Use --output to capture the result in a
# file — see "Reading the result" below for why this is the safer default.
node --experimental-strip-types scripts/transpile.ts bulk \
  --input selectors.json --mode strict --output results.json
```

Options: `--config <path>` (default `.dtmigration`), `--output <path>`,
`--resolution`, `--from`, `--to`, `--mode`, `--consumer` (all subcommands);
plus `--scalar-function`, `--format pretty`, `--error-locations` (`single`
only). Run with `--help` for the full list.

### Reading the result

The result JSON goes to **stdout** by default, or to a file when you pass
`--output <path>`. All progress notes, warnings, and errors — from this script
**and** from the `dtctl` subprocess it invokes to resolve the environment — go
to **stderr**.

Prefer `--output <path>` whenever you machine-read the result (bulk runs, or
anything you parse afterwards). The script writes the JSON straight to that
file, so it is guaranteed to contain **only** the JSON payload. Redirecting
stdout (`> results.json`) usually works too, but if you merge streams
(`> results.json 2>&1`) an incidental `dtctl` warning such as
`warning: ignoring aliases and hooks from local config …` can end up in the
file and break JSON parsing. `--output` removes that risk entirely.

On an HTTP error (e.g. `400` for a malformed request, `401/403` for a bad
token) the script prints the status and body to stderr and exits non-zero. A
selector the transpiler simply cannot convert is **not** an HTTP error — it
comes back `200` with `status: "ERROR"`.

## Using the output

The transpiler returns a ready-to-run DQL whose value column is named per
`metadata[].id` (typically `expression`). The **calling reference** decides how
to adapt it — typically:

1. **Rename / wrap the value column** for the target use (e.g. an SLO needs an
   `sli` column; a dashboard tile may keep `expression`).
2. **Attach entity scope** if the original 2G config carried a separate entity
   selector (that scope is _not_ part of the metric expression).
3. **Review `infos[]` and `warnings[]`** — a metric substitution or a
   `PARTIAL_SUCCESS` may change meaning; flag for human review.

Only fall back to transpiling individual metric selectors if a full expression
returns `status: "ERROR"`.

## Examples

**Multi-metric ratio (success).** Input:

```
(100)*(builtin:service.errors.server.successCount:splitBy())/(builtin:service.requestCount.server:splitBy())
```

Normalized result (abridged) — the transpiler assembled the ratio into one DQL
and noted a Grail substitution in `infos`:

```json
[
  {
    "input": "(100)*(builtin:service.errors.server.successCount:splitBy())/(builtin:service.requestCount.server:splitBy())",
    "status": "SUCCESS",
    "dql": "timeseries { count = sum(dt.service.request.count, filter: { failed == false }), count.0 = sum(dt.service.request.count) }\n| fieldsAdd expression = 100 * count[] / count.0[]\n| fieldsRemove count.0, count",
    "infos": [
      "The metric `builtin:service.errors.server.successCount` does not exist in Grail and is replaced with the metric `dt.service.request.count` plus an additional filter."
    ],
    "warnings": [],
    "errors": [],
    "metadata": [
      {
        "index": 0,
        "id": "expression",
        "scalar": false,
        "metricId": "builtin:service.errors.server.successCount",
        "shifted": false
      }
    ]
  }
]
```

**Unmigratable selector (failure).** A selector whose data model has no Grail
equivalent (e.g. a `builtin:containers.*` metric) or invalid syntax returns:

```json
[
  {
    "input": "…",
    "status": "ERROR",
    "dql": null,
    "infos": [],
    "warnings": [],
    "errors": [{ "message": "…" }],
    "metadata": []
  }
]
```

## Known limitations

Selectors that tend to fail (`status: "ERROR"`). Multi-metric arithmetic is
**not** in this list — the transpiler assembles ratios and constants itself.

| Category                                                  | Behavior                                                          |
| --------------------------------------------------------- | ----------------------------------------------------------------- |
| Multi-metric arithmetic (ratios, constants)               | **Works** — assembled into one DQL                                |
| Metric not present in Grail                               | Usually **auto-substituted** with an `infos` note (not a failure) |
| K8s / `builtin:containers.*`                              | Typically **fails** (2G↔Grail data-model mismatch)                |
| `legacy.*` on phase-3 tenants                             | Typically **fails** (blocked from Grail forwarding)               |
| Unsupported operators (neither aggregation nor `splitBy`) | Typically **fails**                                               |
| Invalid or empty selector syntax                          | **Fails** (parser rejects)                                        |

When a selector genuinely fails, the calling reference decides how to handle it
(e.g. route the config to an "unmigratable" bucket) and records the
`errors[].message`.

## References

- [scripts/transpile.ts](scripts/transpile.ts) — the transpiler client
- [.dtmigration.example](.dtmigration.example) — credential template
