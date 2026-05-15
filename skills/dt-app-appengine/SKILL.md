# AppEngine  Development Skill


| Name | Description | License |
|---|---|---|
| dt-app-appengine | Skill for building AppEngine for the Dynatrace Platform apps using the dt-app CLI and Claude Code, from ideation to deployment. | Apache-2.0 


Create and Improve AppEngine application for the Dynatrace SaaS Platform 

Skill to compliment the Dynatrace Platform 

Dynatrace Solutions Engineers and Customer Success Engineers for building a custom Dynatrace App for a customer or internal use.

It assumes you have not yet run dt-app dev before, but already know Dynatrace and can read DQL. You have a tenant you can develop against and want a polished, customer-presentable app rather than a throwaway prototype.

## What This Skill Covers

- Creating and Running an AppEngine application on the Dynatrace SaaS Platform
- Building a simple AppEngine application that can execute DQL queries and display results

## Prerequisites

Most friction in this workflow comes from skipped setup and authentication issues. Complete all prerequisites now so the later steps stay focused on the app, not the environment.

### 1. A Dynatrace Tenant You Can Develop Against

**Tenant endpoint:** You need a SaaS tenant URL of the form `https://tenantid.apps.dynatrace.com`. This is the AppEngine endpoint, not the classic `.live.dynatrace.com` URL. Confirm you can log in to the Apps UI before continuing.

**Recommended usage:** For customer work, use a customer sandbox or non-prod tenant if one exists. If you are developing for a production tenant directly, get written approval from the customer first.

### 2. Node.js and npm

Install Node.js LTS (20.x or newer). Verify the installation with:

```bash
node --version
npm --version
```

### 3. dtctl: The Dynatrace Observability CLI

**What it is for:** `dtctl` is the official Dynatrace CLI built for both humans and AI agents. You will use it for querying, deploying, and managing your app from the command line.

- Blog: https://www.dynatrace.com/news/blog/dtctl-the-dynatrace-observability-cli-thats-built-for-ai-agents-and-humans/
- GitHub: https://github.com/dynatrace-oss/dtctl

Install following the GitHub README, then authenticate against your tenant:

```bash
dtctl auth login
```

Verify with a simple DQL query:

```bash
dtctl dql "fetch dt.davis.problems | limit 5"
```

If that returns rows, you are good.

### 4. Dynatrace MCP Server

The Dynatrace MCP (Model Context Protocol) server is what lets Claude talk to your tenant. This is the **single most important prerequisite** for this whole workflow.

- Docs: https://docs.dynatrace.com/docs/dynatrace-intelligence/dynatrace-intelligence-integrations/dynatrace-mcp#connect-to-the-mcp-server
- Hub listing: https://www.dynatrace.com/hub/detail/dynatrace-mcp-server/

Follow the connection instructions for both clients:

- **Claude client:** connect the MCP server through Settings and Connectors, then provide the tenant URL and OAuth token or use the OAuth flow if supported.
- **Claude Code:** configure the MCP server in your Claude Code MCP settings using the same tenant context.

**Validate the connection** by asking Claude in either client:

> "Use the Dynatrace MCP to fetch the last 5 problems from my tenant."

If it returns real data, you are wired up.

### 5. Dynatrace for AI Skills

A growing library of agentic skills (DQL essentials, dashboard generation patterns, brand assets, lessons learned) maintained by Dynatrace.

Repo: https://github.com/Dynatrace/dynatrace-for-ai

Clone it locally. You will point Claude Code at specific skill files during the build, particularly the DQL ones, which prevent common rookie mistakes.

### 6. Dynatrace AppEngine and the dt-app CLI

AppEngine is the framework for building custom Dynatrace apps. The `dt-app` CLI scaffolds, runs, and deploys them.

- Blog: https://www.dynatrace.com/news/blog/appengine-custom-apps-for-data-insights/
- Platform docs: https://docs.dynatrace.com/docs/platform/appengine
- Developer portal: https://developer.dynatrace.com/

Install the CLI globally, then verify:

```bash
npm install -g @dynatrace-sdk/dt-app
dt-app --version
```

### 7. Claude Access

You need both of the following:

- **Claude client:** use it for ideation, visual mockups, and specification writing. Sonnet handles most work well; switch to Opus only when you need deeper reasoning.
- **Claude Code:** use it in the terminal for real implementation against the customer tenant.

### 8. A GitHub Repo

Create an empty private repo for your app. You will connect your local app folder to it during scaffolding. Customer apps should live in customer-specific repos with appropriate access controls.

### 9. Dynatrace Brand Assets (Optional but Recommended)

If your app will be customer-facing or demoed in front of leadership, ground the visual design in real Dynatrace brand colors and typography rather than letting Claude guess.

