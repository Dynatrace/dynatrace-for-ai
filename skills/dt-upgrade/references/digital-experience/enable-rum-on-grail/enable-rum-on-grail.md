# Enable RUM on Grail (Frontend Enablement)

<!-- Jira: none -->

**Gen3 replacement**: RUM on the latest Dynatrace (Experience Vitals, Error Inspector, Users & Sessions)
**Applies to**: Phase 1 and Phase 2 tenants — enabling RUM on Grail is valid regardless of which of these phases the tenant is currently on

## Tenant Setup

Before any other step, collect the target tenant from the user:

> **Ask**: "What is the environment ID (or full URL) of the Dynatrace tenant you want to enable RUM on Grail for?"
>
> Expected format: either `abc12345` or `https://abc12345.apps.dynatrace.com`.

Derive and store the following variables; reuse them verbatim in all subsequent steps:

| Variable       | Value                                          |
|----------------|------------------------------------------------|
| `$env_id`      | the environment ID (e.g. `abc12345`)           |
| `$tenant_url`  | `https://$env_id.apps.dynatrace.com`           |
| `$classic_url` | `https://$env_id.live.dynatrace.com`           |

> If the user has already supplied the tenant in their opening message, extract it automatically — do not ask again.

## Prerequisites

- SaaS environment with a DPS contract in place.
- Frontends are already instrumented and reporting via classic RUM (OneAgent or agentless/manual snippet).
- Settings API access with read + write permissions for:
  - `builtin:rum.web.name`, `builtin:rum.web.enablement`
  - `builtin:rum.mobile.name`, `builtin:rum.mobile.enablement`
  - `builtin:rum.custom.name`
- Cordova-based mobile apps are **not yet supported** on Grail. Defer these frontends and note them in the plan output.
- Custom apps have **no Grail path yet**. List them in the plan output but take no action.
- If the customer manages RUM settings via **Monaco or Terraform**, changes made through the Settings API will be overwritten on the next config-as-code pipeline run. Ask the user whether they use config-as-code tooling before proceeding.

- **Authentication**: determine which credential type the dtctl context uses before running any commands. Run `dtctl auth whoami --context <ctx>` to confirm auth is working regardless of type. Ask the user whether he will provide a platform token or authenticate via OAuth.

  - **Platform token** (`dt0s16.*`): Read it once and pass as `Authorization: Bearer <token>`. No rotation — no bootstrap needed. Verify with `cmdkey /list | Select-String "dtctl"`. Also required for Step 6B (frontend deletion). Create in **Settings → Access tokens**, scope `rum:frontends:delete`. Use the platform/apps domain (`https://<env-id>.apps.dynatrace.com`). Not available via `dtctl` — use `curl` or `Invoke-WebRequest` directly with `Authorization: Bearer <platform-token>`.
  - **OAuth refresh token**: stored under `dtctl:oauth:<env-type>:<env-id>-oauth` in Credential Manager. Before any commands, bootstrap a session: read the refresh token from Credential Manager (the blob is UTF-8 JSON), exchange it at the SSO token endpoint for a bearer, write the rotated refresh token back to Credential Manager, and save the bearer to `$env:TEMP\dt_bearer.txt` for reuse. Key constraints: **no parallel `dtctl` calls** (refresh token rotates per call); **`curl.exe` only** for token exchange (`Invoke-WebRequest` returns 403); **entire bootstrap in one atomic call** (shell state does not persist across calls); **re-run bootstrap on 401**.

  > **New context (no existing entry)**: if `cmdkey /list | Select-String "dtctl"` shows no entry for the target tenant, create the context and authenticate before running the bootstrap:
  > ```powershell
  > dtctl config set-context <name> --environment https://<env-id>.apps.dynatrace.com --safety-level readwrite-all
  > dtctl auth login --context <name>   # opens a browser tab; completes OAuth; stores credential automatically as dtctl:oauth:<env-type>:<env-id>-oauth
  > ```
  > Note: the flag is `--environment` (not `--env` — that flag does not exist and errors).

