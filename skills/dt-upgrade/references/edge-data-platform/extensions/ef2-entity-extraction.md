# EF2 Entity Extraction (Smartscape2 Readiness)

**Gen3 replacement**: Extension OpenPipeline entity extraction (Smartscape2)

**Phase 2 required**: no

## What changes

This is a phase/platform-compliance check for EF2 (Extensions 2.0)
extensions, not just an OpenPipeline migration note. Two tracks:

1. **Official (Hub) extensions** -- installed version is compared against a
   per-extension minimum version table. Below the minimum: upgrade via the
   Extensions UI, or let the skill do it -- `upgrade-ef2-extension.ts`
   (Instructions, step 3) installs and activates behind one consent gate, and
   migrates configs behind a second, separate consent gate. Dynatrace manages
   the artifact for Hub extensions either way.
2. **Non-hub (custom) extensions** -- there is no central authority tracking
   their platform-readiness status, so both version *and* artifact contents
   (entity extraction, dashboards, alerting, primary tags) are checked
   directly against the archive.

**Distinguishing hub vs custom extensions.** `custom:` is backend-enforced
for the "custom" extension type -- strongly, not absolutely, tied to
customer authorship. `list-ef2-extensions.ts` trusts the prefix over Hub
membership when they disagree, favoring extra manual verification over a
false "Hub-managed" read -- see the script for details.

> **REQUIRED:** Load [extension-min-version.csv](extension-min-version.csv)
> before comparing versions -- it is the authoritative per-extension minimum
> version table. It currently carries one worked example row; the full set
> is still being filled in. Do not duplicate its contents
> as a markdown table here -- keeping the same lookup data in both a data
> file and a markdown table has caused real drift bugs.

## Contents