Brand portal: https://dynatrace.sharepoint.com/sites/MarketingComms/SiteAssets

You can paste these primary brand colors directly into your prompts:

| Palette | Hex Values |
|---------|-----------|
| Blues | `#1C5BE5` `#4635D6` `#1497FF` `#54C8E9` |
| Purples | `#B23BE4` `#6C3AD6` `#6F2EA8` |
| Greens | `#BDDF28` `#73BE28` |
| Pink | `#E436FF` |

Telling Claude to use these from step 1 produces a modern React-style UI rather than the default Strato look.

---

## The Process at a Glance

The full workflow has nine steps. Steps 1 through 8 happen in the Claude client. Step 9 happens in Claude Code in the terminal.

| Step | Surface | Activity |
|------|---------|----------|
| 1 | Claude client | First-pass ideation and rough scope |
| 2 | Claude client | Re-ideate and pressure-test the idea |
| 3 | Claude client | Build the 80% design prompt |
| 4 | Claude client | Create the visual mockup with placeholder data |
| 5 | Claude client | Refine the mockup |
| 6 | Claude client | Wire the mockup to real customer data via Dynatrace MCP |
| 7 | Claude client | Tweak the design to 90–95% completion |
| 8 | Claude client | Generate the complete design specification |
| 9 | Claude Code | Scaffold, build, and deploy the real app |

---

## Step 01 — Ideate with Claude (First Pass)

**How to start the conversation:** Open a new chat in the Claude client. Start with Sonnet. State the problem you are trying to solve, not the app you think you want to build.

| Less effective | More effective |
|---|---|
| "I want to build a dashboard for cascade risk." | "Our customer's TechOps team cannot see when one application's failure is about to take down five others, and they are reacting instead of getting ahead." |

**What to include in the prompt:** Name the customer, the problem, the current workaround, the data sources you know about, and what you want Claude to help you think through — the most valuable angles, the primary user per angle, the data sources needed, and the killer view.

**How to evaluate the options:** Let Claude propose three or four directions. Do not commit yet. Push back on weak ones. Ask "what would this look like for a managing director vs an SRE?" if the audience is unclear.

**When to switch models:** Switch to Opus if Sonnet is producing generic ideas that could apply to any customer, and you suspect there is a sharper angle you have not surfaced.

✅ **Done when:** You have one direction picked, and you can write a single sentence describing what the app is for and who it is for.

---

## Step 02 — Re-Ideate with Claude

**Why a second chat matters:** Start a fresh chat. The first chat has accumulated meandering context. The second chat gets the polished version of the idea.

**How to pressure-test the idea:** Paste your one-sentence app description from step 1 and ask Claude to pressure-test it. Ask for the strongest version, the weakest assumption, and the one thing that, if you get it wrong, makes the whole app useless to the user.

**Why this step saves time:** This step catches the failure mode where step 1 produced an idea that sounded good but does not survive contact with reality. If Claude finds a hole, fix the idea. If it does not, move on.

✅ **Done when:** You have a refined one-paragraph description of the app, with named users, named decisions, and named data sources.

---

## Step 03 — Provide an 80% Complete Design Prompt

This is the prompt that produces your first visual mockup. Spend real time on it. The quality of everything downstream is set here.

**Prompt structure:** Include these sections:

- **Context:** who the customer is, what the app is for, who the primary users are, and what decisions the app helps them make.
- **Scope:** the number of tabs or views, what each one is for, the data sources involved, drill-down behavior, and refresh cadence expectations.
- **Visual direction:** theme, brand colors, tone, density, and design inspiration.
- **Out of scope:** features you do not want Claude to design yet.
- **Task:** build a non-functional visual mockup as an HTML artifact using realistic placeholder data, with emphasis on layout, information density, and visual hierarchy.

✅ **Done when:** You have submitted the prompt and Claude is producing an artifact.

---

## Step 04 — Visual Mockup in the Claude Client

Claude will render an HTML artifact in the right pane. Look at it for a full minute before you react. Ask yourself:

- Does the information hierarchy match the user's decision flow? What the user needs first should be biggest and topmost.
- Is the density right? Too sparse means the user will scroll for everything. Too dense means they cannot find anything.
- Does it look like a product, or does it look like a wireframe?

Take a screenshot. Save it. You will compare future iterations against this one.

✅ **Done when:** You have a mockup that is at least 70% of what you want.

---

## Step 05 — Refine the Design and Re-Render

Iterate with restraint at this stage. Avoid over-refining a mockup that will change once real data is added.

**Productive refinements now:** re-arranging major sections, adding or removing whole views, changing the visual approach, establishing patterns.

**Ignore for now:** specific tile copy, exact color shades, spacing tweaks, icon choices. Bank those for step 7.

