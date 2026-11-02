# Translation Issue Fixes — Matcher Issues

Matcher validation errors encountered when upgrading a classic pipeline, with fix guidance.

See also: [dql-scripts.md](dql-scripts.md) | [misc.md](misc.md)

## Contents

- [LQL matchers](#lql-matchers)

## Guiding principle — no silent changes

The translated artifact is a faithful representation of the tenant's production configuration. The goal of every fix is to produce an equivalent result in OpenPipeline — not to simplify, not to clean up, and not to delete. **Every change made to the artifact must be communicated to the user.** Changes that are purely mechanical (rename, quote style, redundant no-op removal) should be described before or as they are applied. Changes that could affect runtime behavior — even in edge cases — must be confirmed by the user before they are made. When in doubt, surface the tradeoff and let the user decide.

## LQL matchers

**How to recognize them in the artifact:** When a classic matcher contained LQL, the translation rewrites the LQL into function-like expressions, `lqlMatchValue()` and `lqlMatchFullText()`, in the processor's `matcher` field. The presence of either function in `matcher` is the signal that the matcher needs deliberate conversion by the user. For example:

```json
{
  "id": "<processor-id>",
  "type": "dql",
  "enabled": true,
  "matcher": "lqlMatchValue(<field-name>, \"<field-value>\") and lqlMatchFullText(<field-name>, \"<search-text>\")",
  "description": "<processor-id>",
  "dql": { "script": "..." }
}
```

Validation fails because `lqlMatchValue` and `lqlMatchFullText` are not valid DQL functions.

**Do not send the `lqlMatch*` expression from the artifact to the translation endpoint.** The artifact contains a rewritten form produced by the translation tool — it is not the original LQL. Always go back to the source schema to get the original expression.

**Step 1 — look up the original matcher in the source schema.** Use the processor `id` to find the original classic rule in the Step 1 discovery output. The schema to query depends on which stage the processor is in and which scope (logs or bizevents) is being upgraded:

| Scope           | Stage             | Schema                                             |
| --------------- | ----------------- | -------------------------------------------------- |
| Logs            | Processing        | `builtin:logmonitoring.log-dpp-rules`              |
| Logs            | Security context  | `builtin:logmonitoring.log-security-context-rules` |
| Logs            | Metric extraction | `builtin:logmonitoring.schemaless-log-metric`      |
| Logs            | Event extraction  | `builtin:logmonitoring.log-events`                 |
| Logs            | Bucket assignment | `builtin:logmonitoring.log-buckets-rules`          |
| Business events | Processing        | `builtin:bizevents-processing-pipelines.rule`      |
| Business events | Security context  | `builtin:bizevents-security-context-rules`         |
| Business events | Metric extraction | `builtin:bizevents-processing-metrics.rule`        |
| Business events | Bucket assignment | `builtin:bizevents-processing-buckets.rule`        |

Inspect the settings object's `value` field — look for either a `query` or `matcher` key depending on the rule type. The original LQL expression is raw field comparisons (e.g. `k8s.namespace.name="name" AND content="run finished"`), not the `lqlMatch*` form from the artifact.

**Step 2 — translate the original LQL expression to DQL.** Use `dtctl translate lql-to-dql`, passing the expression read from the source schema. The command outputs the translated DQL expression as plain text. Requires `openpipeline:configurations:read` scope.

If you need to adjust the resulting expression by hand, load `dt-dql-essentials` if available. Note that matchers support only a subset of DQL, so the skill informs the edit but does not confirm it — Step 3 below is what establishes the expression is valid.

```dtctl
dtctl translate lql-to-dql '<original-lql-from-source-schema-unescaped>'
```

For multi-line matchers, pass the expression via a file instead of a positional argument:

```dtctl
dtctl translate lql-to-dql --file matcher.lql
# or from stdin:
dtctl translate lql-to-dql --file -
```

If `dtctl translate lql-to-dql` is not available in the installed dtctl version, call the endpoint directly. The `query` value must be the original LQL expression from the source schema:

```
POST /platform/openpipeline/v1/matcher/lqlToDql
Content-Type: application/json

{ "query": "<original-lql-from-source-schema>" }
```

The response has the same shape: `{ "query": "<translated-dql-expression>" }`.

**Step 3 — verify, then update the artifact.** Before replacing anything, verify the translated DQL expression is valid. Use `dtctl verify openpipeline-matcher`, scoped to the configuration and stage being upgraded:

```dtctl
dtctl verify openpipeline-matcher '<translated-dql-expression-unescaped>' --config-id logs --context <stage>
```

Valid `--context` values: `processing`, `securityContext`, `metricExtraction`, `davis`, `bucketAssignment`. Note: the bucket-assignment stage is keyed `storage` in the artifact but the context value here is `bucketAssignment`. Use `--config-id bizevents` when upgrading Business events. The command exits 0 on success and 1 with an error message on failure. For expressions that span multiple lines or contain special shell characters, pass via a file:

```dtctl
dtctl verify openpipeline-matcher -f matcher.dql --config-id logs --context processing
```

If dtctl is unavailable, fall back to the Python SDK example in [openpipeline-api.md](../openpipeline-api.md). Once the expression verifies clean, replace the `matcher` value in the affected processor with the translated expression and re-apply the artifact.