- **Classic API token** (`dt0c01.*`): required for Step 3 (Metrics API traffic check). Create in the Dynatrace UI under **Settings → Access tokens**, scope `metrics.read`. Use the **classic API domain**: `https://<env-id>.live.dynatrace.com`. curl header: `-H "Authorization: Api-Token <token>"` — the dtctl OAuth token is not accepted by the classic Metrics API.

  > **Header pitfall**: the full `Authorization:` prefix is required. Using `-H "Api-Token <token>"` (without `Authorization:`) causes curl to silently drop the header and the API returns 401 "Missing authorization parameter."

  > **Token availability check (run before Step 3)**: confirm whether a classic API token already exists for the target environment. Ask the user. If no token is available: prompt the user to create one now, or explicitly confirm that Step 3b will be skipped and all Candidates will be treated as active. Classic tokens are environment-scoped and return HTTP 401 on the wrong tenant.

## Instructions

> **Prerequisite — Verify upgrade phase (gate check)**
>
> This skill applies to **Phase 1 and Phase 2** tenants only. Call the management service using the bearer token from the session bootstrap (`$env:TEMP\dt_bearer.txt`):
>
> ```
> GET https://<env-id>.apps.dynatrace.com/platform-reserved/management-service/v1/settings
> Authorization: Bearer <bearer>
> ```
>
> **Important**: `Invoke-WebRequest` returns HTTP 403 on this endpoint — use `curl.exe` only.
>
> Response: `{ "phaseId": <number>, "showQuickStart": <boolean> }`
>
> - **phaseId 1 or 2** → proceed.
> - **phaseId 3 or higher** → **stop.** The tenant has already completed the Group 3 (Enhanced) transition — this skill does not apply. A user can proceeed but some of the checks won't work as some settings and classic data are not reachable.
>
> Alternatively (human-only): run in the browser console while logged into the tenant UI:
> ```javascript
> fetch("/platform-reserved/management-service/v1/settings").then(x=>x.json()).then(r=>console.log(r))
> ```

### Step 0 — Check and set environment-level Grail RUM

Retrieve the `environment`-scoped settings object from both `builtin:rum.web.enablement` and `builtin:rum.mobile.enablement`. This controls the tenant-wide default; per-frontend overrides are handled in Step 6.

> **Fetching the env record**: `dtctl get settings --schema <schema> --scope environment` returns `null` on most tenants even when an env-level record exists (known dtctl limitation). Instead, fetch all records (`dtctl get settings --schema <schema> --plain -o json`) and identify the env record in code: it is the one whose decoded `objectId` scope does **not** match `APPLICATION` or `MOBILE_APPLICATION`.

If no environment-scoped record is found, skip.

For each type (Web, Mobile):
- If `rum.enabled === true` **and** `rum.enabledOnGrail` is absent or `false` → PATCH to set `rum.enabledOnGrail: true`.
- If `rum.enabled` is `false` at env level → surface to the user as a notable finding. Do **not** skip the per-frontend inventory — individual frontends may still have classic RUM enabled only via per-scope override.

**Always proceed to Step 1 regardless of what the env-level object shows.**

### Step 1 — Inventory all frontends

Retrieve all objects for the schemas below, paginating through all pages. Skip the environment-level record in each result (identified by decoded objectId scope — see dtctl note below).

| Type   | Name schema                | Enablement schema               |
|--------|----------------------------|---------------------------------|
| Web    | `builtin:rum.web.name`     | `builtin:rum.web.enablement`    |
| Mobile | `builtin:rum.mobile.name`  | `builtin:rum.mobile.enablement` |
| Custom | `builtin:rum.custom.name`  | (none — no Grail enablement)    |

Join each name record (`value.applicationName`) with its corresponding enablement record by `scope`. Use `scope` (the `APPLICATION-xxx` or `MOBILE_APPLICATION-xxx` identifier) as the join key — application names are not unique. Retain the full enablement object; Session Replay fields are needed in Step 4.

> **`value.applicationName` applies to both web and mobile**: both `builtin:rum.web.name` and `builtin:rum.mobile.name` store the display name in `value.applicationName`. Using `value.name` for mobile silently returns empty strings.

