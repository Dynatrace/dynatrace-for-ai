# Core Web Vitals

Monitor Core Web Vitals and frontend performance metrics. These metrics directly impact SEO rankings and user experience.

**Data Source:** `fetch user.events` with `web_vitals.*` fields

**Google's Core Web Vitals Thresholds:**

- **LCP (Largest Contentful Paint)**: Good < 2.5s | Needs Improvement 2.5-4.0s | Poor > 4.0s (field: `web_vitals.largest_contentful_paint`, duration in nanoseconds)
- **INP (Interaction to Next Paint)**: Good < 200ms | Needs Improvement 200-500ms | Poor > 500ms (field: `web_vitals.interaction_to_next_paint`, duration in nanoseconds)
- **CLS (Cumulative Layout Shift)**: Good < 0.1 | Needs Improvement 0.1-0.25 | Poor > 0.25 (field: `web_vitals.cumulative_layout_shift`, double)
- **FID (First Input Delay)** *(deprecated, replaced by INP)*: Good < 100ms | Needs Improvement 100-300ms | Poor > 300ms (field: `web_vitals.first_input_delay`, duration in nanoseconds)

**Metric-Based Queries:** For timeseries dashboards and alerting, use `dt.frontend.web.page.*` metrics:

- `dt.frontend.web.page.largest_contentful_paint`
- `dt.frontend.web.page.interaction_to_next_paint`
- `dt.frontend.web.page.cumulative_layout_shift`
- `dt.frontend.web.page.first_input_delay`

**Alerting:** Critical if p75 values fall into "poor" range for more than 1 hour

## All Core Web Vitals

Query all web vitals (including INP which replaces FID):

```dql
fetch user.events, from: now() - 2h
| filter isNotNull(web_vitals.largest_contentful_paint) or isNotNull(web_vitals.interaction_to_next_paint) or isNotNull(web_vitals.cumulative_layout_shift)
| summarize
    lcp_p75 = percentile(web_vitals.largest_contentful_paint, 75),
    inp_p75 = percentile(web_vitals.interaction_to_next_paint, 75),
    cls_p75 = percentile(web_vitals.cumulative_layout_shift, 75),
    by: {frontend.name}

```

## Largest Contentful Paint (LCP)

Monitor LCP performance:

```dql
fetch user.events, from: now() - 2h
| filter isNotNull(web_vitals.largest_contentful_paint)
| summarize
    p50_lcp = percentile(web_vitals.largest_contentful_paint, 50),
    p75_lcp = percentile(web_vitals.largest_contentful_paint, 75),
    p90_lcp = percentile(web_vitals.largest_contentful_paint, 90),
    by: {frontend.name}
| fieldsAdd
    lcp_rating = if(
        p75_lcp < 2500ms,
        "good",
        else: if(
            p75_lcp < 4s,
            "needs_improvement",
            else: "poor"
        )
    )

```

## First Input Delay (FID)

> **Note:** FID is deprecated and replaced by INP (Interaction to Next Paint) as of March 2024. Consider using INP for new implementations.

Monitor interactivity (legacy):

```dql
fetch user.events, from: now() - 2h
| filter isNotNull(web_vitals.first_input_delay)
| summarize
    p75_fid = percentile(web_vitals.first_input_delay, 75),
    p95_fid = percentile(web_vitals.first_input_delay, 95),
    by: {frontend.name}
| fieldsAdd
    fid_rating = if(
        p75_fid < 1s,
        "good",
        else: if(
            p75_fid < 3s,
            "needs_improvement",
            else: "poor"
        )
    )

```

## Interaction to Next Paint (INP)

Monitor responsiveness (replaces FID):

```dql
fetch user.events, from: now() - 2h
| filter isNotNull(web_vitals.interaction_to_next_paint)
| summarize
    p75_inp = percentile(web_vitals.interaction_to_next_paint, 75),
    p95_inp = percentile(web_vitals.interaction_to_next_paint, 95),
    by: {frontend.name}
| fieldsAdd
    inp_rating = if(
        p75_inp < 2s,
        "good",
        else: if(
            p75_inp < 5s,
            "needs_improvement",
            else: "poor"
        )
    )

```

## Cumulative Layout Shift (CLS)

Monitor visual stability:

```dql
fetch user.events, from: now() - 2h
| filter isNotNull(web_vitals.cumulative_layout_shift)
| summarize
    p75_cls = percentile(web_vitals.cumulative_layout_shift, 75),
    by: {frontend.name}
| fieldsAdd
    cls_rating = if(
        p75_cls < 0.1,
        "good",
        else: if(
            p75_cls < 0.25,
            "needs_improvement",
            else: "poor"
        )
    )

```

## Web Vitals Trends

Monitor trends over time:

```dql
fetch user.events, from: now() - 2h
| filter isNotNull(web_vitals.largest_contentful_paint)
| summarize
    p75_lcp = percentile(web_vitals.largest_contentful_paint, 75),
    by: {time_bucket = bin(start_time, 1h)}
| sort time_bucket asc

```

## Web Vitals by Page

Analyze per-page performance:

```dql
fetch user.events, from: now() - 2h
| filter isNotNull(web_vitals.largest_contentful_paint)
| summarize
    page_views = count(),
    p75_lcp = percentile(web_vitals.largest_contentful_paint, 75),
    by: {page.url}
| filter page_views > 100
| sort p75_lcp desc
| limit 20

```

## Web Vitals by Device

Compare performance across devices:

```dql
fetch user.events, from: now() - 2h
| filter isNotNull(web_vitals.largest_contentful_paint)
| summarize
    p75_lcp = percentile(web_vitals.largest_contentful_paint, 75),
    p75_inp = percentile(web_vitals.interaction_to_next_paint, 75),
    p75_cls = percentile(web_vitals.cumulative_layout_shift, 75),
    by: {device.type}

```

