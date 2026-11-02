# 3rd-Party Monitor Migration

Migrate customer 3rd-party monitor integrations from the deprecated
`POST /api/v1/synthetic/ext/tests` API to the Grail-native events ingest API
(`POST /platform/ingest/custom/events/external.tests`).

Load **dt-obs-ext-monitors** for the complete new API schema reference before
writing or reviewing any migrated code.

## Execution Model

This skill always follows this sequence — do not skip steps:

1. **Survey** — run the intake questions (load [intake.md](references/intake.md))
2. **Discover** — read the project to understand its structure, language, and components
3. **Plan** — write `MIGRATION_PLAN.md` into the project root with all migration steps as `- [ ]` TODOs
4. **Confirm** — present the plan and wait for explicit customer approval before touching any code
5. **Execute** — work through each TODO in order, marking `- [x]` immediately upon completion
6. **Verify** — run the DQL smoke tests from [verification.md](references/verification.md)

**Resume rule**: if `MIGRATION_PLAN.md` already exists in the project root when this reference is
loaded, read it first, identify the first unchecked `- [ ]` item, and continue from there.
Do not restart completed steps.

**Idempotency rule**: before starting any step, check whether it is already done
(file already migrated, test already updated, etc.). Mark it complete and move on if so.

## Reference Index

| Reference | When to load |
|-----------|-------------|
| [intake.md](references/intake.md) | Always — first thing at session start |
| [schema-mapping.md](references/schema-mapping.md) | Before migrating any model, builder, or client code |
| [workflow.md](references/workflow.md) | When building MIGRATION_PLAN.md and executing migration steps |
| [examples-java.md](references/examples-java.md) | When the customer project is Java |
| [examples-python.md](references/examples-python.md) | When the customer project is Python |
| [examples-node.md](references/examples-node.md) | When the customer project is Node.js |
| [verification.md](references/verification.md) | After migration is complete |

## Migrator Script

A standalone Python script is available at [migrator/migrate_monitors.py](migrator/migrate_monitors.py)
for migrating static JSON fixture files that contain legacy `SyntheticPayload` payloads.

```
python migrator/migrate_monitors.py --type <test_type> <input> [output]
```

- `--type` — **required**. One of: `browser`, `api`, `http`, `mobile`. The legacy format carries no type field so it cannot be inferred; this must match the monitors in the input. When a directory contains monitors of mixed types, run the script once per type on separate files or sub-directories.
- `input` — a single `.json` file or a directory (processed recursively)
- `output` — optional; defaults to in-place migration
- Non-monitor JSON files are detected automatically and skipped
