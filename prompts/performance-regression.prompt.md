---
description: Analyze whether a recent deployment caused a performance regression.
---
My recent deployment to [service-name] might have caused a slowdown.
Infer service-name from current workspace if not provided. Ask user to confirm if not sure.

1. Compare metrics before and after latest deployment
2. Identify which endpoints got slower
3. Get distributed traces for slow requests (>2s)
4. Find which code changes correlate with slowdown
5. Check if there's a Davis Problem with root cause
6. Suggest specific optimization steps

Use Dynatrace to get production data and provide actionable recommendations.

---

**Related skills:** dt-dql-essentials, dt-obs-services, dt-obs-tracing
