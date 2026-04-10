---
agent: agent
description: Investigate recent errors in a service using Davis Problems as the starting point (problems → logs → traces).
argument-hint: Optional specific service or timeframe for the investigation
---

Investigate recent errors in my service using Dynatrace Davis Problems as the entry point.
Infer service-name from the current workspace. Ask user to confirm, or provide a specific timeframe/entity scope if unsure.

1. Use root_cause_agent to identify relevant Davis Problems for the service and obtain their timeframe and affected entities.
2. For each selected problem, use the problem's timeframe and entities to:
   - Search for ERROR level logs scoped to that context
   - Group results by error message/type
3. For the top 3 most frequent errors per problem:
   - Show example log entries
   - Find related distributed traces
   - Identify which code is responsible
   - Confirm and summarize the associated Davis Problem (if any)
4. Suggest root cause and remediation steps based on the combined problem, log, and trace analysis.

Use Dynatrace to gather all data.