> **dtctl scope decode**: dtctl returns `"scope": ""` for all objects. Decode the scope from `objectId` (base64url → ISO-8859-1 → regex): match `MOBILE_APPLICATION[^A-Z0-9]*([A-F0-9]{16,})` first, then `APPLICATION[^A-Z0-9]*([A-F0-9]{16,})`. Always search `MOBILE_APPLICATION` before `APPLICATION` — `APPLICATION` is a substring and would match falsely. The `[^A-Z0-9]*` skips the null-byte + length-byte separator between the scope type string and the hex ID; a simple `APPLICATION-` never matches after base64 decode.
>
> Use `--plain -o json` with dtctl to get clean JSON ready for parsing.
>
> **BOM-free DQL files**: `Set-Content -Encoding utf8` in PowerShell 5.1 adds a BOM; DQL rejects it. Always write query files with `[System.IO.File]::WriteAllText($path, $dql, (New-Object System.Text.UTF8Encoding $false))` and run `dtctl query -f <file>`. For large tenants add `--default-scan-limit-gbytes 2000` (default 500 GB cap).
>
> **dtctl JSON output may include warning text**: when a command emits a warning (e.g., a DQL scan limit notice), the warning is prepended to stdout before the JSON result. This causes `ConvertFrom-Json` to fail. Strip non-JSON content before parsing: `$jsonStart = $result.IndexOf('{'); if ($jsonStart -gt 0) { $result = $result.Substring($jsonStart) }`

### Step 2 — Classify each frontend

**Monaco check first**: for each Candidate, fetch its Settings object individually with `dtctl get settings <objectId>` and inspect `externalId`. If it starts with `monaco:`, mark as Monaco-managed. Bulk fetches always return `externalId: ""` — per-object fetch is required.

Evaluate each frontend in order. Stop at the first matching rule.

| Rule | Classification | Next action |
|---|---|---|
| `type == Custom` | **Deferred** | List for user; no change |
| `rum.enabledOnGrail === true` | **Already on Grail** | Skip |
| `rum.enabled === true` AND `rum.enabledOnGrail` absent or `false` | **Candidate** | Step 3 → 4 |
| `rum.enabled` absent or `false` | **RUM disabled** | Step 3 |

> **No per-frontend record — inherit env-level values**: if the Step 1 join finds no enablement record for a frontend (no per-frontend scope override exists in the Settings API), classify the frontend using the **env-level values read in Step 0** — not absent/false defaults. On a tenant where the env-level record has `rum.enabled=true` and `rum.enabledOnGrail=true`, these unmatched frontends are **Already on Grail** (they inherit the tenant default). Defaulting to `false` when no record is found will misclassify them as "RUM disabled" and generate incorrect deletion candidates.

### Step 3 — Check classic data for all non-Grail frontends

> Run the Metrics API check on **both** Candidates and RUM-Disabled frontends. A Candidate with zero traffic is a better candidate for deletion than enablement — run Step 3 on everything to produce a single coherent plan.

**3a.** Retrieve `FRONTEND-xxx` IDs for RUM-disabled frontends from Smartscape:

```dql
smartscapeNodes "FRONTEND", from: now()-3d
| filter dt.rum.instrumentation.rum.enabled == false
| fields id, name, frontend.name, id_classic
| sort name
| limit 500
```

`id` = `FRONTEND-xxx` (needed for deletion in Step 6B). `id_classic` = `APPLICATION-xxx` — cross-reference with the Settings API list by matching `id_classic` to `scope`.

> **DQL syntax**: entity type is a **quoted string** argument — `smartscapeNodes "FRONTEND"` (not bare `smartscapeNodes FRONTEND`, no `fetch` prefix). Write to a BOM-free file and use `dtctl query -f <file>`.
>
> Dead Candidates (RUM enabled, no traffic) will not appear in the `rum.enabled == false` filter. Retrieve their `FRONTEND-xxx` IDs with a separate unfiltered `smartscapeNodes "FRONTEND"` query, then match by `id_classic` in code.

**3b.** Query classic activity via the Metrics API v2.

> **API domain**: use the **classic domain** (`https://<env-id>.live.dynatrace.com`) with `Api-Token <dt0c01.*>` — not the platform apps domain.

Web frontends:
```
GET /api/v2/metrics/query
  ?metricSelector=builtin:apps.web.actionCount.load.browser:splitBy("dt.entity.application"):sum
                 ,builtin:apps.web.actionCount.xhr.browser:splitBy("dt.entity.application"):sum
  &from=now-60d
```

> **Metric note**: use `builtin:apps.web.actionCount.*` (these have the `dt.entity.application` dimension).

Mobile frontends:
```
GET /api/v2/metrics/query
  ?metricSelector=builtin:apps.mobile.sessionCount:splitBy("dt.entity.mobile_application"):value
  &from=now-60d
```

> **Mobile**: dimension key is `dt.entity.mobile_application` (not `dt.entity.application`). Use `:value` — `:sum` returns 400.

