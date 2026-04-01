# Dynatrace for AI

Everything AI agents need to work with [Dynatrace](https://www.dynatrace.com), starting with skills.

**Skills** are portable knowledge packages following the [Agent Skills](https://agentskills.io) open format. They give AI coding agents the domain-specific context to query, analyze, and interpret Dynatrace data. They work with Claude Code, GitHub Copilot, Cursor, OpenCode, Gemini CLI, and [30+ other compatible tools](https://agentskills.io).

Skills provide knowledge only. To run live queries and manage your Dynatrace environment, pair them with a tool:

- **[dtctl](https://github.com/dynatrace-oss/dtctl)** — Full CLI for the Dynatrace platform: DQL queries, SLOs, dashboards, workflows, settings, and more. Works in any agent that can run shell commands.
- **[Dynatrace MCP server](https://docs.dynatrace.com/docs/shortlink/dynatrace-mcp-server)** — Official MCP server for Dynatrace API access. Use this if your agent supports MCP natively.

## Installation

### Claude Code

```bash
claude plugin marketplace add dynatrace/dynatrace-for-ai
claude plugin install dynatrace@dynatrace-for-ai
```

Restart Claude Code after installation. Skills activate automatically when relevant.

**Update:**

```bash
claude plugin marketplace update
claude plugin update dynatrace@dynatrace-for-ai
```

### Skills Package (skills.sh)

For agents supporting the [skills.sh](https://skills.sh) ecosystem:

```bash
npx skills add dynatrace/dynatrace-for-ai
```

Works with Claude Code, Cursor, Cline, GitHub Copilot, and other compatible agents.

### Manual Installation

Copy any skill directory into your agent's skills path:

```bash
cp -r skills/dt-dql-essentials .agents/skills/

# Or client-specific
cp -r skills/dt-dql-essentials .claude/skills/
cp -r skills/dt-dql-essentials .cursor/skills/
```

## Skills

### DQL & Query Language

| Skill | Description |
|-------|-------------|
| [dt-dql-essentials](skills/dt-dql-essentials/SKILL.md) | DQL syntax rules, common pitfalls, and query patterns. Load this before writing any DQL. |

### Observability

| Skill | Description |
|-------|-------------|
| [dt-obs-services](skills/dt-obs-services/SKILL.md) | Service RED metrics and runtime telemetry for .NET, Java, Node.js, Python, PHP, and Go. |
| [dt-obs-frontends](skills/dt-obs-frontends/SKILL.md) | Real User Monitoring, Web Vitals, user sessions, mobile crashes, and frontend errors. |
| [dt-obs-tracing](skills/dt-obs-tracing/SKILL.md) | Distributed traces, spans, service dependencies, and failure detection. |
| [dt-obs-hosts](skills/dt-obs-hosts/SKILL.md) | Host and process metrics: CPU, memory, disk, network, and containers. |
| [dt-obs-kubernetes](skills/dt-obs-kubernetes/SKILL.md) | Kubernetes clusters, pods, nodes, workloads, labels, and resource relationships. |
| [dt-obs-aws](skills/dt-obs-aws/SKILL.md) | AWS resources: EC2, RDS, Lambda, ECS/EKS, VPC, load balancers, and cost optimization. |
| [dt-obs-logs](skills/dt-obs-logs/SKILL.md) | Log queries, filtering, pattern analysis, and log correlation. |
| [dt-obs-problems](skills/dt-obs-problems/SKILL.md) | Problem entities, root cause analysis, impact assessment, and problem correlation. |
### Platform

| Skill | Description |
|-------|-------------|
| [dt-app-dashboards](skills/dt-app-dashboards/SKILL.md) | Create, modify, and analyze Dynatrace dashboards: tiles, layouts, variables, and visualizations. |
| [dt-app-notebooks](skills/dt-app-notebooks/SKILL.md) | Create, modify, and analyze Dynatrace notebooks: sections, DQL queries, and analytics workflows. |

### Migration

| Skill | Description |
|-------|-------------|
| [dt-migration](skills/dt-migration/SKILL.md) | Migrate classic entity-based DQL and topology navigation to Smartscape equivalents. |

## Prompts

**Prompts** are reusable task templates for common Dynatrace workflows. Paste them directly into any AI chat, or for VS Code/GitHub Copilot users, copy them into `.github/prompts/` to use as slash commands (e.g. `/troubleshoot-problem`).

Each prompt references the relevant skills above — load those skills first for best results.

| Prompt | Description |
|--------|-------------|
| [daily-standup](prompts/daily-standup.prompt.md) | Generate a daily standup report for one or more services. |
| [health-check](prompts/health-check.prompt.md) | Check the health of a service in production. |
| [incident-response](prompts/incident-response.prompt.md) | Respond to an active production incident with triage, root cause, and a shareable report. |
| [investigate-error](prompts/investigate-error.prompt.md) | Investigate recent errors using Davis Problems as the entry point (problems → logs → traces). |
| [performance-regression](prompts/performance-regression.prompt.md) | Analyze whether a recent deployment caused a performance regression. |
| [troubleshoot-problem](prompts/troubleshoot-problem.prompt.md) | Troubleshoot an existing Dynatrace problem with structured log and trace investigation. |

## How Skills Work

Skills follow the [Agent Skills specification](https://agentskills.io/specification) and use progressive disclosure:

1. **Catalog** - Agents load only `name` + `description` (~100 tokens per skill) to know what's available.
2. **Instructions** - When relevant, the full `SKILL.md` is loaded (<5000 tokens).
3. **Resources** - Detailed reference files in `references/` are loaded on demand.

Install all skills without penalty. Agents only load what they need.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Apache-2.0