- [What still needs migrating](#what-still-needs-migrating)
- [Prerequisites](#prerequisites)
- [Instructions](#instructions)
- [Customer actions](#customer-actions)
- [Examples](#examples)
- [Outcome](#outcome)
- [Validation](#validation)
- [References](#references)

## What still needs migrating

For each installed custom EF2 extension, identify which classic artifact
forms are still present in the package. A classic form absent means nothing
to migrate; a classic form present means the developer must convert it before
Phase 3. Probe the archive with `inspect-ef2-artifact.ts` (Instructions,
step 4) -- the script reports `needs-migration`, `ok`, or `manual-check`
per area.

### Topology / entity extraction

The classic topology block (`topology:` at the root of `extension.yaml`,
the old declarative Smartscape topology) must be converted to OpenPipeline
entity extraction (Smartscape 2.0).

- **Classic topology absent** → OK, no migration needed for this area.
- **Classic topology present, no `openpipeline:` node** → needs migration.
  Use VS Code "Create Smartscape Topology" to generate the OpenPipeline
  source and pipeline files and wire the `openpipeline:` node into the
  manifest.
- **Classic topology present alongside `openpipeline:` node** → migration
  in progress. Verify extraction works, then remove the classic `topology:`
  block.

When an `openpipeline:` node is present (either from conversion or original
authoring), also verify:

- `minDynatraceVersion: 1.330` or higher is set -- this gates whether the
  `openpipeline:` node can exist at all. `1.345` or higher is additionally
  required for Smartscape 2.0 node/edge extraction to actually function; an
  extension between the two thresholds has the node present but extraction
  that does not work. Check both thresholds, not just the lower one.
- A matching `*.source.json` (`staticRouting.pipelineId` matches the
  pipeline's `customId`) and `*.pipeline.json` (`customId` matches) exist.
  A `pipelineId`/`customId` mismatch is a common VS Code conversion bug --
  the script checks this mechanically.
- Every `extractNode: true` processor includes the `fieldsToExtract` base
  set (`id_classic`, `primary_tags.*` via `startsWith`) and a
  `staticEdgesToExtract` key, even if empty (`[]`).
- Every `extractNode: true` processor extracts `dt.security_context` --
  without it, entities from this extension are invisible to security-scoped
  views and RBAC-filtered queries.

### Unified Analysis (UA) screens

There are three UA generations: (1) classic Angular screens (top-level
`screens:` in `extension.yaml`; supports every card type except `DqlTable`),
(2) the same card model ported to run on platform (individual cards marked
`target: PLATFORM` or `BOTH` inside the classic `screens:` block; adds
`DqlTable` support but drops a few 2nd-gen card types), and (3) the new
document-based screens (`documents.screens` -- a plain `{path:
screens/<name>.screen.json}` list, structurally identical to
`documents.dashboards`). Phase 3 readiness means generation 3.

- **Classic `screens:` absent** → OK, no migration needed for this area.
- **Classic `screens:` present, no `documents.screens` entries** → needs
  migration. Use VS Code "Convert Screens" to generate them.
- **Both present** → migration in progress; verify the converted screens,
  then remove the classic `screens:` block.

When converting, "Convert Screens" does not have an equivalent for
breadcrumbs, entity/metric tables, or events/logs/problems cards, and skips
any card whose `target:` is `CLASSIC`-only entirely -- these must be ported
manually; check for them before telling the customer a screen is fully
migrated.

### Dashboards

- **Classic dashboards absent** (no top-level `dashboards:` list with bare
  `path:` entries) → OK.
- **Classic dashboards present, no document dashboards** → needs migration
  to document dashboards: a top-level `documents:` node with a `dashboards:`
  list, each entry with `displayName` + `path` pointing at a
  `*.dashboard.json` file.
- **Both forms present** → complete the migration and remove the classic
  form. Document dashboards alone are not sufficient if the classic form
  remains alongside.

  ```yaml
  dashboards:               # classic form -- must be absent after migration
    - path: dashboards/f5_status.json

  documents:                 # platform form
    dashboards:
      - displayName: F5 Status
        path: documents/f5-status.dashboard.json
  ```

### Alerting

- **Classic metric-event alerts absent** (no top-level `alerts:` list with
  bare `path:` entries to metric-event JSON) → OK.
- **Classic metric-event alerts present, no `alertTemplates:`** → needs
  migration to Davis anomaly detectors: a top-level `alertTemplates:` list
  of DQL-based detectors with `title`, `description`,
  `executionSettings.queryOffset`, `analyzer.name` (a fully-qualified
  analyzer class) with `analyzer.input.{query,threshold,alertCondition,
  alertOnMissingData,violatingSamples}`, and
  `eventTemplate.{event.type,event.name,event.description}`.
- **Both forms present** → complete the migration and remove the classic
  form.

  ```yaml
  alerts:                     # classic form -- must be absent after migration
    - path: alerts/f5_cpu_high.json

  alertTemplates:              # platform form -- DQL-based, not metric-selector-based
    - title: "F5 LTM - Instance High CPU"
      analyzer:
        name: "dt.statistics.ui.anomaly_detection.StaticThresholdAnomalyDetectionAnalyzer"
        input:
          query: "timeseries avg(...)"
          threshold: 90
          alertCondition: "ABOVE"
  ```

### Primary tags (declarative and Python extensions)

- Every entity type in `topology.types` has a rule extracting
  `primary_tags.*` (declarative extensions).
- Every `extractNode: true` processor includes `primary_tags.*` with a
  `startsWith` strategy in `fieldsToExtract` (OpenPipeline extensions).
- Python extensions propagate primary tags via the Python code and the
  schema -- do not propose adding them per endpoint: primary tags are
  added automatically at the global level for Python extensions, unlike
  declarative datasources, which get them at both the endpoint and global
  level.
- **Why this matters:** missing primary tags make entities unfilterable in
  the I&O and DB apps -- that's what generates customer support tickets.

If any section above shows `needs-migration`: Hub extensions -- upgrade via
the Extensions UI or scripted path in Instructions, since Dynatrace manages
the artifact. Non-hub/custom extensions -- the artifact must be updated by
its developer.

## Prerequisites

- Tenant on a Dynatrace version supporting Smartscape2.
- `dtctl` authenticated against the customer's tenant.
- Scopes, by what you're running:
  - **Detection** (`list-ef2-extensions.ts`) -- `extensions:definitions:read`
    (installed and active versions) and `hub:catalog:read` (Hub
    classification).
  - **Running any `dtctl exec function` script at all** --
    `app-engine:functions:run`.
  - **Remediation, dry-run** (`upgrade-ef2-extension.ts`, the default) --
    `extensions:definitions:read` (reads the current active version) and
    `extensions:configurations:read` (lists existing monitoring
    configurations, to report which ones *would* be migrated). Dry-run
    still reads live state to build an accurate plan, it just doesn't
    write -- `hub:catalog:read` is **not** needed here, that scope is only
    used by `list-ef2-extensions.ts`.
  - **Remediation, apply mode** -- additionally
    `extensions:definitions:write` (install + activate) and
    `extensions:configurations:write` (config migration).
  - **Optional cleanup** (removing an old extension version, see
    Instructions step 7) -- `extensions:definitions:write`, the same scope
    apply mode already needs.

  Flagging a real gap seen elsewhere in this same epic's work: the readiness
  dashboard's `app.config.ts` currently declares `scopes: []`, meaning none
  of these were requested there -- verify they're present for whatever
  context runs the scripts below before assuming detection or remediation
  will succeed.

## Instructions

1. **List installed extensions and classify hub vs non-hub.** Scripted:

   ```bash
   dtctl exec function -f scripts/list-ef2-extensions.ts
   ```

   The script imports the platform `extensionsClient`
   (`@dynatrace-sdk/client-extensions-v2`) for versions -- both the version
   currently installed and the version actually active in the environment --
   and `@dynatrace-sdk/client-hub`'s `extensionsClient` for Hub
   classification -- both public SDKs, preferred over shelling out per
   `dt-js-runtime/references/fetch.md`'s "prefer a typed client" rule.
   Interactive equivalent for a human at a terminal:

   ```bash
   dtctl get extensions
   dtctl get hub-extensions --filter <name>
   ```

   Document both paths when explaining this step -- an agent may run either.

2. **Compare each installed version against the minimum-version table.**
   Load [extension-min-version.csv](extension-min-version.csv) (see the
   `> **REQUIRED:**` note above) and look up each extension by ID. If it's
   not yet in the table, say so explicitly rather than assuming compliance --
   the table is still being populated. Compare against the **active**
   version, not just the highest installed one -- an extension can have a
   newer version uploaded but never activated, which still leaves it
   non-compliant.

3. **Hub extensions below the threshold** -- three equivalent paths, in order
   of how much the skill can do without the customer:

   - Manually, via the Extensions UI.
   - Manually via `dtctl`, install only:
     ```bash
     dtctl create extension --hub-extension <extension-id> --version <required-version>
     ```
     This wraps the Extensions 2.0 API's install-from-Hub endpoint, but only
     installs -- it does not activate the version in the environment or
     migrate monitoring configs (steps 5 and 6 below still apply).
   - Scripted, with customer consent: `upgrade-ef2-extension.ts` (step 5) runs
     install and activation together behind a dry-run-by-default gate; config
     migration (step 6) runs only with a second, separate consent flag.

   Dynatrace manages the artifact for Hub extensions either way; no
   customer-side content changes are needed, only the install/upgrade action
   itself.

   **If install fails with "Registered versions of `<name>` does not
   contain the requested version `<v>`"** -- the min-version table's value
   has not yet been published to Hub for this tenant. Verified live: neither
   `dtctl describe extension` (lists only locally-installed versions) nor
   `dtctl get hub-extensions --filter <name>` (returns only catalog
   membership -- id/name/type/description, no version list) can tell you
   what Hub will actually accept for this tenant. Probe for it instead, in
   this fixed order, retrying `upgrade-ef2-extension.ts` with `"apply":true`
   each time -- a failed install is a no-op (fails closed before activation),
   so this is safe to repeat without re-confirming with the customer on
   every attempt:

   1. The next 5 patch versions above the required minimum, lowest first
      (required `4.1.3` -> try `4.1.4`, `4.1.5`, `4.1.6`, `4.1.7`, `4.1.8`),
      stopping at the first one that installs.
   2. If none of those 5 succeed, one minor-version bump with patch reset
      to 0 (`4.2.0`).
   3. If that also fails, **stop probing and ask the customer**: keep
      searching further versions, or look up the actual available version
      themselves (Extensions UI version history) and say which one to
      install. Do not keep guessing indefinitely without checking in.

4. **Non-hub/custom extensions** -- version comparison alone isn't enough;
   platform readiness depends on artifact contents. **Ask the customer
   before proceeding** (this step downloads and inspects their extension
   package), then run, once per extension:

   ```bash
   node --experimental-strip-types scripts/inspect-ef2-artifact.ts <extensionName> <version>
   ```

   One extension per invocation, deliberately -- each run downloads a
   customer archive, and the consent gate above is per-extension, not a
   one-time blanket approval for the whole tenant.

   This wraps `dtctl download extension <name> --version <v> --no-agent`
   and walks the checks from [What still needs migrating](#what-still-needs-migrating)
   directly against the archive. Topology, dashboards, alerting, UA screens,
   and `dt.security_context` presence/absence are all checked mechanically;
   the converter-gap caveats (breadcrumbs, entity/metric tables, events/logs/
   problems cards, `target: CLASSIC`-only cards) still require manual
   verification once a `needs-migration` screens finding is being acted on --
   present that section of the checklist to the customer alongside the
   script's output.

   If the artifact needs converting rather than just checking, point the
   developer at the VS Code Extensions 2.0 add-on, in this order: **Create
   Smartscape Topology** -> **Convert Screens** -> **Build**. A few details
   worth knowing before advising on this:

   - Topology conversion writes
     `extension/openpipeline/{metrics,logs}.{source,pipeline}.json` and
     wires them into the manifest via a top-level `openpipeline:` node
     (`sources[].sourcePath`, `pipelines[].pipelinePath`, each tagged with a
     `configScope`). The pipeline file's `customId` must match the source
     file's `staticRouting.pipelineId` -- a mismatch here is a common
     conversion bug.
   - Every generated Smartscape node carries an `id_classic` field tying it
     back to its classic entity. This is the join key the later screens
     conversion depends on -- it must survive untouched.
   - Node naming is mechanical: uppercased, `:` and `-` replaced with `_`
     (`cloudhub:org` -> `CLOUDHUB_ORG`). Relationships map
     `CHILD_OF`->`belongs_to`, `RUNS_ON`->`runs_on`,
     `INSTANCE_OF`->`instance_of`, `PART_OF`->`is_part_of`, `CALLS`->`calls`,
     `SAME_AS`->`same_as`.
   - Screens conversion is not exhaustive -- it skips anything targeting
     `CLASSIC`, plus breadcrumbs, entity tables, and events/logs/problems
     cards. "Converted" is not the same as "complete"; say so when handing
     results to the customer.

5. **Activate the new version in the environment.** A version upgrade alone
   doesn't finish the job, and **there is no `dtctl` command for this step**
   -- `dtctl create extension` only installs; it doesn't set which version is
   active. Use the platform SDK instead:

   ```bash
   dtctl exec function -f scripts/upgrade-ef2-extension.ts \
     --payload '{"extensionName":"<name>","version":"<required-version>","apply":true}'
   ```

   which calls `updateExtensionEnvironmentConfiguration` (or
   `activateExtensionEnvironmentConfiguration` if no version has ever been
   active for that extension yet) -- `extensions:definitions:write`. Run
   without `"apply":true` first to see the plan before writing anything.

6. **Follow-up, not skippable: migrate `extension-configs` after any version
   bump.** Once the new extension version is active (step 5), enumerate
   **all** monitoring configurations whose version is below `<required-version>`
   -- this includes configs that predate the previous active version, not
   just configs pointing to it. **Ask the customer before applying this** --
   migrating configs changes what an active monitoring configuration points
   at, the same consent bar as step 4's artifact download. If the customer
   would rather migrate configs themselves later, tell them the recipe below
   and stop; do not run it on their behalf without that go-ahead.

   ```bash
   # Find all configs below the required minimum (client-side filter by version field)
   dtctl get extension-configs <name> -o json \
     | jq '[.[] | select(.value.version | . != null and (split(".") | map(tonumber)) < ("<required-version>" | split(".") | map(tonumber)))]'
   dtctl describe extension-config <name> --config-id <id> -o yaml   # keep the objectId
   dtctl apply extension-config <name> -f <file> --dry-run             # preview
   dtctl apply extension-config <name> -f <file>                       # apply
   ```

   `dtctl apply extension-config` **updates** the existing configuration when
   the file has an `objectId`, and **creates** a new one when it doesn't --
   for migration you always want update, so never drop `objectId` from the
   file you edit. Validate the migrated payload against the target version's
   schema first if unsure: `dtctl describe extension <name> --version <v>
   --monitoring-configuration-schema`. `upgrade-ef2-extension.ts` (step 5) can
   run this migration as its third phase, but only behind a second, separate
   consent flag -- pass `"migrateConfigsConsent":true` in its payload once the
   customer has agreed to this step specifically, not just to install/activate:

   ```bash
   dtctl exec function -f scripts/upgrade-ef2-extension.ts \
     --payload '{"extensionName":"<name>","version":"<required-version>","apply":true,"migrateConfigsConsent":true}'
   ```

   It migrates all configs below the target version, not just those on the
   previous active version. Omitting `migrateConfigsConsent` (the default)
   runs install+activate only and leaves config migration for later or for
   the manual recipe above.

   Ordering matters: a configuration can't reference a version that doesn't
   yet exist and isn't yet active in the environment, so this step always
   comes after step 5, never before.

   **A version bump can break the config's payload schema, not just its
   version field** -- some extensions change what a monitoring
   configuration accepts between versions ("activation schema" changes). If
   `dtctl apply extension-config` or the script's migrate-configs phase
   rejects a config, don't assume the version field alone is wrong. In
   order of how fast each is to check: (1) read the validation error
   message -- it usually names the offending field; (2) compare
   `dtctl describe extension <name> --version <old-version>
   --monitoring-configuration-schema` against the same command for
   `<required-version>` to see exactly what changed; (3) check the
   extension's release notes as a fallback when the schema diff alone
   doesn't explain the failure. Adjust the payload for whatever changed,
   then retry.

   **Also check for management-zone-scoped configs.** A monitoring
   configuration whose `scope` field references a management zone becomes
   orphaned when management zones are removed in Phase 3. Detect them:

   ```bash
   dtctl get extension-configs <name> -o json \
     | jq '[.[] | select(.scope | test("management_zone"; "i")) | {objectId, scope}]'
   ```

   If any are found, **do not re-scope them now** -- re-scoping requires
   knowing what the management zone's discriminator becomes (a primary tag,
   a Grail bucket, or an IAM policy), which depends on the MZ migration
   outcome. Instead, **work through [`management-zones.md`](../../platform/management-zones/management-zones.md)
   first**, then return to this step once the MZ replacement is understood.
   This is a prerequisite, not just a "see also": the config cannot be
   correctly re-scoped until the MZ migration decision is made.

   > A management-zone-scoped config's `scope` field has the
   > form `management_zone-<zone-name>` (e.g. `management_zone-that-is-that`).

   **Once all three phases (install/activate/migrate-configs) report `done`,
   go straight to step 7** -- check whether the old version is now
   unreferenced and propose removing it. Don't stop at "upgrade complete"
   and wait for the customer to ask; this is the natural close of the flow,
   not a separate errand.

7. **Optional cleanup: propose removing the old extension version.** Once
   `dtctl get extension-configs <name> -o json | jq '[.[] | select(.value.version | . != null and (split(".") | map(tonumber)) < ("<required-version>" | split(".") | map(tonumber)))]'`
   returns an empty array -- or the extension had no configs below the
   required version to begin with --
   the old version is no longer referenced by anything. Propose removing it
   to the customer; do not delete it unprompted. **There is no `dtctl`
   command for this either** -- `dtctl delete` does not support the
   `extension` resource -- so use the SDK's `deleteExtensionVersion`:

   ```bash
   dtctl exec function --code 'import { extensionsClient } from "@dynatrace-sdk/client-extensions-v2";
   export default async function () {
     return await extensionsClient.deleteExtensionVersion({
       extensionName: "<name>",
       extensionVersion: "<old-version>",
     });
   }'
   ```

   This is a suggestion, not a required step for Phase 3 compliance -- an
   unused old version sitting installed does not block readiness, it's
   just housekeeping the customer may or may not want.

8. **Check for the sibling EF1 migration track.** Once this reference's
   findings are resolved, continue with [plugins-ef1.md](plugins-ef1.md) --
   if the tenant also has customer-authored EF1 plugins, that track is
   commonly needed alongside this one.

## Customer actions

Each action below names the recommended, deterministic path -- but the tool
used to get there is not the point of compliance. Whatever mechanism you
choose (the recommended path, the Extensions UI, or your own tooling
against the same public APIs), the **verifiable outcome** stated with each
action is what an agent or reviewer actually checks.

- Upgrade Hub extensions below the minimum version via the Extensions UI, or
  let the skill run `upgrade-ef2-extension.ts` end to end with your consent
  (Instructions, steps 3 and 5). Verifiable outcome: the extension's
  *active* environment-configuration version meets or exceeds its
  `extension-min-version.csv` threshold -- check with `dtctl get extensions`
  (column shows the active version) regardless of which tool performed the
  upgrade.
- For non-hub/custom extensions, convert whichever classic artifact forms
  are present -- entity extraction, Davis-based alerting, document
  dashboards, and primary-tag propagation. See Instructions step 4 for the
  VS Code conversion sequence (Create Smartscape Topology -> Convert Screens
  -> Build) and its gotchas. Verifiable outcome: re-running the artifact
  probe (`inspect-ef2-artifact.ts`) against the rebuilt package shows no
  `needs-migration` findings, independent of which build or upload tooling
  produced the new artifact.
- Migrate any `extension-configs` with version below `<required-version>`,
  manually via `dtctl apply extension-config` or automatically as part of
  `upgrade-ef2-extension.ts`'s third phase (Instructions, step 6).
  Verifiable outcome: `dtctl get extension-configs <name> -o json | jq '[.[] | select(.value.version | . != null and (split(".") | map(tonumber)) < ("<required-version>" | split(".") | map(tonumber)))]'`
  returns an empty array -- true whether the migration was applied via
  dtctl, the SDK, or hand-rolled API calls.
- If any monitoring configurations use a management-zone scope, resolve the
  MZ migration first (see `management-zones.md`), then re-scope them.
  Verifiable outcome: `dtctl get extension-configs <name> -o json | jq '[.[] | select(.scope | test("management_zone"; "i"))]'`
  returns an empty array.
- Optional: once no configs have a version below the required minimum,
  remove the old extension version (Instructions, step 7) -- cosmetic
  housekeeping, not required for Phase 3 compliance. Verifiable outcome:
  `dtctl describe extension <name>` no longer lists the old version under
  `availableVersions`.
- Re-run detection after each change to confirm the fix landed.

## Examples

### Custom extension with no classic content

`list-ef2-extensions.ts` output: `com.acme.custom.metrics-only` is non-hub.
Artifact probe:

```json
{
  "extensionFlavour": "declarative",
  "overallStatus": "ok",
  "findings": [
    { "name": "Topology / entity extraction", "status": "ok", "detail": "no classic topology block and no OpenPipeline extraction -- no migration needed" },
    { "name": "Dashboards", "status": "ok", "detail": "no classic dashboards (top-level `dashboards:` list) present" },
    { "name": "Alerting", "status": "ok", "detail": "no classic metric-event alerts (top-level `alerts:` list) present" },
    { "name": "UA screens", "status": "ok" }
  ]
}
```

→ No migration needed. This extension uses neither classic topology nor any
classic dashboard/alert forms. No action required before Phase 3.

### Mixed hub and custom findings

`list-ef2-extensions.ts` output:

| Extension | Hub | Active | Required | Gap |
|---|---|---|---|---|
| `com.dynatrace.extension.vmware` | yes | 2.0.1 | 2.1.0 | below minimum |
| `com.acme.custom.legacy-monitor` | no | 2.1.0 | not yet in table | unknown |
| `custom:com.acme.billing-probe` | no | 1.4.0 | not yet in table | unknown |

Artifact probe on `com.acme.custom.legacy-monitor`:

```json
{
  "overallStatus": "needs-migration",
  "findings": [
    { "name": "Topology / entity extraction", "status": "needs-migration", "classicPresent": true, "platformPresent": false, "migrationTarget": "OpenPipeline entity extraction (Smartscape 2.0)" },
    { "name": "Primary tags", "status": "manual-check", "detail": "classic topology present but no *.source.json -- verify topology.types rules extract primary_tags.*" }
  ]
}
```

→ `com.dynatrace.extension.vmware` is a Hub extension below its required
version -- upgrade via the Extensions UI.
→ `com.acme.custom.legacy-monitor` is not yet in the minimum-version table
-- say so rather than assuming compliance -- and its artifact has a classic
topology block with no OpenPipeline replacement. Advise the developer to
run "Create Smartscape Topology" in VS Code before Phase 3.
→ `custom:com.acme.billing-probe` is non-hub by name alone, regardless of
what `onHub` reports.
→ Ask the customer before running the artifact probe on any further non-hub
extension.

### Incomplete OpenPipeline conversion

Artifact probe on `com.acme.custom.half-converted` -- the `openpipeline:`
node was added to `extension.yaml`, but the `*.source.json`/`*.pipeline.json`
files were never generated (or were accidentally deleted afterward):

```json
{
  "extensionFlavour": "openpipeline",
  "overallStatus": "needs-migration",
  "findings": [
    { "name": "Topology / entity extraction", "status": "needs-migration", "classicPresent": false, "platformPresent": false, "migrationTarget": "OpenPipeline entity extraction (Smartscape 2.0)", "detail": "openpipeline: node present but missing *.source.json and *.pipeline.json -- conversion appears incomplete" },
    { "name": "minDynatraceVersion >= 1.345", "status": "ok", "detail": "1.347" },
    { "name": "Primary tags / dt.security_context", "status": "needs-migration", "detail": "openpipeline: node present but no *.source.json files found -- conversion appears incomplete" },
    { "name": "Source↔pipeline linkage", "status": "needs-migration", "detail": "cannot verify staticRouting.pipelineId ↔ customId linkage -- missing *.source.json and *.pipeline.json" }
  ]
}
```

→ The `openpipeline:` node existing is not enough on its own -- without the
source and pipeline files it references, nothing is actually extracted. Do
not report this extension as compliant. Advise the developer to finish
"Create Smartscape Topology" in VS Code, or regenerate the files if they were
removed after conversion.

### Fully remediated, including config migration

Re-running `list-ef2-extensions.ts` shows every extension's *active* version
at or above its required version. The version-below-floor jq filter against
`com.dynatrace.extension.vmware` returns an empty array (all configs were
migrated to the required version).

→ All EF2 extensions and their monitoring configurations are Phase 3 ready.

## Outcome

Output a summary table per extension:

| Extension | Hub | Active version | Required version | Status | Migrations needed |
|---|---|---|---|---|---|
| `com.dynatrace.extension.vmware` | yes | 2.1.0 | 2.1.0 | OK | — |
| `com.acme.custom.legacy-monitor` | no | 2.1.0 | not in table | Manual check | Classic topology → OpenPipeline |

## Validation

DQL is explicitly not usable for this check: `dt.entity.extension`,
`dt.entity.plugin`, and `dt.entity.extension_2_0` are recognized DQL entity
types but return zero records on verified test tenants -- there is no
`fetch extensions` table. Validation instead re-runs the same `dtctl`/SDK
commands used for detection:

```bash
dtctl get extensions -o json
dtctl get hub-extensions -o json
```

Remediation is complete when every installed extension's version meets or
exceeds its entry in `extension-min-version.csv`, the version-below-floor
jq filter returns an empty array for all upgraded extensions, and the
artifact probe (`inspect-ef2-artifact.ts`) reports no `needs-migration`
findings for any inspected custom extension.

## References

- [plugins-ef1.md](plugins-ef1.md) -- if the tenant also has
  customer-authored EF1 plugins, load this sibling reference; both migration
  tracks are commonly needed together.
- [extension-min-version.csv](extension-min-version.csv) -- authoritative
  per-extension minimum-version table.
- [management-zones.md](../../platform/management-zones/management-zones.md) --
  prerequisite when any monitoring configuration uses a management-zone scope
  (step 6); the config cannot be correctly re-scoped until the MZ migration
  decision is made.
- [Extensions migration to Smartscape 2.0, full breakdown](https://dynatrace.stackenterprise.co/articles/23636) -- the source article behind this checklist.
- [Convert topology](https://docs.dynatrace.com/docs/ingest-from/extensions/develop-your-extensions/addon-for-vscode/guides/convert-smartscape-topology) and [Convert unified analysis pages](https://docs.dynatrace.com/docs/ingest-from/extensions/develop-your-extensions/addon-for-vscode/guides/convert-ua-screens) -- the VS Code Extensions 2.0 add-on guides behind the conversion order and details noted in Instructions step 4.