> **If no classic token is available**: skip Step 3b, note it in the plan output, and let the user decide whether to enable or defer frontends without traffic data. `fetch user.events` is **not** a valid fallback — Candidates have `enabledOnGrail=false` and never send events to Grail, so they will always show 0 regardless of actual classic traffic.

**3c.** Interpret results:

| Metrics result | Classification | Recommended action |
|---|---|---|
| Has traffic | Candidate | Enable Grail RUM (action A) |
| No traffic (60d) | Candidate | Propose deletion — do not enable |
| Has traffic | RUM Disabled | Surface as unusual state — ask user intent |
| No traffic (60d) | RUM Disabled | Propose deletion (action B) |

### Step 4 — Check Session Replay status for Candidates

Inspect the enablement object from Step 1 — no additional API call needed.

**Web** (`builtin:rum.web.enablement`): `sessionReplay.enabled`, `sessionReplay.enabledOnGrail`

**Mobile** (`builtin:rum.mobile.enablement`): `sessionReplay.fullSessionReplay`, `sessionReplay.fullSessionReplayOnGrail`, `sessionReplay.onCrash`, `sessionReplay.onCrashOnGrail`

SR on Grail requires SR Classic to be enabled. If SR Classic is off, omit the SR flag from the enablement PATCH.

- **Web**: if `sessionReplay.enabled === true` → flag `sessionReplay.enabledOnGrail: true` for PATCH.
- **Mobile**: if `sessionReplay.fullSessionReplay === true` → flag `sessionReplay.fullSessionReplayOnGrail: true`; mirror `sessionReplay.onCrash` → `sessionReplay.onCrashOnGrail`.

### Step 5 — Present classification summary and choose actions

Output the classification summary, then ask the user which actions to take.

> **Terminology**: use **web frontends**, **mobile frontends**, **custom frontends** in all output. Never expose schema names as user-facing labels.

| Classification | Web frontends | Mobile frontends | Custom frontends |
|---|---|---|---|
| Already on Grail | — | — | — |
| Candidate — has traffic | — | — | — |
| Candidate — no traffic (60d) | — | — | — |
| Candidate — ⚠ Monaco-managed (skip) | — | — | — |
| RUM disabled — has classic data | — | — | — |
| RUM disabled — no classic data | — | — | — |
| Deferred (Custom / Cordova) | — | — | — |

**Actions:**
- **(A) Enable Grail RUM** — for Candidates with traffic
- **(B) Clean up inactive frontends** — delete frontends with no traffic (dead Candidates + RUM-disabled with no data)
- **(C) Both**

Do not mix enablement and deletion in the same confirmation table. Execute only what the user confirms.

### Step 6A — Enablement plan and execution

*Skip if the user did not choose action A or C.*

Present the enablement plan:

| Frontend | APPLICATION ID | Type | Classic SR | Injection format | Recommended action |
|---|---|---|---|---|---|
| App A | APPLICATION-xxx | Web | on | JavaScript tag | Enable RUM + SR on Grail |
| App B | APPLICATION-xxx | Web | off | Inline code | Enable RUM on Grail (SR Classic off) — ⚠ redeploy snippet |
| App C | APPLICATION-xxx | Mobile | on | n/a | Enable RUM + SR on Grail — redeployment required (SDK ≥ v8.309) |
| App D | APPLICATION-xxx | Web | on | Code snippet | ⛔ Blocked — change injection format first (see below) |

The injection format is stored in the `builtin:rum.web.enablement` object already fetched in Step 1. Confirm the exact field name from a live Settings API response (look for `injectionMode` or similar).

Monaco-managed frontends: list as "⚠ Monaco-managed — update config-as-code repository instead." Do not PATCH them.

**Pre-flight — injection format check (web frontends)**: before applying `rum.enabledOnGrail: true`, verify the frontend does not use the legacy "Code snippet" injection format. The Settings API will reject the apply with: _"New Real User Monitoring Experience can't be enabled because the configured injection format Code snippet is unsupported."_ Supported formats: JavaScript tag, OneAgent JavaScript tag (with/without SRI), Inline code. Mark blocked frontends as "**⛔ Blocked — change injection format first**".

