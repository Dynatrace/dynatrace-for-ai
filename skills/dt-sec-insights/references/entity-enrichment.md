# Entity Enrichment — Moved to dt-sec-contextualization

> **This capability has moved to `dt-sec-contextualization`.**
>
> Load **dt-sec-contextualization** and read
> `references/entity-enrichment.md` for all entity-mapping recipes:
>
> - 3-way match for K8s workloads (Paths 1 / 2 / 3)
> - Host enrichment by IP and by entity
> - Cloud entity enrichment (Path 1)
> - Natural-language entity name fallback
> - Problem → affected entities → findings (two-query chain)
> - Entity-scoping OR-chain
> - Pre-flight check for identifier availability
>
> The layering contract: dt-sec-contextualization is a lower layer that
> owns the Smartscape mapping primitive and is free of finding-schema
> semantics. dt-sec-insights is a consumer that calls into it for any
> question that needs Smartscape entity resolution.

---

For backwards-compatible cross-links from within dt-sec-insights references,
the key sections are now at:

| Old section | New location |
|---|---|
| § 3-Way Match Strategy | `dt-sec-contextualization/references/identity-mapping.md` (Mapping Primitive section) |
| § Pre-flight check | `dt-sec-contextualization/references/identity-mapping.md` § Mapping Primitive (Pre-flight Check) |
| § Cloud Entity Enrichment | `dt-sec-contextualization/references/entity-enrichment.md` § Cloud Entity Enrichment |
| § K8s Workload Enrichment | `dt-sec-contextualization/references/entity-enrichment.md` § K8s Workload Enrichment |
| § Host Enrichment by IP | `dt-sec-contextualization/references/entity-enrichment.md` § Host Enrichment by IP |
| § Natural-language fallback | `dt-sec-contextualization/references/entity-enrichment.md` § Natural-language Entity Name Fallback |
| § Problem → entities → findings | `dt-sec-contextualization/references/entity-enrichment.md` § Problem → Affected Entities → Findings |
