# Troubleshooting

## Contents

- [Handling Zero Results](#handling-zero-results)
- [Setup-Level Zero Results](#setup-level-zero-results)
- [Old RUM Agent Versions](#old-rum-agent-versions)
- [Handling Anomalous Results](#handling-anomalous-results)
- [Decision Tree: Ask vs. Investigate](#decision-tree-ask-vs-investigate)
- [Common Investigation Steps](#common-investigation-steps)
- [Red Flags: When to Stop and Ask](#red-flags-when-to-stop-and-ask)

## Handling Zero Results

When queries return no data, follow this diagnostic workflow:

1. **Validate Timeframe**
   - Check if timeframe is appropriate for the data type
   - `user.events`: data may have a 1–2 minute delay for recent events
   - `user.sessions`: sessions are only written after ~30+ minutes of inactivity — recent sessions (last ~1 hour) will not appear at all; use `to: now() - 1h` when querying recent sessions to avoid false zero results
   - Verify timeframe syntax: `-1h to now()` or similar
   - Try expanding timeframe: `now()-24h` for initial exploration

2. **Verify frontend Configuration**
   - Confirm frontend is instrumented and sending RUM data
   - Check `frontend.name` filter is correct
   - Test without frontend filter to see if any RUM data exists
   - Verify frontend name matches the environment

3. **Check Data Availability**
   - Run basic query: `fetch user.events | limit 1`
   - If no events exist, RUM may not be configured
   - Check if timeframe predates frontend deployment
   - Verify user has access to the environment

4. **Review Query Syntax**
   - Validate filters aren't too restrictive
   - Check for typos in field names or metric names
   - Test query incrementally: start simple, add filters gradually
   - Verify characteristics filters match event types

**When to Ask User for Clarification:**
- No RUM data exists in environment → "Is RUM configured for this frontend?"
- Timeframe unclear → "What time period should I analyze?"
- Expected data missing → "Has this frontend sent data recently?"

## Setup-Level Zero Results

Check these before any query-level diagnostics — they are the most common root causes of zero data for newly configured frontends.

**10-minute initial delay:** After configuring a new frontend, data takes up to 10 minutes to appear. Check this before any other troubleshooting.

Ref: https://docs.dynatrace.com/docs/observe/digital-experience/new-rum-experience/web-frontends/initial-setup

**JS injection check:** Look in the browser for a script element with `data-config`, `data-envconfig`, or `data-appconfig` attribute. If `data-dtconfig` is present instead, RUM Classic is active but RUM on the latest Dynatrace is not yet enabled.

**Monitoring code download:** Check for `ruxitagentjs_` or `ruxitagent_` files returning HTTP 200. A 404, 503, or CSP block here means the RUM agent never loads.

**Beacon verification:** New-format beacons have URL path starting with `rb_` and contain `pv=4` in the query string. If absent, possible causes:
- Data-collection opt-in mode active (requires `dtrum.enable()` call)
- CSP inline violation blocking the agent
- Blocked beacon endpoint

**CSP blocking:** Not adapting CSP rules for the RUM JS silently blocks the RUM agent → zero data. This is distinct from beacon corruption; see [csp-violations.md](csp-violations.md) for CSP violation queries.

**Instrumentation method mismatch:** Automatic injection requires OneAgent on the web server. Selecting automatic injection without OneAgent support produces no data. See [prerequisites](https://docs.dynatrace.com/docs/observe/digital-experience/rum/web-frontends/initial-setup/enable-new-rum-for-web-apps#prerequisites) for OneAgent version requirements.

**Data mapped to wrong frontend:** Zero results for expected frontend but data exists elsewhere. Caused by detection rules misconfiguration or wrong priority order. Diagnose with:

```dql
fetch user.events, from: now() - 1h
| summarize count = count(), by: {frontend.name}
| sort count desc
```

Ref: https://docs.dynatrace.com/docs/shortlink/finalize-initial-setup-for-auto-injected-frontend

**Beacon query string corruption:** If infrastructure (CDN, WAF, proxy, tag manager) modifies beacon URL query parameters, RUM on the latest Dynatrace silently rejects the beacon → data gaps or zero results with no obvious cause. Check browser dev tools for requests to paths starting with `rb_`. Rejection error codes: `3014` (query string CRC mismatch) or `3001` (parameter `ty` missing).

Ref: https://docs.dynatrace.com/docs/observe/digital-experience/new-rum-experience/transition-from-rum-classic

## Old RUM Agent Versions

Two frontend agent types affect RUM on Grail data quality:

- **RUM JS** (web frontend) — part of OneAgent. GA for RUM on Grail from version 1.329; agents below 1.329 are not officially supported (preview versions only).
- **Mobile agent** (iOS, Android, cross-platform) — part of OneAgent for Mobile. GA for RUM on Grail from version 8.329.

Agent version and type are available as fields on `user.events`: `dt.rum.agent.version` and `dt.rum.agent.type` — see the [Semantic Dictionary](https://docs.dynatrace.com/docs/shortlink/semantic-dictionary-global-field-reference#dynatrace-rum-resource-fields).

**Check the agent version distribution for a frontend:**

```dql
fetch user.events, from: now() - 24h
| filter frontend.name == "my-frontend"
| summarize
    event_count = count(),
    by: {dt.rum.agent.type, dt.rum.agent.version}
| sort event_count desc
```

Replace `my-frontend` with the actual frontend name.

### Features by minimum version (GA versions only)

| Agent | Minimum version | Feature / field |
|-------|-----------------|----------------|
| RUM JS | 1.329 | RUM on Grail GA (web) |
| Mobile agent | 8.329 | RUM on Grail GA (mobile) |
| RUM JS | 1.331 | W3C `tracestate` header propagation |
| Mobile agent | 8.333 | W3C Trace Context for frontend-backend linking (Android/iOS) |
| Mobile agent | 8.335 | W3C Trace Context for frontend-backend linking (cross-platform) |

### Deprecated field values

| Field | Old value (RUM JS < 1.339) | Current value (RUM JS ≥ 1.339) |
|-------|-------------------------------------|----------------------------------------|
| `user_action.type` | `xhr` | `same_view` |

Queries filtering on `user_action.type == "same_view"` will miss traffic from agents below 1.339 still reporting `xhr`. Use `in(user_action.type, "same_view", "xhr")` when the fleet is mixed.


## Handling Anomalous Results

When query results seem unexpected or suspicious:

**Unexpected High Values:**
- **Metric spikes**: Verify interval aggregation (avg vs. max vs. sum)
- **Session counts**: Check for bot traffic or synthetic monitoring
- **Error rates**: Confirm error definition matches expectations
- **Performance degradation**: Look for deployment or infrastructure changes

**Unexpected Low Values:**
- **Missing sessions**: Verify `dt.rum.user_type` filter isn't excluding real users — correct value is `"real_user"` (lowercase), not `"REAL_USER"`
- **Low request counts**: Check if frontend filter is too narrow
- **Few errors**: Confirm error characteristics filter is correct
- **Missing mobile data**: Verify platform-specific fields exist

**Inconsistent Data:**
- **Metrics vs. Events mismatch**: Different aggregation methods are expected
- **RUM on the latest Dynatrace vs. RUM Classic mismatch**: RUM on the latest Dynatrace uses a different underlying data model — metrics are not direct equivalents of RUM Classic metrics. Users migrating from RUM Classic may see different numbers; this is by design, not a data gap. Ref: https://docs.dynatrace.com/docs/observe/digital-experience/new-rum-experience/transition-from-rum-classic
- **No limit on user actions per session**: RUM on the latest Dynatrace has no limit on user actions per session, unlike RUM Classic. Sessions with many user actions are not truncated.
- **Geographic anomalies**: Check timezone assumptions
- **Device distribution skew**: May reflect actual user base
- **Version mismatches**: Verify app version filtering logic

## Decision Tree: Ask vs. Investigate

```
Query returns unexpected results
│
├─ Is this a zero-result scenario?
│  ├─ YES → Follow "Handling Zero Results" workflow
│  │        If newly configured → check "Setup-Level Zero Results" first
│  └─ NO → Continue
│
├─ Can I validate the result independently?
│  ├─ YES → Run validation query
│  │        ├─ Validation confirms result → Report findings
│  │        └─ Validation contradicts → Investigate further
│  └─ NO → Continue
│
├─ Is the anomaly clearly explained by data?
│  ├─ YES → Report with explanation
│  └─ NO → Continue
│
├─ Do I need domain knowledge to interpret?
│  ├─ YES → Ask user for context
│  │        Example: "The error rate is 15%. Is this expected for your frontend?"
│  └─ NO → Continue
│
└─ Is the issue ambiguous or requires clarification?
   ├─ YES → Ask specific question with data context
   │        Example: "I see two frontends named 'web-app'. Which frontend name should I use?"
   └─ NO → Investigate and report findings with caveats
```

## Common Investigation Steps

**For Performance Issues:**
1. Compare to baseline: Query same metric for previous week
2. Segment by dimension: Break down by device, browser, geography
3. Check for outliers: Use percentiles (p50, p95, p99) vs. averages
4. Correlate with deployments: Filter by app version or time windows

**For Data Availability Issues:**
1. Start broad: Query all RUM data without filters
2. Add filters incrementally: Isolate which filter eliminates data
3. Check related metrics: If events missing, try timeseries
4. Validate entity relationships: Confirm frontend-backend linking is configured

**For Unexpected Patterns:**
1. Expand timeframe: Look for historical context
2. Cross-reference data sources: Compare events and metrics
3. Check sampling: Verify no sampling is affecting results
4. Consider external factors: Holidays, outages, traffic changes

## Red Flags: When to Stop and Ask

**Always ask the user when:**
- No RUM data exists anywhere in the environment
- Multiple frontends match the user's description
- Results contradict user's stated expectations explicitly
- Data suggests monitoring is misconfigured
- Query requires business context (e.g., "acceptable error rate")
- Timeframe is ambiguous and affects interpretation significantly

**Example clarifying questions:**
- "I found two frontends named 'checkout'. Which one: `checkout-web` or `checkout-mobile`?"
- "The query returns 0 results for the past hour. Should I expand the timeframe, or do you expect real-time data?"
- "The average LCP is 8 seconds, which exceeds the 4-second threshold. Is this frontend known to have performance issues?"
- "I see only synthetic traffic. Should I include `dt.rum.user_type == "real_user"` to focus on real users?"
