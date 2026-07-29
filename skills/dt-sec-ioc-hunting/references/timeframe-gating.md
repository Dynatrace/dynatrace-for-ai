# Timeframe Gating

Log and span hunt queries default to a tight 15-minute window to control scan
cost. This reference defines when and how to widen.

## Default Windows

| Data source | Default window | Rationale |
|---|---|---|
| `fetch logs` | `from:now()-15m` | High volume. Use `matchesPhrase(content, "<ioc>")` as the unscoped prefilter; raw `contains(content, ...)` across all logs may hit Grail's 10-second limit. |
| `fetch spans` | `from:now()-15m` | High volume; root-span fan-out. Even 1h can exceed read limits |
| `security.events` detections | `from:now()-2h` | Managed by `dt-sec-insights` (widen to 24h on empty) |
| `security.events` RVA vulnerabilities | `from:now()-30m` | Snapshot window; widening has no effect |

## Event-Anchored Hunts

When IoCs are extracted from a specific detection, security event, log line,
span, or other timestamped record, do **not** start with `from:now()-15m` if that
would miss the source event. Use the source timestamp as the anchor and search a
surrounding evidence window first.

Default anchored window:
`from:<event_time - 15m>, to:<event_time + 15m>`

Use this for fields such as `finding.time.created`, event `timestamp`, log
`timestamp`, span `timestamp`, or any user-provided event time.

Rationale:
- The 15 minutes before the event can reveal reconnaissance, scanning, or setup.
- The event time covers the triggering activity itself.
- The 15 minutes after the event can reveal follow-up requests, exfiltration, or
  lateral movement.
- The bounded absolute window is often cheaper and more reliable than a broad
  `now()-1h` query.

Rules:
1. Keep the same log/span hunt template; replace only the `from:` / `to:` range.
2. Never set `to:` in the future. If `event_time + 15m` is later than now, use
   `to:now()` or omit `to:`.
3. If multiple source events are supplied, either run one window per event or use
   a combined bounded window from the earliest `event_time - 15m` to the latest
   `event_time + 15m`; report which choice was used.
4. If the anchored window returns zero rows and the user wants broader discovery,
   then follow the interactive expansion protocol from that point.
5. If the anchored window hits `FETCH_EXEC_TIME_LIMIT`, treat it as
   INCONCLUSIVE and prefer entity scoping or smaller per-event windows before
   widening.

Example:

```dql-template
fetch spans, from:toTimestamp("2026-07-16T11:53:27Z"), to:toTimestamp("2026-07-16T12:23:27Z")
| filter request.is_root_span == true
...
```

### Optional Scope Pre-Filtering for Logs

Raw `contains(content, ...)` has no column index. On high-volume tenants unscoped
15-minute windows can hit Grail's 10-second execution limit. Prefer the
`matchesPhrase(content, "<ioc>")` prefilter from `hunt-logs.md` for broad
unscoped discovery before considering entity scoping.

**Unscoped hunts are valid** when the user has only IoCs and no entity context.
`FETCH_EXEC_TIME_LIMIT` is INCONCLUSIVE, not a failure. Never add a scope filter
that the user did not provide — it narrows the lookup domain and can miss evidence.

When `FETCH_EXEC_TIME_LIMIT` occurs on `fetch logs`:
1. Confirm the query uses literal `matchesPhrase(content, "<ioc>")` clauses, not
   raw `iAny(contains(content, allObservables[]))` as the first content filter.
2. If it still times out, mark the result INCONCLUSIVE.
3. Ask the user whether they want to narrow by entity or accept INCONCLUSIVE.
4. If the user provides entity context (namespace, host, service): re-run with
   the appropriate scope pre-filter.
   See `hunt-logs.md` → "Scoped vs Unscoped Hunting" for filter examples.
5. Do NOT widen the window as a substitute for scoping — widening increases
   scan volume further.

## Interactive Mode (standalone agent use)

The default initial window is `from:now()-15m` for unanchored hunts. For hunts
derived from a timestamped detection/log/event, use the event-anchored window
above as the initial window. When the user explicitly requests a specific initial window — whether narrower
(e.g. "last 5m") or wider (e.g. "last hour", "last 3 hours") — honor that request
directly and use it as the starting window. Never use a window different from what
the user specified; apply the default 15m only when no window is given.

Expansion is step-by-step and requires explicit user approval to move beyond the current window.
If the user gives blanket approval (e.g. "expand if nothing shows up"), treat that as approval
for the full step sequence below (still report each window used).
1. Run hunt at the initial window (default `from:now()-15m`, or the user-requested
   window if one was specified).
2. Report result and ask approval before the next step (`from:now()-1h` if starting
   from default).
3. If approved, run `from:now()-1h` and report the result.
4. If still empty, ask approval before `from:now()-3h`.
5. If approved, run `from:now()-3h` and report the result.
6. If still empty, ask approval before `from:now()-24h`.
7. If approved, run `from:now()-24h` and report the result.
8. Stop at 24h by default. Go beyond (up to 7d) only if the user explicitly
requests it.

Never run a wider query without explicit approval for that step.
Never run two window sizes in parallel.

Expansion sequence:
`15m -> 1h -> 3h -> 24h -> 7d (only if explicitly requested)`

## Autonomous Mode (sub-agent invocation)

When this skill is loaded by a parent agent programmatically (no human in the
loop), the approval gate is bypassed:

1. Run hunt at `from:now()-15m` only.
2. If zero rows, do not auto-expand. Report:

"No matches found in the last 15 minutes (searched window: now()-15m).
Expansion to 1h, 24h, or 7d would require user approval."

3. Surface the empty result so the user can decide whether to widen later.

Default mode is autonomous unless set otherwise by the orchestrator.

## Scan Cost Reference

| Window | Relative data volume |
|---|---|
| 15 minutes | 1x |
| 1 hour | 4x |
| 3 hours | 12x |
| 24 hours | 96x |
| 7 days | 672x |

Source: `dt-dql-essentials` `references/optimization.md` section
"Time Optimization".