> **Code snippet — remediation**: In the Dynatrace classic UI, navigate to the app's **General settings → Injection** and switch from *Code snippet* to *JavaScript tag* (or *Inline code*). After saving, retrieve the updated snippet from the UI and redeploy it on the customer's site. Then re-run Step 6A to apply `enabledOnGrail: true`.
> Reference: [Injection snippet formats](https://docs.dynatrace.com/docs/observe/digital-experience/rum/web-frontends/initial-setup/snippet-formats)

**Manual snippet formats — customer redeploy required after enabling**: Not all agentless formats self-update. After applying `enabledOnGrail: true`:

| Format | Snippet update behaviour | Customer action |
|---|---|---|
| JavaScript tag | Auto-refreshes via 1-hour cache | None — propagates automatically |
| OneAgent JavaScript tag (auto-injection) | OneAgent pushes current config | None — OneAgent handles it |
| OneAgent JavaScript tag (manual insertion) | Must be manually updated | Retrieve updated snippet from UI and redeploy on site |
| Inline code | Must be manually updated | Retrieve updated snippet from UI and redeploy on site |

Note this in the plan table and in the customer-facing confirmation message for affected frontends.

**Do not apply any changes until the user explicitly confirms the plan.**

#### Apply via dtctl

Retrieve the current enablement object as YAML, edit fields, apply. Use `$enablementMap[$scope].objectId` (the enablement object's `objectId`, not the name object):

```
dtctl get settings --context <ctx> <enablement-objectId> -o yaml > frontend.yaml
# Set rum.enabledOnGrail: true (and SR fields as needed — see constraint below)
dtctl apply --context <ctx> -f frontend.yaml
```

**`sessionReplay.enabledOnGrail` constraint**: only set `sessionReplay.enabledOnGrail: true` when `sessionReplay.enabled` is `true`. Including it when SR Classic is off (even as `false`) triggers a validation error. Same for mobile: `fullSessionReplayOnGrail` requires `fullSessionReplay: true`.

> **dtctl apply YAML format**: for bulk applies (multiple objects), the YAML must be a **list** (items prefixed with `- objectid: ...`). Multi-document YAML with `---` separators is treated as a single object.

#### Apply via direct HTTP (if dtctl is unavailable)

Use the **classic domain** (`https://<env-id>.live.dynatrace.com`). POST accepts an array; returns **HTTP 207** — check each item's `code` field (`200` = success).

Web value object (full replacement — include all existing fields):
```json
{
  "rum": { "costAndTrafficControl": <existing>, "enabled": true, "enabledOnGrail": true },
  "sessionReplay": { "costAndTrafficControl": <existing>, "enabled": <existing>, "enabledOnGrail": true }
}
```

Mobile (partial merge accepted):
```json
{
  "rum": { "enabledOnGrail": true },
  "sessionReplay": { "fullSessionReplayOnGrail": true, "onCrashOnGrail": true }
}
```

Include SR fields only if the corresponding Classic flags were `true` (Step 4).

### Step 6B — Clean-up plan and execution

*Skip if the user did not choose action B or C.*

| name | frontend.name | FRONTEND ID | APPLICATION ID | Type | Traffic (60d) | Action |
|---|---|---|---|---|---|---|
| Legacy App | Legacy_App | FRONTEND-xxx | APPLICATION-xxx | Web | None | Delete |
| Dead Candidate | Dead_Candidate | FRONTEND-xxx | APPLICATION-xxx | Web | None | Delete — no traffic |
| Disabled (has data) | Disabled_App | FRONTEND-xxx | APPLICATION-xxx | Web | Present | ⚠ Confirm intent |

**Do not delete any frontend until the user explicitly confirms this plan.**

**Retrieving FRONTEND-xxx IDs**:

```dql
smartscapeNodes "FRONTEND", from: now()-3d
| filter dt.rum.instrumentation.rum.enabled == false
| fields id, name, frontend.name, id_classic
| sort name
| limit 500
```

For dead Candidates, use a separate unfiltered `smartscapeNodes "FRONTEND"` query (no `rum.enabled` filter), then match `id_classic` to the APPLICATION-xxx scope in code.

**Execute deletion**:

```
DELETE https://<env>.apps.dynatrace.com/platform/rum/v1/frontends/{FRONTEND-xxx}
Authorization: Bearer <dt0s16.*-platform-token>
```

Success: **HTTP 204**. Not available via `dtctl`.

### Step 7 — Validate data ingestion

*Run after Steps 6A and 6B complete.*

Use `fetch user.events` — events appear before sessions (sessions aggregate with ~30 min delay).

```dql
fetch user.events, from: now() - 2h
| filter frontend.name == "<frontend-name>"
| summarize event_count = count()
```

> **DQL file required**: inline DQL strings containing `.` in filter values fail (parser treats `.` as a field accessor). Write to a BOM-free file and run `dtctl query -f <file>`.
>
> **frontend.name format** for Dynatrace platform apps: `Dtp-App<appIdentifier>_<DisplayName>` — e.g., `Dtp-Appdynatrace.logs_Logs`. Confirm the exact value from the `smartscapeNodes` query result rather than constructing it manually.

If `event_count` is 0 after 30–60 minutes:
- **Dev/test**: zero events are expected if no real traffic runs — confirm with the user before escalating.
- **Web with agentless injection**: advise updating and redeploying the instrumentation snippet.
- **Mobile**: redeployment or SDK update likely required.
- Refer to [Transition from RUM Classic](https://docs.dynatrace.com/docs/observe/digital-experience/rum/transition-from-rum-classic).

## Step 8 — Assess Group 3 (Enhanced) Upgrade Readiness

*Run after Steps 6A and 7. Informational — no settings changes. Skip if no frontends are Grail-enabled.*

> **Scope**: run across **all** Grail-enabled frontends — not just those enabled this session. Combine "Already on Grail" from Step 2 with newly enabled from Step 6A.

Group 3 (Enhanced) requires higher minimum agent versions and the new cookie model on web frontends.

### Step 8A — Agent version check

Group 3 (Enhanced) thresholds:

- **Web**: release train ≥ **347**
- **Mobile**: release train ≥ **347** (SDK 8.347.x.x or higher)

**Web** — named list (preferred) or tenant-wide fallback:

```dql
fetch user.events, from: now() - 7d
| filter (frontend.name == "App-Name-1" or frontend.name == "App-Name-2")
       and isNotNull(dt.rum.agent.version)
| parse dt.rum.agent.version, "LONG '.' LONG:agent_version"
| summarize latest_version = max(agent_version), by: { dt.smartscape.frontend, frontend.name }
| fields dt.smartscape.frontend, frontend.name, latest_version, passes = latest_version >= 347
```

Tenant-wide fallback (no explicit list needed):
```dql
fetch user.events, from: now() - 7d
| filter dt.rum.agent.type == "javascript" and isNotNull(dt.rum.agent.version)
| parse dt.rum.agent.version, "LONG '.' LONG:agent_version"
| summarize latest_version = max(agent_version), by: { dt.smartscape.frontend, frontend.name }
| fields dt.smartscape.frontend, frontend.name, latest_version, passes = latest_version >= 347
```

> **Scan limit**: on large tenants the default 500 GB scan cap truncates results and may omit frontends. Add `scanLimitGBytes: -1` as a top-level DQL option or pass `--default-scan-limit-gbytes 2000` to the `dtctl query` call.

**Mobile** — named list (preferred) or tenant-wide fallback:

```dql
fetch user.events, from: now() - 7d
| filter (frontend.name == "Mobile-App-1" or frontend.name == "Mobile-App-2")
       and isNotNull(dt.rum.agent.version)
| parse dt.rum.agent.version, "LONG '.' LONG:agent_version"
| summarize latest_version = max(agent_version), by: { dt.smartscape.frontend, frontend.name }
| fields dt.smartscape.frontend, frontend.name, latest_version, passes = latest_version >= 347
```

Tenant-wide fallback (covers all mobile agent types — iOS, Android, Flutter, React Native, etc.):
```dql
fetch user.events, from: now() - 7d, scanLimitGBytes: 2000
| filter dt.rum.agent.type != "javascript" and isNotNull(dt.rum.agent.version)
| parse dt.rum.agent.version, "LONG '.' LONG:agent_version"
| summarize latest_version = max(agent_version), by: { dt.smartscape.frontend, frontend.name }
| fields dt.smartscape.frontend, frontend.name, latest_version, passes = latest_version >= 347
```

> **Mobile scan limit**: a 7-day `fetch user.events` filtered to non-javascript agent types hits the default 500 GB scan cap and returns a warning instead of results. `scanLimitGBytes: 2000` in the `fetch` statement is required — the default cap is insufficient for this query on large tenants.

> **`frontend.type` is NOT a field in `user.events`** — it exists on `smartscapeNodes` records only. Filtering by it in `user.events` silently returns zero results. Scope by `frontend.name` OR chain or `dt.rum.agent.type` (`"javascript"` for web, `!= "javascript"` as a tenant-wide mobile fallback).
>
> **`dt.smartscape.frontend` equality filter does not work in `user.events`**. Use `frontend.name` for scoping. `in [array("v1","v2")]` also fails with a parse error for multiple values — use an OR chain instead.
>
> **Field reference**: `dt.rum.application.entity` (format `APPLICATION-XXXXXXXXXXXXXXXX`) is present in `user.events` and matches the Step 1 inventory scope IDs directly.

### Step 8B — Cookie upgrade check (web only)

**Step 1 — Check environment level:**

```
GET https://<classic-domain>/api/v2/settings/objects
    ?schemaIds=builtin:rum.web.rum-cookies-upgrade&scopes=environment
Authorization: Bearer <dtctl-oauth-token>
```

Record the result as `env_cookie_upgrade`:
- `upgradeRumCookies: true` (or `upgraded: true`) → `env_cookie_upgrade = true` — note this as context, but **do not stop here**. Individual frontends may have a frontend-level override that disables the upgrade even when the tenant default is on.
- No env-level object → `env_cookie_upgrade = false`.

**Step 2 — Always check per frontend** (batch in groups of 50 scopes per request):

```
GET https://<classic-domain>/api/v2/settings/objects
    ?schemaIds=builtin:rum.web.rum-cookies-upgrade
    &scopes=<APPLICATION-xxx1>,<APPLICATION-xxx2>,...
    &pageSize=500
Authorization: Bearer <dtctl-oauth-token>
```

For each Grail-enabled web frontend, determine its **effective cookie status**:

| env_cookie_upgrade | Frontend-level object exists? | Frontend-level `upgradeRumCookies` | Effective status |
|---|---|---|---|
| true | No | — | ✅ inherits tenant upgrade |
| true | Yes | true | ✅ explicitly enabled |
| true | Yes | false | ❌ frontend override disables upgrade |
| false | No | — | ❌ not upgraded |
| false | Yes | true | ✅ frontend-level upgrade active |
| false | Yes | false | ❌ explicitly disabled |

Report the env-level finding as context, then list the effective status for each web frontend.

### Step 8B-2 — Apply cookie upgrade (optional)

If any web frontends show ❌ effective cookie status, offer to apply the upgrade before proceeding to 8C.

**Do not apply until the user confirms.** Show a plan table first:

| Frontend | APPLICATION ID | Cookie status | Reason | Action |
|---|---|---|---|---|
| Shop Frontend | APPLICATION-xxx | ❌ not upgraded | no env or frontend setting | Enable cookie upgrade |
| Admin Panel | APPLICATION-xxx | ❌ frontend override disables | frontend-level object set to false | Re-enable at frontend level |

> **Recommendation**: Propose the tenant-wide option — one settings object covers all frontends and avoids a large batch write. If some frontends have an explicit frontend-level override set to `false`, those must be patched individually regardless of the tenant-wide setting; a tenant-wide enable alone will not override them.

**Tenant-wide** (classic domain, bearer token):
```
POST https://<classic-domain>/api/v2/settings/objects
Authorization: Bearer <dtctl-oauth-token>
Content-Type: application/json

[{
  "schemaId": "builtin:rum.web.rum-cookies-upgrade",
  "scope": "environment",
  "value": { "upgradeRumCookies": true }
}]
```

**Per-frontend** (same endpoint, scope = APPLICATION-xxx per object — required for frontends with an explicit frontend-level override):
```json
[
  { "schemaId": "builtin:rum.web.rum-cookies-upgrade", "scope": "APPLICATION-xxx1", "value": { "upgradeRumCookies": true } },
  { "schemaId": "builtin:rum.web.rum-cookies-upgrade", "scope": "APPLICATION-xxx2", "value": { "upgradeRumCookies": true } }
]
```

Success: HTTP 207 — check each item's `code` field (`200` = success). After applying, re-verify affected frontends in the 8C summary.

### Step 8C — Group 3 (Enhanced) readiness summary

**Migration completeness:**

| Status | Web | Mobile | Blocking Group 3 (Enhanced)? |
|---|---|---|---|
| On Grail | — | — | — |
| Enabled this session | — | — | — |
| Blocked — injection format | — | — | ✋ yes — change injection format and re-run Step 6A |
| Deferred — Monaco-managed | — | — | ✋ yes — update config-as-code repository |
| Deferred — Cordova | — | — | ✋ yes — support pending |
| Proposed for deletion | — | — | ✋ yes — not on Grail; must be deleted (Step 6B) or enabled (Step 6A) first |

> Frontends proposed for deletion remain classic-only until actually removed and count as migration blockers. Run Step 6B to delete them, or revisit Step 6A to enable them instead.

**Technical readiness** (Grail-enabled frontends only):

| Frontend | Type | Latest Agent | Version OK? | Cookies Upgraded | Tech Ready? |
|---|---|---|---|---|---|
| Shop Frontend | Web | 350 | ✅ ≥ 347 | ✅ | ✅ |
| Admin Panel | Web | 312 | ❌ need ≥ 347 | ✅ | ❌ |

Remediation notes:
- **Agent below threshold (web)**: update JavaScript agent version.
- **Agent below threshold (mobile)**: publish a new app release built with SDK ≥ 8.347.
- **Cookies not upgraded**: run Step 8B-2 to apply via Settings API.
- **No traffic data**: note as "no data" rather than failing (expected on dev/test).

**Group 3 (Enhanced) RUM Readiness Verdict**

After populating both tables, output a single verdict:

> ✅ **READY** — all active frontends are on Grail and technically ready. No migration blockers remain.

or

> ❌ **BLOCKED** — \<n\> items require attention before Group 3 (Enhanced):
> - \<n1\> frontends blocked by injection format — change format and re-run Step 6A
> - \<n2\> frontends not yet on Grail (proposed for deletion or deferred) — delete or enable
> - \<n3\> frontends below agent version threshold — update OneAgent / SDK
> - \<n4\> frontends without cookie upgrade — run Step 8B-2

The verdict is ✅ only when the migration completeness table has **zero ✋ rows** AND the technical readiness table has **zero ❌ rows**. Omit zero-count lines from the ❌ list.

## Customer actions

- Review and confirm the plan in Step 5 before any changes are applied.
- **Mobile**: schedule redeployment after enablement. SDK must be at v8.309 or higher.
- **Web (agentless/manual injection)**: update and redeploy the instrumentation snippet if OneAgent auto-update is not active.
- **Config-as-code (Monaco / Terraform)**: update repository to set `rum.enabledOnGrail: true` (and SR fields) before the next pipeline run.
- Monitor Experience Vitals after enablement to confirm data arrives within 30–60 minutes.

## Outcome

| Frontend | Type | RUM on Grail | SR on Grail | Notes |
|---|---|---|---|---|
| Shop Frontend | Web | Enabled | Enabled | Validated — events arriving |
| Admin Panel | Web | Already enabled | — | Skipped |
| Legacy Portal | Web | — | — | Deleted (user confirmed) |
| Mobile App | Mobile | Enabled | Enabled | Redeployment required |
| Custom App | Custom | — | — | Deferred |

## Notes

- **Environment targeting**: run enablement against a non-production tenant first before touching production.
- **Cordova**: defer and list explicitly. Support is planned but not released.
- **Custom apps**: list in the plan output but take no action. Do not suggest migrating to web or mobile types as a workaround.
- **Group 3 (Enhanced) readiness**: covered in Step 8. Agent version thresholds (web ≥ 347, mobile SDK ≥ 8.347) are read from `user.events`; cookie upgrade status from Settings API (`builtin:rum.web.rum-cookies-upgrade`).

## References

- [Transition from RUM Classic](https://docs.dynatrace.com/docs/observe/digital-experience/rum/transition-from-rum-classic)
- [Enable new RUM for web apps](https://docs.dynatrace.com/docs/observe/digital-experience/rum/web-frontends/initial-setup/enable-new-rum-for-web-apps)
- [Injection snippet formats](https://docs.dynatrace.com/docs/observe/digital-experience/rum/web-frontends/initial-setup/snippet-formats)
- [Android initial setup](https://docs.dynatrace.com/docs/observe/digital-experience/rum/mobile-frontends/android/id-01-initial-setup)
- Settings schemas: `builtin:rum.web.name`, `builtin:rum.web.enablement`, `builtin:rum.mobile.name`, `builtin:rum.mobile.enablement`, `builtin:rum.custom.name`, `builtin:rum.web.rum-cookies-upgrade`
