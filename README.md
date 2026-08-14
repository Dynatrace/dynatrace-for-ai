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

The plugin includes the Dynatrace MCP server. Set these environment variables before starting Claude Code to connect it to your environment:

```bash
export DT_ENVIRONMENT=https://<env>.apps.dynatrace.com   # e.g. https://abc12345.apps.dynatrace.com
export DT_PLATFORM_TOKEN=<your-platform-token>
```

Please consult the [Dynatrace MCP server docs
](https://docs.dynatrace.com/docs/shortlink/dynatrace-mcp-server) for a full list of scopes required for using the MCP Server with a Platform Token.

Update with `claude plugin marketplace update && claude plugin update dynatrace@dynatrace-for-ai`.

The bundled MCP server connects to your Dynatrace environment. See the [Dynatrace Privacy Policy](https://www.dynatrace.com/company/trust-center/privacy/) for details on data handling.

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

The **[Dynatrace MCP server](https://docs.dynatrace.com/docs/shortlink/dynatrace-mcp-server)** provides Dynatrace API access via MCP. The Claude Code plugin bundles the MCP server configuration automatically — just set `DT_ENVIRONMENT` and `DT_PLATFORM_TOKEN` as shown above. For other agents that support MCP natively, see the [MCP server docs](https://docs.dynatrace.com/docs/shortlink/dynatrace-mcp-server).

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
| [dt-obs-azure](skills/dt-obs-azure/SKILL.md) | Azure resources: VMs, VMSS, SQL Database, Storage, AKS, App Service, Functions, VNet, Event Hubs, Container Apps, and Key Vault. |
| [dt-obs-gcp](skills/dt-obs-gcp/SKILL.md) | GCP resources: Compute Engine, GKE, Cloud Run, Pub/Sub, VPC, DNS, IAM, and Secret Manager. |
| [dt-obs-logs](skills/dt-obs-logs/SKILL.md) | Log queries, filtering, pattern analysis, and log correlation. |
| [dt-obs-problems](skills/dt-obs-problems/SKILL.md) | Problem entities, root cause analysis, impact assessment, and problem correlation. |
| [dt-obs-predictive-analytics](skills/dt-obs-predictive-analytics/SKILL.md) | Time series forecasting, capacity saturation planning, and trend/anomaly detection across hosts, services, and infrastructure. |
| [dt-alerting](skills/dt-alerting/SKILL.md) | End-to-end alerting lifecycle: anomaly detector setup, alert events in Grail, problem grouping, and workflow notification routing. |
| [dt-obs-analytics](skills/dt-obs-analytics/SKILL.md) | Analyze Dynatrace dashboards and notebooks with Davis analyzers: anomaly detection, novelty scoring, and metric correlation. |
| [dt-obs-ext-monitors](skills/dt-obs-ext-monitors/SKILL.md) | Ingest third-party test and monitor results into Dynatrace Grail via the platform events ingest API. |
| [dt-obs-genai](skills/dt-obs-genai/SKILL.md) | Analyze observability signals from GenAI applications: golden signals, LLM cost/token analytics, agent tool-call behavior, and evaluation results. |
| [dt-obs-log-semantic-mapping](skills/dt-obs-log-semantic-mapping/SKILL.md) | Suggest and validate semantic dictionary mappings for audit log integrations, using vendor log payloads or live ingested events. |

### Security

| Skill | Description |
|-------|-------------|
| [dt-sec-insights](skills/dt-sec-insights/SKILL.md) | Query and analyze security data in `security.events`: Runtime Vulnerability Analytics, Runtime Application Protection, Automated Detections (MITRE ATT&CK), and Security Posture Management (KSPM/CSPM). |
| [dt-sec-contextualization](skills/dt-sec-contextualization/SKILL.md) | Resolve security signals and IoC matches to runtime entities, and connect findings across topology levels through a shared runtime entity. |
| [dt-sec-ioc-hunting](skills/dt-sec-ioc-hunting/SKILL.md) | Hunt threat-intelligence indicators of compromise across logs and spans, producing a threat-exposure score. |
| [dt-sec-semantic-mapping](skills/dt-sec-semantic-mapping/SKILL.md) | Suggest and validate semantic dictionary mappings for new security integrations, using vendor API samples or live events. |

### Mobile Instrumentation

| Skill | Description |
|-------|-------------|
| [dt-obs-android](skills/dt-obs-android/SKILL.md) | Instrument an existing Android project (Kotlin or Java) with the Dynatrace Mobile Agent: Gradle plugin, agent config, and user privacy opt-in. |
| [dt-obs-flutter](skills/dt-obs-flutter/SKILL.md) | Integrate the Dynatrace Flutter Plugin: dependency setup, config, SDK bootstrap, navigation tracking, and verification. |
| [dt-obs-ios](skills/dt-obs-ios/SKILL.md) | Set up the Dynatrace iOS SDK via Swift Package Manager: SPM dependency, Dynatrace.plist config, privacy opt-in, and Xcode build verification. |
| [dt-obs-react-native](skills/dt-obs-react-native/SKILL.md) | Integrate the Dynatrace React Native Plugin for bare React Native and Expo: dependency setup, dynatrace.config.js, Babel registration, navigation tracking, and verification. |

### Platform

| Skill | Description |
|-------|-------------|
| [dt-app-dashboards](skills/dt-app-dashboards/SKILL.md) | Create, modify, and analyze Dynatrace dashboards: tiles, layouts, variables, and visualizations. |
| [dt-app-notebooks](skills/dt-app-notebooks/SKILL.md) | Create, modify, and analyze Dynatrace notebooks: sections, DQL queries, and analytics workflows. |
| [dt-js-runtime](skills/dt-js-runtime/SKILL.md) | Dynatrace server-side JavaScript runtime: function contract, runtime limits, Web APIs, Node.js modules, and the `@dynatrace-sdk/*` catalog. |
| [dt-platform-costs](skills/dt-platform-costs/SKILL.md) | Query and analyze a Dynatrace tenant's actual billing and usage data with DQL: DPS consumption breakdown, cost-normalized spend ranking, chargeback/showback, cost drivers, and entity-level cost drill-down. |

### Migration

| Skill | Description |
|-------|-------------|
| [dt-migration](skills/dt-migration/SKILL.md) | Migrate classic entity-based DQL and topology navigation to Smartscape equivalents. |

## Prompts

**Prompts** are reusable task templates for common Dynatrace workflows. You can copy them from the `/prompts/` directory and paste them directly into any AI chat. For VS Code/GitHub Copilot users, copy prompts into `.github/prompts/` to use as slash commands (e.g. `/troubleshoot-problem`).

Each prompt references the relevant skills above — load those skills first for best results.

| Prompt | Description |
|--------|-------------|
| [dt-daily-standup](prompts/dt-daily-standup.prompt.md) | Generate a daily standup report for one or more services. |
| [dt-health-check](prompts/dt-health-check.prompt.md) | Check the health of a service in production. |
| [dt-incident-response](prompts/dt-incident-response.prompt.md) | Respond to an active production incident with triage, root cause, and a shareable report. |
| [dt-investigate-error](prompts/dt-investigate-error.prompt.md) | Investigate recent errors using Davis Problems as the entry point (problems → logs → traces). |
| [dt-performance-regression](prompts/dt-performance-regression.prompt.md) | Analyze whether a recent deployment caused a performance regression. |
| [dt-troubleshoot-problem](prompts/dt-troubleshoot-problem.prompt.md) | Troubleshoot an existing Dynatrace problem with structured log and trace investigation. |

## How Skills Work

Skills follow the [Agent Skills specification](https://agentskills.io/specification) and use progressive disclosure:

1. **Catalog** - Agents load only `name` + `description` (~100 tokens per skill) to know what's available.
2. **Instructions** - When relevant, the full `SKILL.md` is loaded (<5000 tokens).
3. **Resources** - Detailed reference files in `references/` are loaded on demand.

Install all skills without penalty. Agents only load what they need.

## Contributing

Skill content (`skills/`) is maintained internally at Dynatrace and published here periodically. **PRs that modify skill files will not be accepted** — please [open an issue](../../issues/new) instead to suggest changes. See [CONTRIBUTING.md](CONTRIBUTING.md) for details on what can be contributed directly.

## License

Apache-2.0
