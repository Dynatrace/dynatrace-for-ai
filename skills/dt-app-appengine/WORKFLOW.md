# Workflow: From Idea to Deployed Dynatrace App

This is the human-facing process for designing and shipping a custom Dynatrace App on AppEngine. It covers ideation, mockup, real-data wiring, and specification writing — everything that happens *before* you scaffold the app in Claude Code.

The technical scaffold, build, and deploy mechanics live in `SKILL.md`. This file is the design judgement that makes a customer-presentable app instead of a throwaway prototype.

## Audience

Dynatrace Solutions Engineers and Customer Success Engineers building a custom Dynatrace App for a customer or internal use. Assumes you know Dynatrace, can read DQL, have a tenant to develop against, and want a polished result rather than a one-off prototype.

---

## Prerequisites (human-side)

The technical CLI prerequisites (`node`, `npm`, `dt-app`, `dtctl`, MCP server) are checked automatically when you start the skill — see `SKILL.md`. The setup that is not just CLI tooling:

### 1. A Dynatrace tenant you can develop against

**Tenant endpoint:** SaaS tenant URL of the form `https://tenantid.apps.dynatrace.com`. This is the AppEngine endpoint, not the classic `.live.dynatrace.com` URL. Confirm you can log in to the Apps UI before continuing.

**Recommended usage:** For customer work, use a customer sandbox or non-prod tenant if one exists. If you are developing directly against production, get written approval from the customer first.

### 2. The Dynatrace MCP server

The MCP (Model Context Protocol) server is what lets Claude talk to your tenant. This is the **single most important prerequisite** for the design phase.

- Docs: https://docs.dynatrace.com/docs/dynatrace-intelligence/dynatrace-intelligence-integrations/dynatrace-mcp
- Hub listing: https://www.dynatrace.com/hub/detail/dynatrace-mcp-server/

Follow the connection instructions for both clients:

- **Claude client:** connect through Settings → Connectors, providing the tenant URL and OAuth credentials.
- **Claude Code:** configure the MCP server in your MCP settings using the same tenant context.

**Validate the connection** by asking Claude in either client:

> "Use the Dynatrace MCP to fetch the last 5 problems from my tenant."

If it returns real data, you are wired up.

### 3. Claude client and Claude Code

- **Claude client:** ideation, visual mockups, specification writing. Sonnet handles most of this well; switch to Opus when you need deeper reasoning.
- **Claude Code:** terminal-based implementation against the customer tenant.

### 4. A GitHub repo

Empty, private, customer-scoped if this is customer work. You'll connect your local app folder to it during scaffolding.

### 5. The Dynatrace for AI skills repo

A growing library of agentic skills (DQL essentials, dashboard patterns, observability domain skills, lessons learned). Clone it locally so you can point Claude Code at specific skill files during the build — particularly the DQL ones, which prevent common errors.

Repo: https://github.com/Dynatrace/dynatrace-for-ai

### 6. Dynatrace brand assets (optional, recommended)

If your app is customer-facing or will be demoed to leadership, ground the visual design in real Dynatrace brand colors and typography rather than letting Claude guess.

Brand portal (internal): https://dynatrace.sharepoint.com/sites/MarketingComms/SiteAssets

Primary brand palette to paste directly into prompts:

| Palette | Hex Values |
|---------|-----------|
| Blues | `#1C5BE5` `#4635D6` `#1497FF` `#54C8E9` |
| Purples | `#B23BE4` `#6C3AD6` `#6F2EA8` |
| Greens | `#BDDF28` `#73BE28` |
| Pink | `#E436FF` |

Telling Claude to use these from step 1 produces a modern React-style UI rather than the default Strato look.

---

## The process at a glance

The full workflow has nine steps. Steps 1 through 8 happen in the Claude client. Step 9 happens in Claude Code in the terminal and is driven by `SKILL.md`.

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
| 9 | Claude Code | Scaffold, build, and deploy the real app (see `SKILL.md`) |

---

## Step 01 — Ideate with Claude (First Pass)

**How to start:** Open a new chat in the Claude client. Start with Sonnet. State the problem you are trying to solve, not the app you think you want to build.

| Less effective | More effective |
|---|---|
| "I want to build a dashboard for cascade risk." | "Our customer's TechOps team cannot see when one application's failure is about to take down five others, and they are reacting instead of getting ahead." |

