"""Per-metric migration verdict, and the two aggregate views the report needs.

One record per calculated service metric defined on the tenant. The verdict answers a single
question — *can this be migrated as an OpenPipeline span metric* — and, when it can, the
candidate processor is written to disk next to the report. How it gets deployed is the
customer's decision: no pipeline, no pipeline group and no routing entry is produced here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .catalog import metric_report
from .processor import Unsupported, build_processor, target_metric_key

PROCESSOR_DIR = "processors"

#: Three explanations that recur across several classic elements, written once. They are
#: customer-facing, so they follow the report register: plain language, nothing about the
#: environments the mapping was measured on.
CLIENT_SIDE = (
    "Classic measures this the way the caller saw it. The migration extracts from the span the "
    "service itself produced, which records the server side, so the two do not measure the same "
    "thing."
)
CHILD_CALLS = (
    "Classic added this up over the calls a request made further down the chain. A processor "
    "looks at one span at a time and cannot total up child calls."
)
FAILED_FOLD = (
    "Classic treats a request as failed when either the caller or the service saw a failure. The "
    "span records only what the service saw, so a metric built on it would cover a different set "
    "of requests. Deciding which of the two you want is not something this migration can do for "
    "you."
)

#: Verdict keys, and the label the report prints for each. The keys are the machine contract;
#: only the labels are customer-facing wording.
#:
#: The verdict answers *can this be migrated* and nothing else. Whether the metric still
#: receives data is a separate property (``traffic``): a dormant metric that could be rebuilt
#: belongs with the ones that can be rebuilt, ranked below the live ones, not in a category of
#: its own where its verdict is never computed.
VERDICTS = {
    "migratable": "Can be migrated",
    "migratable_inexact": "Can be migrated, not exactly",
    "not_migratable": "Cannot be migrated",
    "unknown": "Not assessed",
}

#: Blockers that share a root cause, so the reason list reports the underlying gap rather than
#: one row per classic element.
BLOCKER_FAMILIES = {
    "REQUEST_TYPE": "Request type (classic service method group)",
    "SERVICE_TAG": "Entity tags",
    "PROCESS_GROUP_TAG": "Entity tags",
    "HOST_TAG": "Entity tags",
    "TAG_KEY_EQUALS": "Entity tags",
    "TAG_KEY_EQUALS_ANY_OF": "Entity tags",
    # Server-side failure verdict: same field, same client/server divergence.
    "FAILED_STATE": "Failure detection semantics",
    "FAILED_REQUEST_COUNT": "Failure detection semantics",
    "SUCCESSFUL_REQUEST_COUNT": "Failure detection semantics",
    "FAILURE_RATE": "Failure detection semantics",
    "FAILURE_REASON": "Failure detection semantics",
    # Client-side measurements are a *different* root cause: there is no client-side span
    # selection to extract from at all, rather than a verdict that folds sides differently.
    "FAILED_REQUEST_COUNT_CLIENT": "Client-side measurements",
    "SUCCESSFUL_REQUEST_COUNT_CLIENT": "Client-side measurements",
    "FAILURE_RATE_CLIENT": "Client-side measurements",
    "HTTP_4XX_ERROR_COUNT_CLIENT": "Client-side measurements",
    "HTTP_5XX_ERROR_COUNT_CLIENT": "Client-side measurements",
    "RESPONSE_TIME_CLIENT": "Client-side measurements",
    # Aggregates over a service call's children, not properties of one span.
    "PROCESSING_TIME": "Child-call and processing-time aggregates",
    "TOTAL_PROCESSING_TIME": "Child-call and processing-time aggregates",
    "DATABASE_CHILD_CALL_COUNT": "Child-call and processing-time aggregates",
    "DATABASE_CHILD_CALL_TIME": "Child-call and processing-time aggregates",
    "NON_DATABASE_CHILD_CALL_COUNT": "Child-call and processing-time aggregates",
    "NON_DATABASE_CHILD_CALL_TIME": "Child-call and processing-time aggregates",
    "REGEX_MATCHES": "Regular expressions",
    "REGEX_EXTRACTION": "Regular expressions",
}

#: Element labels that are built from a compared *value* rather than taken from a catalog row,
#: so they cannot be keyed exactly. ``metric_report`` renders them as
#: ``"<type> <comparison> <value>"`` — a substring is the only stable handle.
_FAMILY_CONTAINS = (
    ("DATABASE_SERVICE", "Database and external services"),
    ("EXTERNAL", "Database and external services"),
)


#: The sentence a *root cause* row prints. Without these the row borrows the text of whichever
#: element happened to be seen first, which then speaks for the whole family — "Service tags are
#: not available on spans" standing in for a row that also covers process-group and host tags.
FAMILY_REASONS = {
    "Entity tags": (
        "Tags on services, process groups and hosts are not available on spans, so a condition "
        "on them cannot be checked."
    ),
    "Failure detection semantics": FAILED_FOLD,
    "Client-side measurements": CLIENT_SIDE,
    "Child-call and processing-time aggregates": CHILD_CALLS,
    "Regular expressions": (
        "Classic matches a regular expression against the value. A processor cannot run regular "
        "expressions."
    ),
    "Not expressible in an OpenPipeline processor": (
        "These metrics ask for something a span processor cannot express. Each entry says which "
        "part of its definition it is."
    ),
}


def family_of(element: str) -> str:
    """The root cause *element* belongs to, or the element itself."""
    if element in BLOCKER_FAMILIES:
        return BLOCKER_FAMILIES[element]
    for needle, family in _FAMILY_CONTAINS:
        if needle in element:
            return family
    return element


_CATALOG_SECTIONS = (
    "conditionAttributes", "measurements", "comparisons", "comparisonTypes",
    "dimensions", "topLevel",
)


#: Printed when a catalog entry has no ``report_comment``. Deliberately vague rather than
#: falling back to ``comment``: that field is an internal engineering note carrying the
#: environments we measured on, cluster source paths, dates and open-question tags, none of
#: which belong in a report produced for somebody else's environment.
_NO_REPORT_COMMENT = (
    "This part of the classic definition has no equivalent on spans, so the metric cannot be "
    "migrated as it stands."
)


def _catalog_comment(catalog: dict, source: str) -> str:
    """The customer-facing sentence for one classic element.

    Reads ``report_comment`` only. Every catalog entry that can block a metric has one.
    """
    from .catalog import index

    for name in _CATALOG_SECTIONS:
        entry = index(catalog, name).get(source)
        if entry:
            return (entry.get("report_comment") or "").strip() or _NO_REPORT_COMMENT
    return _NO_REPORT_COMMENT


def describe(definition: dict) -> list[str]:
    """What the classic metric does, one plain line per part.

    A request attribute is named rather than left as ``SERVICE_REQUEST_ATTRIBUTE``: the attribute
    is the whole content of the condition, and the enum name alone tells the reader nothing about
    which of their attributes this metric depends on.
    """
    out: list[str] = []
    metric_definition = definition.get("metricDefinition") or {}
    measure = metric_definition.get("metric")
    if measure == "REQUEST_ATTRIBUTE" and metric_definition.get("requestAttribute"):
        out.append(f"measures the request attribute **{metric_definition['requestAttribute']}**")
    elif measure:
        out.append(f"measures **{measure}**")
    for condition in definition.get("conditions") or []:
        info = condition.get("comparisonInfo") or {}
        value = info.get("value")
        if value is None and info.get("values"):
            value = ", ".join(str(v) for v in info["values"])
        rendered = f"`{value}`" if value is not None else ""
        negate = "not " if info.get("negate") else ""
        subject = (
            f"request attribute **{info['requestAttribute']}**"
            if info.get("requestAttribute")
            else f"**{condition['attribute']}**"
        )
        out.append(
            f"where {subject} {negate}{info.get('comparison', '')} {rendered}".strip()
        )
    dimension = (definition.get("dimensionDefinition") or {}).get("dimension")
    if dimension:
        out.append(f"split by **{dimension}**")
    if definition.get("entityId"):
        out.append(f"scoped to `{definition['entityId']}`")
    if definition.get("managementZones"):
        out.append("scoped to a management zone")
    return out


def assess_metric(
    definition: dict,
    catalog: dict,
    *,
    has_data: bool | None,
    traffic_window: str,
    in_grail: bool = True,
) -> dict[str, Any]:
    """The migration record for one classic definition.

    *has_data* is ``None`` when the datapoint check could not answer for this metric — either
    the query failed, or the metric is not enabled for Grail and therefore has no ``service.*``
    series to look for. Neither case may read as dormant.
    """
    classic_key = definition["tsmMetricKey"]
    record: dict[str, Any] = {
        "classic_metric_key": classic_key,
        "metric_key": classic_key.removeprefix("calc:"),
        "name": definition.get("name") or "",
        "enabled": bool(definition.get("enabled", True)),
        "description": describe(definition),
        "notes": [],
        "inexact": [],
        "blockers": [],
        "traffic": (
            "unknown" if has_data is None else "recent" if has_data else "none"
        ),
        "traffic_window": traffic_window,
        "in_grail_inventory": in_grail,
    }
    if has_data is False:
        # Kept apart from ``notes``: this says nothing about the replacement, it says the
        # metric may not be worth one. The verdict below is computed all the same, so a
        # dormant metric still tells the reader whether it *could* be rebuilt.
        record["traffic_note"] = (
            f"No datapoint in the last {traffic_window}, so there is nothing for a replacement "
            "metric to measure today. Check whether this metric is still wanted before spending "
            "any effort on it — a metric that only reports monthly can look dormant in this "
            "window."
        )
    if not in_grail:
        # Without Grail forwarding there is no `service.<key>` series, so the datapoint check
        # cannot see this metric at all. Calling it dormant on that basis would be wrong: the
        # classic metric may well be collecting.
        record["notes"].append(
            "This metric is not enabled for Grail, so it is not available under its "
            "`service.*` key and this report cannot tell whether it still collects data. A "
            "dashboard, SLO or alert on the new platform cannot read it today either."
        )

    try:
        report = metric_report(catalog, definition)
    except Exception as exc:  # noqa: BLE001 - a catalog gap is not a failed scan
        # The catalog indexes classic enums by name, so a value it has never seen — a newer
        # cluster version, or a shape no environment used while the catalog was built — raises
        # rather than resolving. That is a gap in the catalog, not a verdict about the metric,
        # and it must not take every other metric down with it.
        record["verdict"] = "unknown"
        record["reason"] = (
            "the definition uses a classic element the bundled mapping catalog does not cover "
            f"({exc}), so no verdict can be given for it"
        )
        return record

    if report["verdict"] == "blocked":
        record["verdict"] = "not_migratable"
        record["blockers"] = [
            {
                "kind": kind,
                "element": value,
                "status": status,
                "why": (report.get("reasons") or {}).get(value)
                or _catalog_comment(catalog, value),
                "family": family_of(value),
            }
            for kind, value, status in report["blockers"]
        ]
        return record

    try:
        processor, notes, inexact = build_processor(definition)
    except Unsupported as exc:
        # The catalog says the classic elements have Phase 3 equivalents but this code cannot
        # write the config. That is our gap, not a platform gap, and it is kept apart in the
        # machine record while the report says the same thing to the customer either way.
        record["verdict"] = "not_migratable"
        record["generator_gap"] = str(exc)
        record["blockers"] = [
            {
                "kind": "configuration",
                "element": "not expressible in a span processor",
                "status": "GENERATOR_GAP",
                "why": exc.plain,
                "family": "Not expressible in an OpenPipeline processor",
            }
        ]
        return record

    record["verdict"] = "migratable_inexact" if inexact else "migratable"
    record["target_metric_key"] = target_metric_key(classic_key)
    record["processor_file"] = f"{PROCESSOR_DIR}/{record['target_metric_key']}.json"
    record["processor"] = processor
    # extend, not assign: a note added earlier — "not enabled for Grail" — must survive.
    record["notes"].extend(notes)
    record["inexact"] = inexact
    if report["warnings"]:
        record["top_n_dropped"] = True
    return record


def assess(
    definitions: dict[str, dict],
    catalog: dict,
    *,
    keys_with_data: set[str],
    traffic_known: bool,
    traffic_window: str,
    grail_keys: set[str] | None = None,
) -> list[dict[str, Any]]:
    """One record per definition, ordered by metric key.

    *grail_keys* is the inventory of metrics enabled for Grail. A metric outside it has no
    ``service.*`` series by construction, so its traffic state is unknown rather than empty:
    the datapoint check cannot see such a metric at all, and would otherwise report every one of
    them as dormant while its classic counterpart collects normally.
    """
    records = []
    for classic_key in sorted(definitions):
        definition = definitions[classic_key]
        grail_key = classic_key.removeprefix("calc:")
        in_grail = grail_keys is None or grail_key in grail_keys
        has_data = (grail_key in keys_with_data) if (traffic_known and in_grail) else None
        records.append(
            assess_metric(
                definition,
                catalog,
                has_data=has_data,
                traffic_window=traffic_window,
                in_grail=in_grail,
            )
        )
    return records


def totals(records: list[dict[str, Any]]) -> dict[str, int]:
    """Verdict counts, plus how many of the assessed metrics are dormant.

    ``no_traffic`` is counted from the traffic state rather than from a verdict: dormancy is a
    property of the metric today, not of whether it can be migrated, and every dormant metric
    also carries one of the four verdicts.
    """
    counts = {key: 0 for key in VERDICTS}
    for record in records:
        counts[record.get("verdict", "unknown")] = (
            counts.get(record.get("verdict", "unknown"), 0) + 1
        )
    counts["assessed"] = len(records)
    counts["migratable_total"] = counts["migratable"] + counts["migratable_inexact"]
    counts["no_traffic"] = sum(1 for record in records if record.get("traffic") == "none")
    counts["migratable_with_data"] = sum(
        1
        for record in records
        if record.get("verdict") in ("migratable", "migratable_inexact")
        and record.get("traffic") != "none"
    )
    return counts


def blocking_reasons(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Why metrics cannot be migrated, one row per root cause.

    Deliberately light: the root cause, the classic elements behind it, and how many metrics it
    stops. No ranking by potential and no *only blocker* column — the blocking element is
    already named on each metric, and this list exists so a reader can see the shape of the
    remainder at a glance.
    """
    rows: dict[str, dict[str, Any]] = {}
    for record in records:
        if record.get("verdict") != "not_migratable":
            continue
        for blocker in record["blockers"]:
            row = rows.setdefault(
                blocker["family"],
                {
                    "family": blocker["family"],
                    "elements": set(),
                    "metrics": set(),
                    "why": FAMILY_REASONS.get(blocker["family"], blocker["why"]),
                },
            )
            row["elements"].add(blocker["element"])
            row["metrics"].add(record["classic_metric_key"])
            if not row["why"]:
                row["why"] = blocker["why"]
    ordered = sorted(rows.values(), key=lambda row: (-len(row["metrics"]), row["family"]))
    return [
        {
            "family": row["family"],
            "elements": sorted(row["elements"]),
            "metrics": len(row["metrics"]),
            "why": row["why"],
        }
        for row in ordered
    ]


