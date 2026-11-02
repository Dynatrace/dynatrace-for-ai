/**
 * Remediation script for one EF2 extension found below its minimum version
 * by list-ef2-extensions.ts. Unlike every other reference in this skill,
 * this one WRITES to the customer's environment -- get explicit customer
 * consent naming the extension and target version before applying, the same
 * way inspect-ef2-artifact.ts requires consent before downloading an
 * archive.
 *
 * Runs inside the Dynatrace JS runtime via `dtctl exec function -f`, payload
 * driven:
 *
 *   dtctl exec function -f scripts/upgrade-ef2-extension.ts \
 *     --payload '{"extensionName":"com.dynatrace.extension.vmware","version":"1.330.0","apply":true}'
 *
 * `apply` defaults to false (dry run): the script reports the three-phase
 * plan below without calling any write endpoint. Pass `"apply": true` in the
 * payload only after the customer has confirmed both the extension name and
 * the target version.
 *
 * Config migration is a second, separate consent gate -- `migrateConfigsConsent`
 * defaults to false, so `apply:true` alone only ever runs install+activate.
 * Pass `"migrateConfigsConsent":true` once the customer has separately agreed
 * to phase 3, at the same consent bar as inspect-ef2-artifact.ts's artifact
 * download; see ef2-entity-extraction.md's Instructions step 6. The manual
 * `dtctl apply extension-config` recipe there is the fallback when the
 * customer wants to migrate configs themselves, or later.
 *
 * Three phases, always in this order -- a monitoring configuration cannot
 * reference a version that does not yet exist and is not yet active, so
 * activation must happen before config migration, and installation before
 * activation:
 *
 *   1. Install the target version from Hub (`installExtension`). If `version`
 *      is omitted, the Hub-recommended version is installed, and the version
 *      actually installed (from the response) is resolved and carried into
 *      phases 2 and 3 below -- omitting `version` is a first-time-install
 *      convenience, not a way to skip activation.
 *   2. Activate it in the environment (`updateExtensionEnvironmentConfiguration`
 *      if a version is already active, `activateExtensionEnvironmentConfiguration`
 *      if none is -- e.g. right after a first-time Hub install). There is no
 *      `dtctl` command for this step; see ef2-entity-extraction.md's
 *      Instructions for why the SDK is required here specifically.
 *   3. Migrate monitoring configurations still pinned to the version that was
 *      active before this run (`updateExtensionMonitoringConfiguration`).
 *      Runs only when `migrateConfigsConsent:true` is given -- see above.
 *
 * Fails closed: a phase that errors stops the run before the next phase
 * starts, so a failed activation never leaves configs migrated to a version
 * that isn't live, a failed install never reaches activation at all, and an
 * install that cannot resolve which version it installed (no `version` given,
 * and the response doesn't name one) fails the run rather than silently
 * skipping activation.
 *
 * Equivalent manual step for phase 1 alone, if the customer prefers doing
 * only the Hub upgrade themselves and handling activation/config migration
 * through the UI: `dtctl create extension --hub-extension <id> --version <v>`.
 */

import { extensionsClient } from '@dynatrace-sdk/client-extensions-v2';

interface UpgradePayload {
  extensionName: string;
  /** Target version. Omit to install the Hub-recommended version -- the
   * version actually installed is then resolved from the install response and
   * carried into activation and config migration automatically. */
  version?: string;
  /** Perform the writes. Defaults to false (dry run, reports the plan only). */
  apply?: boolean;
  /** Consent to run phase 3 (migrate monitoring configurations to the new
   * version once it's active). Defaults to false -- config migration is a
   * separate consent decision from `apply`, at the same bar as
   * inspect-ef2-artifact.ts's artifact download (ef2-entity-extraction.md
   * step 6). `apply:true` alone only runs install+activate. */
  migrateConfigsConsent?: boolean;
}

interface PhaseResult {
  phase: 'install' | 'activate' | 'migrate-configs';
  status: 'planned' | 'done' | 'skipped' | 'failed';
  detail: string;
}

