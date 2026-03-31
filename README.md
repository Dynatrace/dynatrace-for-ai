# Dynatrace Skills

Agent skills for the [Dynatrace](https://www.dynatrace.com) platform, following the [Agent Skills](https://agentskills.io) open format.

Skills are portable knowledge packages that give AI coding agents domain-specific context for working with Dynatrace. They work with Claude Code, GitHub Copilot, Cursor, OpenCode, Gemini CLI, and [30+ other compatible tools](https://agentskills.io).

> Skills provide **knowledge** (how to query, analyze, and interpret Dynatrace data). For **tool capabilities** (API access, live queries), see the [Dynatrace MCP server](https://github.com/dynatrace-oss/dynatrace-mcp-server) or [Dynatrace CLI](https://github.com/dynatrace-oss/dtctl).

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
# Cross-client convention
cp -r skills/dt-dql-essentials .agents/skills/

# Or client-specific
cp -r skills/dt-dql-essentials .claude/skills/
cp -r skills/dt-dql-essentials .cursor/skills/
```

## Available Skills

### DQL & Query Language

| Skill | Description |
|-------|-------------|
| [dt-dql-essentials](skills/dt-dql-essentials/SKILL.md) | REQUIRED before generating any DQL queries. Provides critical syntax rules, common pitfalls, and patterns. Load this skill BEFORE writing DQL to avoid syntax errors. |

### Observability

| Skill | Description |
|-------|-------------|
| [dt-obs-services](skills/dt-obs-services/SKILL.md) | Service metrics, RED metrics (Rate, Errors, Duration), and runtime-specific telemetry for .NET, Java, Node.js, Python, PHP, and Go applications. |
| [dt-obs-frontends](skills/dt-obs-frontends/SKILL.md) | Real User Monitoring (RUM), Web Vitals, user sessions, mobile crashes, page performance, user interactions, and frontend errors. |
| [dt-obs-tracing](skills/dt-obs-tracing/SKILL.md) | Distributed traces, spans, service dependencies, performance analysis, and failure detection. Query trace data, analyze request flows, and investigate span-level details. |
| [dt-obs-hosts](skills/dt-obs-hosts/SKILL.md) | Host and process metrics including CPU, memory, disk, network, containers, and process-level telemetry. |
| [dt-obs-kubernetes](skills/dt-obs-kubernetes/SKILL.md) | Kubernetes clusters, pods, nodes, workloads, labels, annotations, and resource relationships. Monitor K8s infrastructure and troubleshoot containerized applications. |
| [dt-obs-aws](skills/dt-obs-aws/SKILL.md) | AWS cloud resources including EC2, RDS, Lambda, ECS/EKS, VPC networking, load balancers, databases, serverless, messaging, and cost optimization. |
| [dt-obs-logs](skills/dt-obs-logs/SKILL.md) | Log queries, filtering, pattern analysis, and log correlation. Search and analyze application and infrastructure logs. |
| [dt-obs-problems](skills/dt-obs-problems/SKILL.md) | Problem entities, root cause analysis, impact assessment, and problem correlation. Query and analyze Dynatrace-detected problems and incidents. |
| [dt-obs-extensions](skills/dt-obs-extensions/SKILL.md) | Work with Dynatrace extensions — check extension status and help troubleshoot configuration issues. |

### Dynatrace Apps

| Skill | Description |
|-------|-------------|
| [dt-app-dashboards](skills/dt-app-dashboards/SKILL.md) | Work with Dynatrace dashboards — create, modify, query, and analyze dashboard JSON including tiles, layouts, DQL queries, variables, and visualizations. |
| [dt-app-notebooks](skills/dt-app-notebooks/SKILL.md) | Work with Dynatrace notebooks — create, modify, query, and analyze notebook JSON including sections, DQL queries, visualizations, and analytics workflows. |

### Migration

| Skill | Description |
|-------|-------------|
| [dt-migration](skills/dt-migration/SKILL.md) | Migrate Dynatrace classic and Gen2 entity-based DQL, topology navigation, and classic entity selectors to Smartscape equivalents. |

## How Skills Work

Skills follow the [Agent Skills specification](https://agentskills.io/specification) and use progressive disclosure to minimize context usage:

1. **Catalog** — At startup, agents load only `name` + `description` (~100 tokens per skill) to know what's available.
2. **Instructions** — When a skill is relevant, agents load the full `SKILL.md` (<5000 tokens).
3. **Resources** — Detailed reference files in `references/` are loaded only when needed.

This means you can install all skills without a context penalty — agents only load what they need.

## Relationship to Dynatrace MCP Server

This repo provides **knowledge** (skills). The [Dynatrace MCP server](https://github.com/dynatrace-oss/dynatrace-mcp-server) provides **capabilities** (API tools). They are complementary:

- **Skills** teach agents *how* to think about Dynatrace data — query patterns, best practices, domain knowledge.
- **MCP tools** give agents the *ability* to act — querying Grail, fetching problems, accessing entities.

An agent working on a Dynatrace task might load `dt-dql-essentials` for query syntax rules, then use the MCP server's `query_grail` tool to execute the query.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on creating and improving skills.

## License

Apache-2.0
