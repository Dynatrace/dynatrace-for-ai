/**
 * Detection script for installed EF2 extensions still on Gen2 entity
 * extraction: lists every installed extension with its version, classifies
 * hub vs non-hub, and returns the set for the caller to compare against
 * extension-min-version.csv.
 *
 * Runs inside the Dynatrace JS runtime via `dtctl exec function -f`. Uses
 * typed SDK clients rather than raw fetch or shelling out to `dtctl` --
 * both clients below are public (`@dynatrace-sdk/*`), so this is the
 * preferred path per `dt-js-runtime/references/fetch.md`'s "prefer a typed
 * client" rule.
 *
 * Uses the platform Extensions 2.0 client (`@dynatrace-sdk/client-extensions-v2`,
 * scope `extensions:definitions:read`), not the classic
 * `extensions_2_0Client` (`@dynatrace-sdk/client-classic-environment-v2`) --
 * the platform client is what `ef2-entity-extraction.md`'s Prerequisites
 * already declares a scope for, and it is the one to extend when the
 * upgrade-ef2-extension.ts remediation script needs write access
 * (`installExtension`, `updateExtensionEnvironmentConfiguration`) to the same
 * resource. Aliased to `platformExtensionsClient` because the hub SDK below
 * exports a same-named `extensionsClient`.
 *
 * Interactive equivalent for a human at a terminal:
 *   dtctl get extensions
 *   dtctl get hub-extensions --filter <name>
 *
 * Read-only: does not install, upgrade, or otherwise mutate anything.
 * Detecting a below-minimum version is not the full job -- after any version
 * bump, the new version still needs activating in the environment and
 * existing `extension-configs` tied to the old version still need migrating.
 * Those are separate, later steps handled by `upgrade-ef2-extension.ts` and
 * are not performed by this script.
 */

import { extensionsClient as platformExtensionsClient } from '@dynatrace-sdk/client-extensions-v2';
import { extensionsClient as hubExtensionsClient } from '@dynatrace-sdk/client-hub';

/** Custom (non-Hub) extension names are prefixed `custom:` -- with a colon,
 * not a dot. EF1 plugin type IDs use `custom.` (a dot) instead; see
 * find-ef1-plugins.ts's `CUSTOM_PREFIX` for the EF1 side.
 *
 * Backend-enforced for the "custom" extension type, not cosmetic -- but
 * that type only strongly implies customer authorship, it doesn't
 * guarantee it. See classify below.
 */
const CUSTOM_NAME_PREFIX = 'custom:';

interface ExtensionEntry {
  extensionName: string;
  /** Highest version installed in the environment (may not be active). */
  latestInstalledVersion: string;
  /** Version actually active in the environment; null if none is active.
   * Gen3 readiness depends on this, not on latestInstalledVersion -- an
   * extension can have a newer version uploaded but not yet activated. */
  activeVersion: string | null;
  /** Name carries the `custom:` prefix (backend-enforced for the "custom"
   * type) -- strongly, not absolutely, implies customer authorship. */
  custom: boolean;
  /** Present in the Hub catalog, so the Instructions step-3 upgrade path is
   * usable for it. */
  onHub: boolean;
  /** Routing decision: true only when unprefixed and catalogued. Dynatrace
   * manages the artifact and step 3 applies. */
  hub: boolean;
}

export default async function () {
  const installed = await listInstalledExtensions();
  const hubIds = await listHubExtensionIds();

  const entries: ExtensionEntry[] = installed.map((ext) => ({
    extensionName: ext.extensionName,
    latestInstalledVersion: ext.version,
    activeVersion: ext.activeVersion,
    ...classify(ext.extensionName, hubIds),
  }));

  return {
    scanned: entries.length,
    entries,
  };
}

/**
 * custom -- backend-enforced for the "custom" type; strongly, not
 *   absolutely, correlated with customer authorship (Dynatrace could in
 *   principle publish a custom-type extension to Hub). `com.dynatrace.`
 *   isn't a safe "official" test either (e.g. `com.dynatrace.custom.*`
 *   exists and isn't on Hub).
 * onHub  -- Hub-catalog membership: presence means Dynatrace distributes
 *   the artifact and Instructions step 3 applies.
 *
 * `hub` trusts `custom` over `onHub` when they disagree -- the safe default
 * for an upgrade skill: a false "needs manual check" only costs extra
 * verification, a false "Hub-managed" could skip it.
 */
function classify(
  extensionName: string,
  hubIds: Set<string>,
): { custom: boolean; onHub: boolean; hub: boolean } {
  const custom = extensionName.startsWith(CUSTOM_NAME_PREFIX);
  const onHub = hubIds.has(extensionName);
  return { custom, onHub, hub: !custom && onHub };
}

interface InstalledExtension {
  extensionName: string;
  version: string;
  activeVersion: string | null;
}

/**
 * Lists every installed extension, paginating through the full result set.
 * `listExtensions` defaults to pageSize 20 (max 100) -- fetching only the
 * first page would silently truncate any tenant with more than 20 installed
 * extensions. Per the API contract, once `pageKey` is supplied every other
 * query parameter must be omitted, so the first call and follow-up calls are
 * built differently below.
 */
async function listInstalledExtensions(): Promise<InstalledExtension[]> {
  const entries: InstalledExtension[] = [];
  let pageKey: string | undefined;

  do {
    const page = pageKey
      ? await platformExtensionsClient.listExtensions({ pageKey })
      : await platformExtensionsClient.listExtensions({ pageSize: 100, addFields: 'activeVersion' });

    for (const item of page.items) {
      entries.push({
        extensionName: item.extensionName,
        version: item.version,
        activeVersion: item.activeVersion ?? null,
      });
    }

    pageKey = page.nextPageKey ?? undefined;
  } while (pageKey);

  return entries;
}

/**
 * Hub catalog membership, by extension id. `onlyCompatible: false` is
 * required -- the default restricts results to extensions compatible with
 * this tenant's current version, which would misclassify a Hub extension
 * that is incompatible (e.g. below the tenant's minimum) as non-hub/custom.
 * Those are exactly the extensions this scan exists to catch, so silently
 * excluding them from the Hub set would defeat the purpose. Verified live:
 * `Overview.id` is the extension name and `Overview.type` discriminates item
 * kinds via the literal `'EXTENSION_2'`.
 */
async function listHubExtensionIds(): Promise<Set<string>> {
  const overview = await hubExtensionsClient.getExtensionOverviewList({ onlyCompatible: false });
  const ids = overview.items.filter((item) => item.type === 'EXTENSION_2').map((item) => item.id);
  return new Set(ids);
}