/** How many times to poll for the newly installed version to become visible
 * before giving up. `installExtension` returns 202 Accepted -- installation
 * completes asynchronously, so activation must wait for it. Bounded well
 * under the runtime's 120s execution timeout. */
const INSTALL_POLL_ATTEMPTS = 6;
const INSTALL_POLL_INTERVAL_MS = 3000;

export default async function (payload?: UpgradePayload) {
  if (!payload?.extensionName) {
    throw new Error('payload.extensionName is required, e.g. {"extensionName":"com.dynatrace.extension.vmware","version":"1.330.0"}');
  }
  // Fail loudly on the retired field name instead of silently changing
  // behaviour under it -- migrateConfigs used to default to true (config
  // migration ran unless explicitly opted out); migrateConfigsConsent
  // defaults to false (config migration runs only when explicitly opted in).
  // An agent copying an old payload snippet needs to be told, not given a
  // different default quietly.
  if (Object.prototype.hasOwnProperty.call(payload, 'migrateConfigs')) {
    throw new Error(
      'payload.migrateConfigs was renamed to migrateConfigsConsent and now defaults to false -- config migration is opt-in, a separate consent decision from apply/install/activation. Replace "migrateConfigs" with "migrateConfigsConsent" in the payload and re-run.',
    );
  }
  const { extensionName, version, apply = false, migrateConfigsConsent = false } = payload;

  const phases: PhaseResult[] = [];
  const previousVersion = await getActiveVersion(extensionName);

  const installResult = await runInstall(extensionName, version, apply, phases);
  if (installResult.outcome === 'failed') {
    return { extensionName, apply, previousVersion, phases };
  }
  // The version actually installed -- resolved from the response when
  // `version` was omitted -- is what activation and config migration must
  // target, not the (possibly undefined) payload field. See runInstall.
  const resolvedVersion = installResult.resolvedVersion;

  const activateResult = await runActivate(extensionName, resolvedVersion, previousVersion, apply, phases);
  if (activateResult === 'failed') {
    return { extensionName, apply, previousVersion, phases };
  }

  if (migrateConfigsConsent) {
    await runMigrateConfigs(extensionName, resolvedVersion, apply, phases);
  } else {
    phases.push({
      phase: 'migrate-configs',
      status: 'skipped',
      detail: 'migrateConfigsConsent:false (default) -- config migration needs its own customer go-ahead, separate from apply; migrate manually via `dtctl apply extension-config` (see ef2-entity-extraction.md step 6), or re-run with "migrateConfigsConsent":true once the customer agrees',
    });
  }

  return { extensionName, apply, previousVersion, phases };
}

async function getActiveVersion(extensionName: string): Promise<string | null> {
  try {
    const active = await extensionsClient.getActiveExtensionEnvironmentConfiguration({ extensionName });
    return active.version;
  } catch (e) {
    // 404 is the documented "no active environment configuration yet" case --
    // e.g. the extension isn't installed at all, or was installed but never
    // activated. Verified live against oml1007d: both a genuinely nonexistent
    // extension name and one that is installed-but-never-activated surface
    // this way (ErrorEnvelopeError, response.status 404); a malformed request
    // (e.g. an empty extensionName) instead surfaces as a 400 ApiGatewayError.
    // Anything other than 404 -- auth failures, malformed input, transient
    // platform errors -- is a real problem the caller needs to see, not a
    // silent "nothing to migrate away from" that steers phase 2 toward
    // `activateExtensionEnvironmentConfiguration` instead of `update...`.
    if (isNotFoundError(e)) {
      return null;
    }
    throw e;
  }
}

function isNotFoundError(e: unknown): boolean {
  const status = (e as { response?: { status?: unknown } })?.response?.status;
  return status === 404;
}

interface InstallResult {
  outcome: 'done' | 'skipped' | 'failed';
  /** The version to carry into activation and config migration -- the
   * caller's explicit `version`, or (once apply:true has actually run
   * install) the version resolved from installExtension's response. Only
   * undefined for a dry run with no explicit version: nothing has been
   * installed yet to resolve one from. In apply mode this is always set when
   * outcome is 'done' -- an unresolvable version fails the phase instead. */
  resolvedVersion?: string;
}