**What to include in the prompt:** Name the customer, the problem, the current workaround, the data sources you know about, and what you want Claude to help you think through — the most valuable angles, the primary user per angle, the data sources needed, and the killer view.

**How to evaluate the options:** Let Claude propose three or four directions. Do not commit yet. Push back on weak ones. Ask "what would this look like for a managing director vs an SRE?" if the audience is unclear.

**When to switch models:** Switch to Opus if Sonnet is producing generic ideas that could apply to any customer, and you suspect there is a sharper angle you have not surfaced.

**Done when:** You have one direction picked, and you can write a single sentence describing what the app is for and who it is for.

---

## Step 02 — Re-Ideate with Claude

**Why a second chat matters:** Start a fresh chat. The first chat has accumulated meandering context. The second chat gets the polished version of the idea.

**How to pressure-test the idea:** Paste your one-sentence app description from step 1 and ask Claude to pressure-test it. Ask for the strongest version, the weakest assumption, and the one thing that, if you get it wrong, makes the whole app useless to the user.

**Why this step saves time:** It catches the failure mode where step 1 produced an idea that sounded good but does not survive contact with reality. If Claude finds a hole, fix the idea. If it does not, move on.

**Done when:** You have a refined one-paragraph description of the app, with named users, named decisions, and named data sources.

---

## Step 03 — Provide an 80% Complete Design Prompt

This is the prompt that produces your first visual mockup. Spend real time on it. The quality of everything downstream is set here.

**Prompt structure:** Include these sections:

- **Context:** who the customer is, what the app is for, who the primary users are, and what decisions the app helps them make.
- **Scope:** the number of tabs or views, what each one is for, the data sources involved, drill-down behavior, and refresh cadence expectations.
- **Visual direction:** theme, brand colors, tone, density, and design inspiration.
- **Out of scope:** features you do not want Claude to design yet.
- **Task:** build a non-functional visual mockup as an HTML artifact using realistic placeholder data, with emphasis on layout, information density, and visual hierarchy.

**Done when:** You have submitted the prompt and Claude is producing an artifact.

---

## Step 04 — Visual Mockup in the Claude Client

Claude will render an HTML artifact in the right pane. Look at it for a full minute before you react. Ask yourself:

- Does the information hierarchy match the user's decision flow? What the user needs first should be biggest and topmost.
- Is the density right? Too sparse means the user will scroll for everything. Too dense means they cannot find anything.
- Does it look like a product, or does it look like a wireframe?

Take a screenshot. Save it. You will compare future iterations against this one.

**Done when:** You have a mockup that is at least 70% of what you want.

---

## Step 05 — Refine the Design and Re-Render

Iterate with restraint at this stage. Avoid over-refining a mockup that will change once real data is added.

**Productive refinements now:** re-arranging major sections, adding or removing whole views, changing the visual approach, establishing patterns.

**Ignore for now:** specific tile copy, exact color shades, spacing tweaks, icon choices. Bank those for step 7.

**Done when:** The structure is right and the visual direction is locked, even if the data is fake and the polish is rough.

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

**Done when:** Every tile in the mockup shows real numbers from the customer tenant, and you have the DQL for each one captured in the chat.

---

## Step 07 — Tweak to 90–95% of Your Liking

Refine tile copy, color accents, callout boxes, badge styling, chip styling, section headers, empty states, hover behavior, and stat-bar numbers.

> **Important:** Stop at about 95% complete. The last layer of polish belongs in the real app build with real components. Any visual polish you do in the HTML mockup gets thrown away anyway.

**Done when:** You would be comfortable showing this mockup to the customer as a "here is what we are going to build" reference.

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

**Done when:** The spec is comprehensive enough that someone who was not in this chat could read it and know exactly what to build.

---

## Step 09 — Scaffold, Build, and Deploy with Claude Code

Switch surfaces: open your terminal and open Claude Code with your spec from step 8 ready to paste.

From here, `SKILL.md` takes over. It enforces:

- A pre-flight check of `node`, `dt-app`, `dtctl`, and tenant auth.
- A plan-first contract: Claude Code must summarize state and propose a file-by-file plan before writing code.
- Phase-by-phase iteration with acceptance criteria and GitHub commits between phases.
- A gated deploy step that requires your explicit authorization before `dtctl app deploy` runs.

Paste your spec into Claude Code and let the skill drive.

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

## Appendix B: The CLAUDE.md Prompt Pattern

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