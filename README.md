# Dynatrace for AI

Everything AI agents need to work with [Dynatrace](https://www.dynatrace.com), starting with skills.

**Skills** are portable knowledge packages following the [Agent Skills](https://agentskills.io) open format. They give AI coding agents the domain-specific context to query, analyze, and interpret Dynatrace data. They work with Claude Code, GitHub Copilot, Cursor, OpenCode, Gemini CLI, and [30+ other compatible tools](https://agentskills.io).

## Installation

### Skills Package (skills.sh)

```bash
npx skills add dynatrace/dynatrace-for-ai
```

Works with Claude Code, Cursor, Cline, GitHub Copilot, OpenCode, and other [compatible agents](https://agentskills.io).

### Claude Code Plugin

```bash
claude plugin marketplace add dynatrace/dynatrace-for-ai
claude plugin install dynatrace@dynatrace-for-ai
```

Update with `claude plugin marketplace update && claude plugin update dynatrace@dynatrace-for-ai`.

### Manual

Copy skill directories into your agent's skills path (`.agents/skills/`, `.claude/skills/`, `.cursor/skills/`, etc.).

## Connecting to Dynatrace

Skills provide knowledge only. To run live queries and manage your environment, pair them with a tool.

### Dynatrace CLI (dtctl)

**[dtctl](https://github.com/dynatrace-oss/dtctl)** is a kubectl-style CLI for the Dynatrace platform. It ships with its own [Agent Skill](https://github.com/dynatrace-oss/dtctl/tree/main/skills/dtctl) that teaches agents how to operate it.

```bash
brew install dynatrace-oss/tap/dtctl                        # Install
dtctl auth login --context my-env \
  --environment "https://<env>.apps.dynatrace.com"           # Authenticate
npx skills add dynatrace-oss/dtctl                           # Install the dtctl skill
dtctl doctor                                                 # Verify setup
```

Or install the dtctl skill with dtctl itself: `dtctl skills install`

### Dynatrace MCP Server

The **[Dynatrace MCP server](https://docs.dynatrace.com/docs/shortlink/dynatrace-mcp-server)** provides Dynatrace API access via MCP. Use this if your agent supports MCP natively.

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

**Prompts** are reusable task templates for common Dynatrace workflows. You can copy them from the `/prompts/` directory and paste them directly into any AI chat. For VS Code/GitHub Copilot users, copy prompts into `.github/prompts/` to use as slash commands (e.g. `/troubleshoot-problem`).

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