async function runInstall(
  extensionName: string,
  version: string | undefined,
  apply: boolean,
  phases: PhaseResult[],
): Promise<InstallResult> {
  const detail = version
    ? `install ${extensionName}@${version} from Hub`
    : `install ${extensionName} at the Hub-recommended version`;

  if (!apply) {
    phases.push({
      phase: 'install',
      status: 'planned',
      detail: version ? detail : `${detail} -- the resolved version will be used for activation and config migration once apply:true runs`,
    });
    return { outcome: 'skipped', resolvedVersion: version };
  }

  try {
    const result = await extensionsClient.installExtension({ extensionName, version });
    const installedVersion = version ?? result.extensionVersion;
    if (!installedVersion) {
      // Nothing to activate against -- stop here rather than let phase 2
      // silently skip and report the run as otherwise-successful.
      phases.push({
        phase: 'install',
        status: 'failed',
        detail: `${detail} -- install accepted but the installed version could not be resolved from the response; re-run with an explicit "version" so activation and config migration can target it`,
      });
      return { outcome: 'failed' };
    }
    const visible = await pollForVersion(extensionName, installedVersion);
    if (!visible) {
      phases.push({
        phase: 'install',
        status: 'failed',
        detail: `install accepted but ${installedVersion} not visible via listExtensionVersions after ${INSTALL_POLL_ATTEMPTS} attempts -- installation may still be in progress; re-run later rather than proceeding to activation`,
      });
      return { outcome: 'failed' };
    }
    phases.push({ phase: 'install', status: 'done', detail: `${detail} -- accepted, version ${installedVersion} now visible` });
    return { outcome: 'done', resolvedVersion: installedVersion };
  } catch (e) {
    phases.push({ phase: 'install', status: 'failed', detail: `${detail} -- ${errorMessage(e)}` });
    return { outcome: 'failed' };
  }
}

/** Polls listExtensionVersions for the target version to appear, since
 * installExtension's 202 Accepted means the install is still in progress. */
async function pollForVersion(extensionName: string, version: string): Promise<boolean> {
  for (let attempt = 0; attempt < INSTALL_POLL_ATTEMPTS; attempt++) {
    const versions = await extensionsClient.listExtensionVersions({ extensionName, pageSize: 100 });
    if (versions.items.some((v) => v.version === version)) return true;
    await sleep(INSTALL_POLL_INTERVAL_MS);
  }
  return false;
}

async function runActivate(
  extensionName: string,
  version: string | undefined,
  previousVersion: string | null,
  apply: boolean,
  phases: PhaseResult[],
): Promise<'done' | 'skipped' | 'failed'> {
  if (!version) {
    // Only reachable in dry-run with no explicit version -- apply mode always
    // resolves a version in runInstall or fails the run before this point.
    phases.push({
      phase: 'activate',
      status: 'skipped',
      detail: 'no target version was given -- the Hub-recommended version will be resolved during install once apply:true runs, and used to activate automatically; nothing to plan here yet',
    });
    return 'skipped';
  }

  const detail = previousVersion
    ? `activate ${version}, replacing active version ${previousVersion}`
    : `activate ${version} -- no version is currently active for this extension`;

  if (!apply) {
    phases.push({ phase: 'activate', status: 'planned', detail });
    return 'skipped';
  }

  try {
    // updateExtensionEnvironmentConfiguration switches an already-active
    // extension to a new version; activateExtensionEnvironmentConfiguration
    // is for a version that has never had an environment configuration
    // before (typically right after a first-time Hub install). previousVersion
    // -- captured before phase 1 ran -- is what tells these two cases apart.
    if (previousVersion) {
      await extensionsClient.updateExtensionEnvironmentConfiguration({ extensionName, body: { version } });
    } else {
      await extensionsClient.activateExtensionEnvironmentConfiguration({ extensionName, body: { version } });
    }
    phases.push({ phase: 'activate', status: 'done', detail });
    return 'done';
  } catch (e) {
    phases.push({ phase: 'activate', status: 'failed', detail: `${detail} -- ${errorMessage(e)}` });
    return 'failed';
  }
}