def decisions(records: list[dict[str, Any]]) -> list[str]:
    """Tenant-wide differences the customer decides on, deduplicated across metrics.

    Everything here applies to a metric that *can* be migrated — these are the reasons a
    migrated metric is not simply a drop-in replacement.
    """
    out: list[str] = []
    migratable = [
        record for record in records
        if record.get("verdict") in ("migratable", "migratable_inexact")
    ]
    if not migratable:
        return out

    out.append(
        "**The metric gets a new name.** The old key is still in use by the classic metric, so "
        "a migrated metric cannot reuse it: `service.foo` becomes `migrated.service.foo`. Every "
        "dashboard, notebook, SLO, guardian and alert listed above has to be pointed at the new "
        "name."
    )
    top_n = sum(1 for record in migratable if record.get("top_n_dropped"))
    if top_n:
        out.append(
            f"**The \"top N values\" limit is gone** on {top_n} metric(s). Classic kept only "
            "the top few values of a split; a migrated metric keeps them all, so sorting and "
            "limiting move into the query that reads it. Where a split takes many different "
            "values, check how many that produces first."
        )
    inexact = sum(1 for record in migratable if record.get("verdict") == "migratable_inexact")
    if inexact:
        out.append(
            f"**{inexact} metric(s) are not migrated exactly.** Their classic definition picks "
            "requests by something a span does not record the same way — the kind of a service, "
            "or the name a service or a process group is shown under after being renamed — so "
            "the migrated metric covers a slightly different set of requests. Each one says "
            "which, and in which direction, in its own entry."
        )
    out.append(
        "**The unit and the display name are not carried over.** They live on the classic "
        "definition, so a migrated metric starts without them and a tile that showed "
        "milliseconds shows a bare number instead. Set them on the new metric key with "
        "`builtin:metric.metadata`."
    )
    out.append(
        "**Where to put the processors is your decision.** Each one below is a single metric "
        "extraction processor, and nothing more: it is not attached to a pipeline, a pipeline "
        "group or a routing rule. Which pipeline a given service\'s spans go through depends on "
        "how this environment is set up, so add each processor where those spans are handled."
    )
    return out


def write_processors(output_dir: Path, records: list[dict[str, Any]]) -> int:
    """Write one processor JSON per migratable metric, and remove stale ones.

    Stale files are deleted first. A metric that generated on an earlier run and stopped
    generating on this one otherwise leaves a file behind that reads as a valid config.
    """
    directory = output_dir / PROCESSOR_DIR
    if directory.is_dir():
        for stale in directory.glob("*.json"):
            stale.unlink()
    written = 0
    for record in records:
        processor = record.get("processor")
        if not processor:
            continue
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{record['target_metric_key']}.json"
        path.write_text(json.dumps(processor, indent=2) + "\n", encoding="utf-8")
        written += 1
    return written
