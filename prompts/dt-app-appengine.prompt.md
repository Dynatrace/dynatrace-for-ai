# Prompt — Create a Dynatrace AppEngine Application

Use this as the **first paste into Claude (Sonnet → Opus if needed)** when starting a new customer app from this template. Fill in every `«bracketed»` field. Delete sections you genuinely don't need rather than leaving them empty — empty fields generate generic output.

Paired workflow: `designing_dynatrace_apps_with_claude.md` (9-step process). This prompt covers Steps 1–3 in one shot. Steps 4–9 happen in follow-up turns.

---

## Paste this into Claude

```
You are helping me design a Dynatrace AppEngine application for a real customer.
I am a Dynatrace Solutions Engineer. The output will be shown to the customer and
deployed to their tenant, so it must be customer-quality — not a throwaway.

────────────────────────────────────────────────────────────────────────────
CONTEXT
────────────────────────────────────────────────────────────────────────────
Customer:           «customer name, e.g. Cardinal Health»
Tenant URL:         «https://«tenantid».apps.dynatrace.com»
Industry / domain:  «e.g. healthcare distribution, airline ops, financial services»
Primary users:      «role + seniority, e.g. SRE leads, TechOps managing director»
Decision they make: «the specific decision the app should improve»
Current workaround: «what they do today — spreadsheets, classic dashboards, paging RCA»
Pain / why now:     «what makes the current state unacceptable»

────────────────────────────────────────────────────────────────────────────
PROBLEM STATEMENT (one sentence)
────────────────────────────────────────────────────────────────────────────
«One sentence. Lead with the user's problem, not the app you think you want.»

Example pattern:
"«User role» cannot see «critical signal» before «bad outcome», so they react
instead of getting ahead."

────────────────────────────────────────────────────────────────────────────
SCOPE
────────────────────────────────────────────────────────────────────────────
Tabs / views:          «list 2–5; one sentence each on purpose»
Data sources in scope: «e.g. dt.davis.problems, spans, logs, host metrics, K8s events»
Data sources OUT of scope: «be explicit — saves correction cycles»
Drill-down behavior:   «which tile opens which app/intent»
Refresh cadence:       «live / 1 min / 5 min / on-demand»
Global filters:        «tier, environment, application tag, time range, etc.»

────────────────────────────────────────────────────────────────────────────
VISUAL DIRECTION
────────────────────────────────────────────────────────────────────────────
Theme:        «dark / light / both — prefer dark for ops»
Density:      «sparse hero-style / dense analyst-style»
Inspiration:  «name 1–2 real products or screenshots if you can paste them»
Brand colors (Dynatrace primary palette — use these, do not invent):
  Blues:    #1C5BE5  #4635D6  #1497FF  #54C8E9
  Purples:  #B23BE4  #6C3AD6  #6F2EA8
  Greens:   #BDDF28  #73BE28
  Pink:     #E436FF
Tone:        «product-grade React UI, not Strato-default wireframe»

────────────────────────────────────────────────────────────────────────────
OUT OF SCOPE FOR THIS PASS
────────────────────────────────────────────────────────────────────────────
«Anything you do NOT want Claude to design yet — auth flows, admin pages,
exotic visualizations, mobile responsiveness, etc.»

────────────────────────────────────────────────────────────────────────────
WHAT I WANT FROM YOU, IN THIS ORDER
────────────────────────────────────────────────────────────────────────────
1. **Pressure-test the idea first.** Give me:
   - the strongest version of this app,
   - the weakest assumption I am making,
   - the one thing that, if I get it wrong, makes this useless to the user.
   Do not move on until I respond.

2. **Once I approve the direction, produce an HTML artifact mockup** with:
   - realistic placeholder data (numbers, app names, host counts that make sense
     for «customer industry»),
   - the brand palette applied,
   - information hierarchy that matches the user's decision flow
     (what they need first must be biggest and topmost),
   - density tuned per the Visual Direction above.

3. **After the mockup renders, wait for my feedback** before iterating.
   Do not auto-refine — I want to review the structure first.

4. **When I say "wire to real data,"** use the Dynatrace MCP connected to
   «tenant URL» to query the tenant. For each tile:
   - write the DQL,
   - execute it,
   - update the mockup with real returned values,
   - show both the DQL and the values in chat,
   - STOP if any query returns nothing or obviously wrong data — do not
     invent placeholder values.

5. **When I say "generate the spec,"** produce a complete implementation-ready
   design specification for Claude Code covering:
   - AppEngine structure, permissions, intents
   - routing and reusable React components
   - global filters and their DQL impact
   - DQL per tile with real field names (not pseudocode)
   - drill-down behavior and AppEngine intent contracts
   - phased build plan with acceptance criteria
   - known limitations and future work
   Target length: 800–1500 lines of markdown.

────────────────────────────────────────────────────────────────────────────
GUARDRAILS
────────────────────────────────────────────────────────────────────────────
- Never invent DQL field names. If you are not sure a field exists, say so and
  propose `describe` queries to confirm.
- Never fabricate Dynatrace product features that do not exist.
- Prefer Smartscape (`smartscapeNodes`) over classic `dt.entity.*` entity queries.
- For multi-aggregation `summarize`, wrap in curly braces.
- Do not put inline math inside `makeTimeseries` aggregation parameters —
  compute raw, then convert with `fieldsAdd`.
- Tenant URL must use `.apps.dynatrace.com`, not `.live.dynatrace.com`.
- If anything in this prompt is ambiguous, ask before assuming.

Begin with step 1 (pressure-test). Wait for my response.
```

---

## After the design pass — switching to Claude Code (Step 9)

Once Claude has produced the spec, open this repo in Claude Code and paste:

```
Read designing_dynatrace_apps_with_claude.md and the design spec I just pasted
below. Then:

1. Summarize your understanding of the app in 5 bullets.
2. Propose a file-by-file plan for Phase 1 (scaffold + global filters +
   one fully-wired tab). Do not write code yet.
3. Wait for my approval before implementing.

Use the dt-dql-essentials and dt-app-dashboards skills from .claude/skills
before writing any DQL or dashboard JSON.

——— DESIGN SPEC ———
«paste the full markdown spec produced by Claude in step 8»
```

Then iterate Phase 1 → review in `dt-app dev` → commit → Phase 2, and so on.

---

## Tips

- **Use Sonnet first.** Switch to Opus only if ideation is generic or the spec
  step is producing fluff.
- **Start a fresh chat for the spec.** The mockup-iteration chat accumulates
  noise; the spec chat should start clean with the final mockup pasted in.
- **Keep the customer name and tenant URL in the prompt.** Claude will route
  MCP calls accordingly and will pattern-match industry-appropriate placeholder
  data.
- **Anchor with example dashboards.** If the customer has existing dashboard
  JSON or screenshots, paste them — Claude pattern-matches well from concrete
  examples.