async function runMigrateConfigs(
  extensionName: string,
  targetVersion: string | undefined,
  apply: boolean,
  phases: PhaseResult[],
): Promise<void> {
  if (!targetVersion) {
    // Only reachable in dry-run with no explicit version -- apply mode always
    // resolves a version in runInstall or fails the run before this point.
    phases.push({
      phase: 'migrate-configs',
      status: 'skipped',
      detail: 'no target version was given -- cannot determine the required minimum version floor until install resolves one (apply:true always resolves a version before this phase runs)',
    });
    return;
  }

  const stale = await listConfigsBelowVersion(extensionName, targetVersion);
  if (stale.length === 0) {
    phases.push({
      phase: 'migrate-configs',
      status: 'skipped',
      detail: `no monitoring configurations have version below ${targetVersion}`,
    });
    return;
  }

  const detail = `migrate ${stale.length} monitoring configuration(s) with version below ${targetVersion} to ${targetVersion}: ${stale.map((c) => c.objectId).join(', ')}`;

  if (!apply) {
    phases.push({ phase: 'migrate-configs', status: 'planned', detail });
    return;
  }

  const failures: string[] = [];
  for (const config of stale) {
    try {
      const updatedValue = { ...config.value, version: targetVersion };
      await extensionsClient.updateExtensionMonitoringConfiguration({
        extensionName,
        configurationId: config.objectId,
        body: { value: updatedValue },
      });
    } catch (e) {
      failures.push(`${config.objectId}: ${errorMessage(e)}`);
    }
  }

  // A failed update here is often a schema mismatch, not a version-field
  // problem -- the target version may accept a different config payload
  // shape than the one being copied forward. Point at the diagnostic path
  // (documented in ef2-entity-extraction.md step 6) directly in the failure
  // detail, so an agent hitting this doesn't need to have read the doc
  // first to know what to try next.
  const schemaHint = `compare \`dtctl describe extension ${extensionName} --version <old-version> --monitoring-configuration-schema\` against the same command for --version ${targetVersion} to see what changed, adjust the payload, and retry`;

  phases.push({
    phase: 'migrate-configs',
    status: failures.length === 0 ? 'done' : 'failed',
    detail:
      failures.length === 0
        ? detail
        : `${detail} -- ${failures.length} failed: ${failures.join('; ')}. If this looks like a validation error rather than a version typo, ${schemaHint}.`,
  });
}

interface StaleConfig {
  objectId: string;
  value: Record<string, unknown>;
}

/** Monitoring-config values carry their extension version at `value.version`
 * (verified live). Collects all configs whose version is strictly below
 * `floor` (the required minimum version from the min-version table), not just
 * configs on the previous active version -- a version bump from 4.0.0 to 4.1.3
 * should also migrate configs still on 3.0.1. The list endpoint's documented
 * `filter` parameter was not verified against a live tenant, so this filters
 * client-side instead. */
async function listConfigsBelowVersion(extensionName: string, floor: string): Promise<StaleConfig[]> {
  const stale: StaleConfig[] = [];
  let pageKey: string | undefined;

  do {
    const page = pageKey
      ? await extensionsClient.listExtensionMonitoringConfigurations({ extensionName, pageKey })
      : await extensionsClient.listExtensionMonitoringConfigurations({ extensionName, pageSize: 500 });

    for (const item of page.items) {
      const cfgVersion = String((item.value as Record<string, unknown>)?.version ?? '');
      if (cfgVersion && compareVersions(cfgVersion, floor) < 0) {
        stale.push({ objectId: item.objectId, value: item.value as Record<string, unknown> });
      }
    }

    pageKey = page.nextPageKey ?? undefined;
  } while (pageKey);

  return stale;
}

function compareVersions(a: string, b: string): number {
  const pa = a.split('.').map(Number);
  const pb = b.split('.').map(Number);
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const diff = (pa[i] ?? 0) - (pb[i] ?? 0);
    if (diff !== 0) return diff;
  }
  return 0;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}
