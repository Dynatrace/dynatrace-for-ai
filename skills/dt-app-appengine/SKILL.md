---
name: dt-app-appengine
description: >-
  Scaffold, build, and deploy Dynatrace AppEngine apps using the dt-app CLI and dtctl.
  Covers project init, the plan-first build loop, phase-by-phase iteration against a
  customer tenant, and gated deployment. Use this skill when the user wants to create a
  custom Dynatrace App, run `dt-app init/dev/build`, or deploy to a `*.apps.dynatrace.com`
  tenant.
  Trigger: "build a Dynatrace app", "AppEngine app", "dt-app init", "scaffold a Dynatrace
  App", "deploy to dynatrace tenant".
  Do NOT use for: dashboards (use dt-app-dashboards), notebooks (use dt-app-notebooks),
  pure DQL authoring (use dt-dql-essentials), or classic-to-Smartscape migration (use
  dt-migration). For the human-facing ideation-to-spec process that produces the design
  this skill implements, see WORKFLOW.md in this folder.
license: Apache-2.0
---

# Dynatrace AppEngine App Skill

Scaffold, build, and deploy a custom Dynatrace App on AppEngine using the `dt-app` CLI and `dtctl`. This skill assumes a design specification already exists; the upstream ideation, mockup, and spec-writing process is documented in `WORKFLOW.md` in this folder.

## When to use

Use when the user wants to:

- Initialize a new AppEngine project (`dt-app init`)
- Run an app locally against a customer tenant (`dt-app dev`)
- Build and deploy a production bundle (`dt-app build`, `dtctl app deploy`)
- Iterate phase-by-phase against an implementation spec

Skip when:

- The user only wants to write or fix a DQL query → `dt-dql-essentials`
- The user wants to create a dashboard → `dt-app-dashboards`
- The user wants to create a notebook → `dt-app-notebooks`

## Hard rules

1. **Plan before code.** Never generate the full app in one pass. After receiving the spec, summarize current state and propose a file-by-file plan. Wait for explicit user approval before writing implementation code.
2. **One phase at a time.** Implement → verify acceptance criteria → commit → next phase. Do not start phase N+1 before phase N is verified by the user.
3. **Load DQL skills before writing DQL.** Pull `dt-dql-essentials` into context before generating any query. Defer DQL pitfall handling to that skill.
4. **Deploy requires explicit confirmation.** Never run `dtctl app deploy` without the user explicitly authorizing the deploy in the current turn. Authorization in a previous session does not carry over.
5. **Do not invent data.** If a tenant query returns nothing or unexpected results, surface it. Do not substitute placeholder values in a real-data build.

## Pre-flight check

Before scaffolding, run this once and report any failures back to the user:

```bash
node --version      # require >= NodeJS version 24. 


npm --version
dt-app --version
dtctl --version
dtctl auth status
```

If `dt-app` is missing:

```bash
npm install -g @dynatrace-sdk/dt-app
```

If `dtctl` is not authenticated, ask the user to run `dtctl auth login` themselves — it is an interactive flow. Do not try to drive it.

Verify tenant access with a trivial query:

```bash
dtctl dql "fetch dt.davis.problems | limit 1"
```

A non-error response confirms the tenant is reachable.

## The build loop

### 1. Scaffold

```bash
dt-app init
```

After init, connect the project to the user's GitHub repo. The user supplies the remote URL — do not guess one. Then:

```bash
dt-app dev
```

Confirm the dev server loads in the customer tenant browser before continuing. The tenant URL must be `https://<tenantid>.apps.dynatrace.com`, not `.live.dynatrace.com`.

### 2. Propose the plan

Reference the design spec, then produce:

- A file-by-file plan grouped by phase
- Acceptance criteria per phase (lifted from the spec)
- Open questions back to the user

Wait for approval. Do not begin implementation until the plan is approved.

### 3. Implement phase N

- Generate code for the files in phase N only.
- For any tile or view requiring DQL: load `dt-dql-essentials` first.
- After implementation, ask the user to run `dt-app dev` and verify against the phase acceptance criteria. Also ask them to test drill-down and intent behavior if the phase covers them.
- Commit the phase to GitHub before moving on. Use a descriptive message tied to the phase.

### 4. Repeat until all phases pass acceptance.

### 5. Deploy (gated)

Only after the user explicitly authorizes deployment in the current turn:

```bash
dt-app build
dtctl app deploy
git tag v0.1.0 && git push origin v0.1.0
```

Confirm the app is visible and loadable in the customer tenant before declaring the deploy complete.

## Troubleshooting

| Symptom | Likely cause | Action |
| --- | --- | --- |
| MCP "tool not found" in Claude | MCP server not connected | Reconnect via Settings → Connectors; restart client |
| `dt-app dev` won't load in tenant | Wrong tenant URL or session | Confirm `.apps.dynatrace.com` URL; confirm browser is logged in to the same tenant; confirm app permissions match the DQL |
| DQL returns nothing | Wrong time range or field name | Use `describe <entity-type>`; verify `dt.*` prefixes; defer to `dt-dql-essentials` |
| Claude wants to write the whole app | Plan-first rule violated | Stop; restate hard rule #1 and re-propose a plan |
| App looks generic / default Strato | No brand direction supplied | See the brand palette section in `WORKFLOW.md` |
| Many iterations, app still wrong | No spec — drifting | Stop; generate a spec from the current code per `WORKFLOW.md` Step 8, then resume |

For DQL-specific pitfalls (`makeTimeseries` inline math, multi-aggregation `summarize`, span duration units, etc.) defer to `dt-dql-essentials`.

## Companion skills

- `dt-dql-essentials` — required before any DQL is written
- `dt-app-dashboards` — if the app embeds or generates dashboards
- `dt-app-notebooks` — if the app embeds or generates notebooks
- `dt-migration` — if porting from a classic Gen2 entity model

## See also

- `WORKFLOW.md` (this folder) — the 9-step human workflow from ideation to spec
- AppEngine platform docs: https://docs.dynatrace.com/docs/platform/appengine
- Developer portal: https://developer.dynatrace.com/
- dtctl: https://github.com/dynatrace-oss/dtctl
- Dynatrace MCP server: https://docs.dynatrace.com/docs/dynatrace-intelligence/dynatrace-intelligence-integrations/dynatrace-mcp