✅ **Done when:** The structure is right and the visual direction is locked, even if the data is fake and the polish is rough.

---

## Step 06 — Wire the Mockup to Real Customer Data

This is where the mockup becomes useful. You will ask Claude to query the customer tenant via the Dynatrace MCP, then update the mockup with real data and real DQL.

**Prepare before you prompt:**

- **Guardrails on data sources:** tell Claude exactly which data sources are in scope and which are not.
- **Example dashboards:** provide existing JSON exports and screenshots when available so Claude can pattern-match.
- **Specific locator hints:** name the workload, service, problem ID, application CI, or other entity that should anchor the queries.
- **Expected data shape:** describe the ranges or patterns you expect so Claude can detect when query output is clearly wrong.

**Prompting pattern:**

```
Use the Dynatrace MCP connected to [tenant URL] to query real data for this mockup.
Follow the guardrails.
Write the DQL query that produces each tile's data.
Execute the query.
Update the mockup with real returned values.
Show both the DQL and the values.
Stop if a query returns nothing or unexpected results — do not invent placeholder data.
```

Claude will iterate. Expect 5 to 15 MCP tool calls per mockup tile. When it finishes, you have a mockup that is visually styled the way you want and powered by real data. The DQL queries it produced are reusable in step 8.

✅ **Done when:** Every tile in the mockup shows real numbers from the customer tenant, and you have the DQL for each one captured in the chat.

---

## Step 07 — Tweak to 90–95% of Your Liking

Refine tile copy, color accents, callout boxes, badge styling, chip styling, section headers, empty states, hover behavior, and stat-bar numbers.

> **Important:** Stop at about 95% complete. The last layer of polish belongs in the real app build with real components. Any visual polish you do in the HTML mockup gets thrown away anyway.

✅ **Done when:** You would be comfortable showing this mockup to the customer as a "here is what we are going to build" reference.

---

## Step 08 — Generate the Complete Design Specification

This is the most valuable artifact in the entire process. The spec is what makes the difference between a 30-iteration messy build and a 5-to-15-iteration clean build in step 9.

**Write the specification:** Keep Claude in the same chat so it retains the full design and data context. Ask for a complete implementation-ready specification for Claude Code. Require the spec to define:

- AppEngine structure, permissions, and intents
- Routing and reusable React components
- Global filters and their DQL impact
- DQL per tile with real field names (not pseudocode)
- Drill-down behavior and AppEngine intent contracts
- Build phases with acceptance criteria
- Known limitations and future work

**Review the specification critically.** Push back on anything vague. For example:

> "Section 7.4 is too abstract — expand it with the tile-by-tile breakdown including DQL."

Iterate until the spec is something you would be proud to hand to a colleague.

✅ **Done when:** The spec is comprehensive enough that someone who was not in this chat could read it and know exactly what to build.

---

## Step 09 — Scaffold, Build, and Deploy with Claude Code

Now you switch surfaces. Open your terminal. Open Claude Code. Have your spec from step 8 ready to paste.

### 9a. Scaffold the App

Bootstrap the project and verify the dev server runs:

```bash
dt-app init
dt-app dev
```

Set up a clean versioning workflow before heavy iteration begins. Connect the project to your GitHub repo.

**Force a plan-first workflow** by pasting the complete spec, then adding:

```
Before you write any code, summarize the current state and propose a
file-by-file plan for me to approve before you start implementing.
```

> **Why this matters:** Without the plan-first instruction, Claude Code will sometimes generate the whole app in one pass. If its mental model diverges from yours, you have to throw it all out. The plan-first pattern is cheap insurance.

### 9b. Approve the Plan

Read the plan. Push back on anything that looks wrong. Ask for justifications where the plan is non-obvious. When the plan is right, tell Claude Code to proceed with Phase 1.

### 9c. Iterate Phase by Phase

Have Claude Code implement one phase at a time. After each phase:

```bash
dt-app dev
```

- Load the app in the customer tenant
- Check the phase acceptance criteria
- Test drill-down and intent behavior
- Commit to GitHub before moving to the next phase

**Load the right DQL skills early.** Pull `dt-dql-essentials` and `dt-dql-lessons-learned` from the Dynatrace for AI Skills repo into the Claude Code context before any DQL gets written. The lessons-learned file catches common errors:

- Inline math inside `makeTimeseries` aggregation parameters
- Missing curly braces on multi-aggregation `summarize`
- Span duration unit confusion (nanoseconds vs microseconds)

### 9d. Deploy to the Customer Tenant

```bash
# Build the production bundle
dt-app build

# Upload via dtctl
dtctl app deploy

# Tag the GitHub commit with the deployed version
git tag v0.1.0 && git push origin v0.1.0
```

The customer can now open the app directly in their tenant.

---

## The Polish vs. Prototype Decision

