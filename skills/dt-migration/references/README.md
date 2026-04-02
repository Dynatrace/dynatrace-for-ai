# dt-migration references

Use these references with `SKILL.md`.

## Read This First

1. Start with [`../SKILL.md`](../SKILL.md) for scope, use cases, and the compact mapping table.
2. Load [`migration-workflow.md`](migration-workflow.md) for the step-by-step migration process.
3. Then choose the most relevant deep reference for the task at hand.

## Reference Map

| File | When to use |
| --- | --- |
| [`migration-workflow.md`](migration-workflow.md) | You need the end-to-end migration process, validation checklist, and output structure |
| [`type-mappings.md`](type-mappings.md) | You need the full classic-to-Smartscape entity and field mapping tables |
| [`dql-function-migration.md`](dql-function-migration.md) | You need to migrate `entityName()`, `entityAttr()`, selectors, relationship fields, signal dimensions, or ID filters |
| [`relationship-mappings.md`](relationship-mappings.md) | You need to verify valid Smartscape edges and traversal targets |
| [`special-cases.md`](special-cases.md) | The query uses host group, process group, container group, or unsupported mappings |
| [`quick-reference.md`](quick-reference.md) | You need a compact cheat sheet or gotcha list |
| [`examples.md`](examples.md) | You need concrete before/after migration patterns |
| [`entity-host.md`](entity-host.md) | The migration centers on hosts, host tags, host groups, or host traversal |
| [`entity-service.md`](entity-service.md) | The migration centers on services, service relationships, or service signal dimensions |
| [`entity-process.md`](entity-process.md) | The migration centers on process-group-instance or process-group patterns |
| [`entity-container.md`](entity-container.md) | The migration centers on container-group-instance, container group, or affected-entity event joins |
| [`entity-kubernetes.md`](entity-kubernetes.md) | The migration centers on Kubernetes cluster, node, service, namespace, pod, or workload entities |
| [`entity-cloud-application.md`](entity-cloud-application.md) | The migration centers on `cloud_application`, `cloud_application_instance`, or `cloud_application_namespace` |

## Related Skills

- Load `dt-dql-essentials` before writing final DQL.
