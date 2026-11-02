# Upgrade Overview

## Terminology

- **Classic UI** = gen2 UI (classic screens and menus)
- **Latest UI** = gen3 UI (App shell and React apps on the platform)

No phase is a single UI generation. Even Phase 3 still contains some gen2 screens.

## Upgrade Phases

A phase is a property of an environment, not of a customer. One customer can have environments in different phases.

### Phase 1 -- Hybrid default

Where most existing customers are today. Everything is mixed and nothing has been removed.

- **UI:** hybrid -- gen2 UI alongside gen3 UI (React)
- **Classic apps:** enabled
- **Removed:** nothing

### Phase 2 -- New environments only

More gen3 experience, but still a mix of gen2 UI and gen3 UI.

- **Who gets it:** only environments created from scratch on SaaS 331+. What decides it is the environment being new, not the customer being new -- an existing customer can choose Phase 2 when creating a *new* tenant. A Phase 2 environment cannot come into existence any other way.
- **No in-place upgrade from Phase 1.** There is no UI upgrade path, and existing Phase 1 environments are unchanged by the Phase 2 GA. Switching an existing environment from Phase 1 to Phase 2 is not possible -- only new tenants can be created directly in Phase 2.

**Removed in Phase 2:**

- 32 classic apps, including the Settings Classic app. Its pages remain reachable as an overlay from the new Settings app -- those overlays are gen2 UI.
- 21 APIs
- Management zones and auto-tagging

### Phase 3 -- Ready for opt-in

For customers who agree to opt in to gen2 retirement. Almost pure gen3 UI -- almost, not fully: some gen2 screens remain.

**Opt-in is per environment. Plan every Phase 3 upgrade as permanent.** Do not rely on rollback as a mitigation for an incomplete migration.

**Ways to reach Phase 3:**

- **New customers:** from September 2026, environments start in Phase 3 at creation time.
- **Existing customers in Phase 1 or Phase 2:** after the June 2026 Rally, they can upgrade an environment to Phase 3 at any time.
- **Existing customers** can also create new tenants directly in Phase 3.

**Removed in Phase 3** (cumulative, counting what Phase 2 already removed):

- 50 apps total
- 45 APIs
- API tokens
- Entity IDs
- Management zones and auto-tagging
- All remaining classic concepts
- Classic extraction rules stop running; only OpenPipeline rules run

A Phase 2 environment upgrading to Phase 3 loses a further **18 apps, 24 APIs**, entity IDs, and all remaining classic concepts on top of what Phase 2 already removed.

Management zones and auto-tagging appear in both lists because there are two paths to losing them: a new customer starting in Phase 2 never has them, and any environment upgrading to Phase 3 loses them at that point.

## Data Types for Readiness Assessment

When evaluating upgrade readiness, tracking data falls into these categories:

- **Classic Usage** -- Tracks individual usage events of legacy features. Examples: dashboard views, classic API calls, USQL queries. Helps quantify how much a tenant depends on classic features.
- **Classic Configuration** -- Lists classic config objects that may need migration. Examples: management zone definitions, metric event alert rules, classic SLO definitions. Helps identify the migration workload.
- **Readiness Status** -- Per-item pass/fail compatibility check for Phase 3. Examples: OneAgent version >= 1.337, ActiveGate version >= 1.327. Helps determine blockers.
- **New Usage** -- Tracks adoption of gen3 replacements. Examples: new dashboard views, OpenPipeline processed events, gen3 SLO definitions. Helps measure migration progress.

## General Prerequisites

Before starting the upgrade assessment:

1. Establish which phase the environment is in today -- it determines what is already gone and what the upgrade will remove
2. Identify which upgrade areas are relevant to the tenant (not all tenants use all features)
3. Ensure you have appropriate permissions to run DQL queries and read settings
4. Plan the assessment area by area -- each area has its own tracking queries and migration actions
5. Prioritize blockers: anything an environment depends on that Phase 3 removes must be migrated before the opt-in, because the opt-in is permanent

## Upgrade Areas

The upgrade items are organized by team ownership:

1. **Platform** -- Dashboards, entity queries, IAM, management zones, autotagging, alerting, settings
2. **Edge Data Platform** -- OpenPipeline, extensions, cloud integrations, ActiveGate
3. **Application Observability** -- SLOs, logs, service detection, request attributes, calculated metrics, services
4. **Infrastructure Observability** -- Disk alerts, VMware, K8s, databases, network, OneAgent, naming rules
5. **Cloud Automations** -- Releases, config-as-code, SRG
6. **Application Security** -- Vulnerability monitoring
7. **Digital Experience** -- Web/mobile RUM, sessions, synthetic, properties, privacy, alerting, actions