### When you can skip the full spec

Skip step 8 and go straight to Claude Code from a mockup if:

- You are exploring whether an idea is worth pursuing
- The audience is internal and just needs to see the concept
- You are willing to throw it all away

### When you should not skip it

Do not skip the full spec if:

- The app will be shown to a customer
- The app will be deployed to a customer tenant
- You will need to maintain or extend it
- More than one person will work on it

| Without a spec | With a spec |
|---|---|
| 20–40 Claude Code iterations | 5–15 Claude Code iterations |
| Higher risk of wrong direction | Token cost usually recovered during build |

---

## What a Complete Spec Looks Like

A finished design spec for a Dynatrace App runs **800 to 1,500 lines of markdown**. It includes:

- Purpose and overview, with named users and the north star metric
- Tab structure, with route keys and what each tab is for
- Visual design system including color palette, typography, component anatomy diagrams, badge variants, and hover behavior
- Global filter bar definition with the DQL impact of each filter
- Global data contracts including cached lookup queries and loading behavior
- Drill-down architecture using direct deep links and AppEngine intent contracts
- Tab-by-tab specification including stats bars, hero tiles, supporting tiles, and DQL for each
- DQL reference appendix with critical rules embedded as comments and inline notes
- App configuration including `app.config.json`, intent registration, and permissions
- Component library to build first
- Known limitations and future work
- Acceptance criteria per tab

---

## Appendix A: Anonymized Example Specification

The following is a lightly anonymized excerpt from a real spec for a multi-tab observability intelligence app. The full spec runs about 1,400 lines of markdown. This excerpt shows the structure and level of detail to aim for.

```
# [App Name] — Implementation Specification

## 1. Purpose and Overview
## 2. Tab Structure
## 3. Visual Design System
## 4. Global Filter Bar
## 5. Global Data Contracts
## 6. Drill-Down Architecture
## 7. Tab-by-Tab Specification
## 8. Critical DQL Rules
## 9. App Configuration
## 10. Component Library
## 11. Known Limitations
## 12. Acceptance Criteria
```

> **The bar:** Real hex codes. Real DQL with the actual field names. Real permission strings. Real acceptance criteria with real numbers. That is the bar.

---

## Appendix B: Troubleshooting Cheat Sheet

### The Dynatrace MCP returns "tool not found" in Claude

The MCP server is not actually connected. Re-check Settings and Connectors in the Claude client, or your MCP config file in Claude Code. Restart the client after reconfiguring.

### dt-app dev will not load in the tenant

Confirm you are logged in to the tenant in the same browser session, confirm the tenant URL uses `.apps.dynatrace.com`, and confirm the app permissions match what your DQL requires.

### DQL queries return nothing

```sql
-- First check the time range
-- Then verify field names, especially dt.* prefixes
-- Use describe to inspect available fields:
describe [entity-type]
```

### makeTimeseries errors with cryptic messages

This is often caused by inline math inside the aggregation. Compute raw values first, then convert in a subsequent step:

```sql
// WRONG: inline math in aggregation parameter
makeTimeseries avg(duration / 1000000)

// CORRECT: raw aggregation first, then convert
makeTimeseries avg_ns = avg(duration)
| fieldsAdd avg_ms = avg_ns[] / 1000000
```

### Multi-aggregation summarize errors

Wrap multiple aggregations in curly braces:

```sql
// WRONG
summarize total = count(), failures = countIf(error == true)

// CORRECT
summarize {total = count(), failures = countIf(error == true)}, by: {span.name}
```

### Claude Code wants to write the whole app in one pass

Require it to summarize the current state and propose a file-by-file plan before implementing.

### The app looks like every other Strato app

Add the brand palette earlier in the workflow so Claude has explicit visual direction from step 1.

### You are dozens of iterations into a build and it still is not right

Stop and generate the full specification before continuing. If the app proves valuable enough to keep, you can retrofit a spec by asking Claude to generate one from the current codebase.

---

## Appendix C: The CLAUDE.md Prompt Pattern

Using a `CLAUDE.md` file at the repo root persists project-level guidance. Claude Code reads this file automatically on every invocation.

```markdown
# CLAUDE.md

## Goal
One sentence describing what this project is.

## Guardrails
- Coding principles
- Propose a plan before writing code
- Justify key architectural decisions

## Tasks
1. Current Phase 1 implementation priority
2. Next priority
3. ...

## Persistence
Update this file during long sessions and before compactification.
Reflect the current state of completed and in-progress work.

## Documentation
See README.md for setup and usage. Keep it current as the app evolves.

## Notifications
Send completion notices to: [your-slack-channel or email]
```

This pattern helps Claude Code stay aligned across long builds and compactification events. It is optional, but it pays off quickly on projects that span more than a few sessions.
