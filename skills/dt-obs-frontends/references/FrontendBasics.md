# Frontend Observability & RUM

DQL query patterns for monitoring Real User Monitoring (RUM) data and frontend application performance.

## Overview

Frontend observability combines two data sources:

- **Metric-Based**: `timeseries` with `dt.frontend.*` metrics for trends, dashboards, and alerting
- **Event-Based**: `fetch user.events` for detailed diagnostics and root cause analysis

## Quick Reference

**Common Filters:**

- `frontend.name` - Filter by application
- `geo.country.iso_code` - Geographic filtering
- `device.type` - Mobile, desktop, tablet
- `browser.name` - Browser filtering
- `dt.rum.user_type` - Exclude synthetic monitoring

**Time Ranges:**

- Real-time: 15m-1h | Daily: 12h-24h | Trends: 7d-30d | Capacity planning: 30d-90d

**Key Metrics:**

- `dt.frontend.request.count` - Request volume
- `dt.frontend.request.duration` - Request latency (ms)
- `dt.frontend.error.count` - Error counts
- `dt.frontend.session.active.estimated_count` - Active sessions
- `dt.frontend.user.active.estimated_count` - Unique users

## Best Practices

1. **Use metrics for trends**, events for debugging
2. **Filter by application** in multi-app environments
3. **Match interval to time range** (5m for hours, 1h for days)
4. **Exclude synthetic traffic** when analyzing real users
5. **Combine metrics with events** for complete insights
