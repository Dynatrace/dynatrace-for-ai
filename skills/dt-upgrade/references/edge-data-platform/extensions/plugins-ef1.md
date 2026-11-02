# DT Plugins (EF1)

**Gen3 replacement**: EF2 (via Hub equivalent, or custom rebuild)

**Phase 2 required**: no

## What changes

Extension Framework 1.0 ("DT Plugins" -- Python and JMX/PMI monitoring
extensions) is deprecated in favor of EF2. There is no automatic migration:
customers with a public/Hub-downloaded EF1 plugin must find and install its
EF2 equivalent on Hub; customers with a custom-built EF1 plugin must rebuild
it as an EF2 extension.

**Scope of this reference: customer-authored ("custom") EF1 plugins only.**
Built-in plugins (Dynatrace-shipped, not uploaded by the customer) are out of
scope pending a separate follow-up epic -- their lifecycle (global enable
state vs. per-instance configuration vs. actual active use) is materially
more complex and not yet well enough understood to give reliable migration
guidance.

## Contents

- [Prerequisites](#prerequisites)
- [Instructions](#instructions)
- [Customer actions](#customer-actions)
- [Examples](#examples)
- [Outcome](#outcome)
- [Validation](#validation)
- [References](#references)

## Prerequisites

- `dtctl` authenticated against the customer's tenant, or an equivalent
  in-app context for the browser path below.
- `legacy-plugins:configs:read` on the token/app used for detection -- the
  reserved endpoint enforces this scope regardless of transport; the runtime
  injects *credentials* for a relative fetch, not *authorization*. Without this scope, the detection script fails with `403 ... "missingScopes":["legacy-plugins:configs:read"]`.
- `app-engine:functions:run` to execute the detection script at all
  (`dtctl exec function`).

## Instructions

1. Run the bundled detection script. It reads classic Config v1 through the
   reserved, CORS-safe route and is read-only:

   ```bash
   dtctl exec function -f scripts/find-ef1-plugins.ts
   ```

   The script runs inside the Dynatrace JS runtime, which injects
   credentials for the relative fetch automatically -- it needs no token of
   its own, only an authenticated `dtctl` context pointing at the customer's
   tenant with the `legacy-plugins:configs:read` scope above (credentials and
   authorization are separate; the runtime handles only the former). It uses
   a raw relative fetch rather than a typed SDK client, because the one
   typed client for this endpoint (`getPlugins`) ships in a private package
   that external customers cannot install.
   The relative fetch needs no package install and works identically
   whether a customer or a Dynatrace support engineer is the one running it
   against the customer's tenant.

   It returns `scanned` (all plugin entries -- the endpoint's response is a
   flat `{ extensions: [...] }` list, not grouped by scope), `custom` (the
   subset whose `id` is prefixed `custom.*`), and `entries` (`id`, `name`,
   and `kind` -- the datasource type, e.g. `JMX`, `ONEAGENT` for Python,
   `ACTIVEGATE` -- per matching plugin).

2. **Browser/Dynatrace-App alternative.** If the agent is running inside a
   Dynatrace App rather than a CLI session, direct calls to
   `/api/config/v1/plugins` are blocked by CORS from the apps domain (`*.apps.dynatrace.com`).
   The same data is reachable CORS-safely at
   `GET /platform-reserved/classic-config/v1/plugins` -- this is the exact
   endpoint `find-ef1-plugins.ts` already calls, so no separate tooling is
   needed; just note that both contexts resolve to the same detection path.

3. **No results** (`custom: 0`) -- say so plainly and stop:

   > No customer-authored EF1 plugins found. No action needed for this area.

4. **Results returned** -- report the count, then one row per plugin (id,
   name, kind). Then classify each:

   - **JMX-type plugins** with a Hub equivalent -- point to the Hub EF2
     extension. Finding the candidate: extract the technology token from
     the plugin's `id` (e.g. `custom.jmx.<technology>`) and search Hub
     with it -- `dtctl get hub-extensions --filter <technology>`, which
     matches name/ID/description substrings. Hub's JMX family is
     namespaced `com.dynatrace.extension.jmx-<technology>`, so
     `--filter jmx` narrows to the whole family if the technology token
     alone is ambiguous or returns nothing. `dtctl` cannot search Hub
     `keywords` -- if the technology-token search misses, widen with
     `@dynatrace-sdk/client-hub`'s `getExtensionOverviewList()` (runs
     inside `dtctl exec function`) and match client-side against each
     result's `keywords[]`/`description`, then check `Detail.relatedItems`
     for neighbors of the closest hit. This is only ever a suggestion, not
     a mandate: there is no automatic migration, no metric-level
     equivalence data exists in the Hub catalog to verify a match
     programmatically, and the reference must not imply EF2 adoption is
     forced for JMX specifically any more than for EF1 generally.
   - **Custom plugins with no Hub equivalent** -- point to the VS Code EF2
     migration tooling, or the Extensions Creator app's browser-based JMX
     Browser for JMX-shaped plugins (see Customer actions).

   Ask before proceeding to remediation; this reference only detects and
   advises, it does not migrate anything automatically.

5. **Check for the sibling EF2 migration track.** Once this reference's
   findings are resolved, continue with
   [ef2-entity-extraction.md](ef2-entity-extraction.md) -- if the tenant also
   runs EF2 extensions below the Smartscape2 version threshold, that track is
   commonly needed alongside this one.

## Customer actions

- **Public/Hub-equivalent plugins**: find the EF2 equivalent on Dynatrace
  Hub, then verify it collects the same data before removing the EF1
  plugin. **Disclaimer:** the suggested equivalent is based on a shallow
  name/keyword match, not verified feature parity -- the customer must
  confirm it actually covers what they need. Once you have a candidate
  extension ID, **offer** to install and
  activate it via `upgrade-ef2-extension.ts` -- this is optional, not a
  requirement; the customer may prefer installing manually via the
  Extensions UI instead:

  ```bash
  dtctl exec function -f scripts/upgrade-ef2-extension.ts \
    --payload '{"extensionName":"<hub-extension-id>"}'
  ```

  Omitting `version` installs the Hub-recommended version, and once
  `"apply":true` runs, the version actually installed is resolved
  automatically and used to activate it -- there is no minimum-version
  requirement to target here, since this is a first-time install, not a
  version bump (see ef2-entity-extraction.md's Instructions, steps 3 and 5,
  for what install+activate do under the hood). Config migration needs its
  own separate consent flag (`migrateConfigsConsent`) and defaults to
  skipped, which is what you want here anyway -- there's nothing to migrate
  for a never-before-installed extension. Same dry-run-by-default gate as
  elsewhere: run without `"apply":true` first to show the plan, and don't
  remove the EF1 plugin until the new extension is verified to be collecting
  the expected data.
- **Custom plugins with no Hub equivalent**: rebuild as an EF2 extension.
  Two paths, pick whichever fits:
  - **VS Code Extensions 2.0 development tooling** -- full control, works
    for any extension shape, and is the only path for Python plugins (the
    Extensions Creator app below does not support the Python datasource).
    The add-on provides dedicated commands for each source type -- there is
    no CLI converter, only these VS Code commands:
    - **Convert JMX**: source is `plugin.json` or a `.zip`, output is
      `extension/extension.yaml`. Before converting, enable **Java Metric
      Extensions (JMX)** under Settings > Preferences > OneAgent features
      and restart the monitored Java processes; initialize the workspace
      with schema version **1.275.0** and project type **JMX 1.0
      Conversion**.
    - **Convert Python**: turns `plugin.json` into `activationSchema.json`;
      the plugin's code then moves into `__main__.py` inside the
      `ExtensionImpl` class, with `self.config` becoming
      `self.activation_config`, `report_custom_info_event` becoming
      `self.report_dt_event`, and metrics reported via `self.report_metric()`.
  - The **Extensions Creator** app (`dynatrace.custom.extensions.creator-app`)
    -- a browser-based, no-install alternative with a JMX Browser for
    exploring MBeans/attributes on JMX-shaped custom plugins. Its own docs
    describe no dedicated v1-migration feature; use it for authoring a new
    EF2 extension from scratch (via Import or Upload from file), not as a
    v1-conversion tool specifically.
- Remove the EF1 plugin only after its EF2 replacement is verified to be
  collecting the expected data.

## Examples

### Discovery, zero results

Script output: `{ "scanned": 12, "custom": 0, "entries": [] }` (all 12 are
built-in, not customer-authored).

→ No customer-authored EF1 plugins found. No action needed for this area.

### Mixed JMX and custom findings

Script output:

```json
{
  "scanned": 15,
  "custom": 3,
  "entries": [
    { "id": "custom.jmx.legacy-cache-monitor", "name": "Legacy Cache Monitor", "kind": "JMX" },
    { "id": "custom.python.internal-billing-poller", "name": "Internal Billing Poller", "kind": "ONEAGENT" },
    { "id": "custom.jmx.old-queue-depth", "name": "Old Queue Depth", "kind": "JMX" }
  ]
}
```

→ Three customer-authored EF1 plugins found:

| Plugin | Kind | Suggested path |
|---|---|---|
| `custom.jmx.legacy-cache-monitor` | JMX | Check Hub for a JMX-based EF2 equivalent; if none, rebuild via VS Code tooling or the Extensions Creator JMX Browser |
| `custom.python.internal-billing-poller` | ONEAGENT (Python) | No Hub equivalent expected for an internal-billing plugin -- rebuild via VS Code tooling |
| `custom.jmx.old-queue-depth` | JMX | Check Hub for a JMX-based EF2 equivalent; if none, rebuild via VS Code tooling or the Extensions Creator JMX Browser |

→ Ask the customer which they'd like to tackle first before proceeding.

### Fully migrated

Re-running the script after remediation returns `{ "scanned": 12, "custom": 0, "entries": [] }`.

→ All customer-authored EF1 plugins have been migrated to EF2.

## Outcome

Zero customer-authored EF1 plugins remain (`custom: 0` from
`find-ef1-plugins.ts`). Output a summary table per plugin found during the
session:

| Plugin | Kind | EF2 path | Status |
|---|---|---|---|
| `custom.jmx.legacy-cache-monitor` | JMX | Hub equivalent | Migrated |
| `custom.python.internal-billing-poller` | ONEAGENT (Python) | Custom rebuild (VS Code) | In progress |

## Validation

Re-run the detection script:

```bash
dtctl exec function -f scripts/find-ef1-plugins.ts
```

Remediation is complete when the response shows `custom: 0`.

## References

- [ef2-entity-extraction.md](ef2-entity-extraction.md) -- if the tenant also
  runs EF2 extensions below the Smartscape2 version threshold, load this
  sibling reference; both migration tracks are commonly needed together.
- [Extensions Creator](https://docs.dynatrace.com/docs/ingest-from/extensions/develop-your-extensions/custom-extensions-creator) -- browser-based extension authoring, including the JMX Browser. The old `extend-dynatrace/extensions20/extensions-creator` URL now 404s; this is the canonical one.
- [Extensions 2.0 VS Code development](https://docs.dynatrace.com/docs/extend-dynatrace/extensions20/tutorial) -- full VS Code tooling for building EF2 extensions.
- [Migrate JMX extensions](https://docs.dynatrace.com/docs/ingest-from/extensions/develop-your-extensions/addon-for-vscode/guides/jmx-conversion) and [Migrate Python extensions](https://docs.dynatrace.com/docs/ingest-from/extensions/develop-your-extensions/addon-for-vscode/guides/python-migrate) -- the VS Code add-on guides behind the **Convert JMX** / **Convert Python** steps noted in Customer actions.
