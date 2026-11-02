# Translation Reference

Task-relevant details from `dtctl translate classic-pipelines` (previously `dtctl get classic-pipelines-translation`) needed during the upgrade workflow.

## Processor placeholder format

When a processing rule cannot be translated, a processor placeholder is emitted and a `withWarning=true` message appears in `.context.warnings` of the `-A` envelope (or on stderr without `-A`). Each processor placeholder preserves the original processor's `id`, `matcher`, `enabled`, and `sampleData`, and adds:

- `dql.script` — the partially translated DQL (or the original script verbatim on major failure)
- `description` — one of:
  - `DQL translation failed due to an unexpected issue.` — original script placed verbatim in `dql.script`
  - `Auto-translated DQL script is invalid. <reason>` — partial result in `dql.script`; reason describes the specific validation failure

Use the `description` value to identify processor placeholders. When fixing, look up the original classic rule by the processor placeholder's `id` in the source schema.

For known processor placeholder patterns and how to resolve them, see [translation-issue-fixes/dql-scripts.md](translation-issue-fixes/dql-scripts.md).

## Davis event extraction field mapping

Classic event extraction rules are translated to Davis event processors using this mapping:

| Classic field | Davis property key | Notes |
|---|---|---|
| `title` | `event.name` | Placeholder keys (e.g. `{someKey}`) renamed to Davis attribute equivalents |
| `eventType` | `event.type` | Enum name written as-is |
| `davisMerge` | `dt.davis.is_merging_allowed` | Controls problem merging |
| `description` | `event.description` | Only added if non-empty |
| `metadata` items | key-value properties | Both key names and placeholder keys in values renamed to Davis attribute equivalents |

If `event.name`, `event.type`, `dt.davis.is_merging_allowed`, or `event.description` were already present as metadata items, the result may contain duplicate property keys — see [translation-issue-fixes/misc.md](translation-issue-fixes/misc.md).
