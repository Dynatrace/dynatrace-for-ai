---
description: Generate a daily standup report for one or more services.
---
Generate a daily standup report for my services.
If no specific services are provided, infer from current workspace and ask user to confirm.

For each service:
1. Health status (healthy/degraded/critical)
2. Fetch and compare key metrics (response time, errors, throughput) from today vs yesterday
3. Any incidents or problems in last 24 hours
4. Recent deployments and their impact
5. Action items if any issues detected

Format as concise bullet points I can share with my team.
Use Dynatrace to gather all metrics.
