/**
 * Migration-needs prober for a non-hub/custom EF2 extension artifact.
 *
 * Architecture note: unlike find-ef1-plugins.ts and list-ef2-extensions.ts,
 * this is a *local* Node script, not a `dtctl exec function` script. The
 * Dynatrace JS runtime that `dtctl exec function` scripts run in is a
 * sandboxed cloud environment with no child-process or local-filesystem
 * access -- it cannot spawn the `dtctl` CLI or an `unzip` binary. Downloading
 * and inspecting an extension package needs both, so this script runs
 * locally instead, the same way `shared/metric-transpiler/scripts/transpile.ts`
 * does:
 *
 *   node --experimental-strip-types scripts/inspect-ef2-artifact.ts <extensionName> <version>
 *
 * Investigated whether the SDK could avoid the download+unzip step via
 * content negotiation (an `acceptType` on the extension-details call): that
 * capability exists only on an internal client (`application/octet-stream`),
 * not on the public `@dynatrace-sdk/client-extensions-v2`. Same
 * internal-vs-public distribution problem as the EF1 plugins client (see
 * ef2-entity-extraction.md's Constraints note) -- not usable here. `dtctl
 * download extension` remains the correct, publicly-supported path.
 *
 * Requires `dtctl` and `unzip` on PATH. Explicitly gated behind the agent
 * asking the customer before running -- see ef2-entity-extraction.md's
 * Instructions.
 *
 * The artifact is a double-zip: `dtctl download extension` returns an outer
 * zip containing `extension.zip` (the signed payload) and `extension.zip.sig`.
 * This script unwraps the outer zip automatically before inspecting the inner
 * package.
 */

import { execFileSync } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

type FindingStatus = 'ok' | 'needs-migration' | 'not-applicable' | 'manual-check';
type ExtensionFlavour = 'python' | 'declarative' | 'openpipeline' | 'unknown';

interface Finding {
  name: string;
  status: FindingStatus;
  classicPresent?: boolean;
  platformPresent?: boolean;
  migrationTarget?: string;
  detail?: string;
}

const [extensionName, version] = process.argv.slice(2);

if (!extensionName || !version) {
  console.error('Usage: inspect-ef2-artifact.ts <extensionName> <version>');
  process.exit(1);
}

const workDir = mkdtempSync(join(tmpdir(), 'ef2-artifact-'));

try {
  let zipBytes: Buffer;
  try {
    // --no-agent ensures the binary response is not wrapped in a JSON envelope,
    // regardless of whether the caller's dtctl config enables agent mode by default.
    zipBytes = execFileSync('dtctl', ['download', 'extension', extensionName, '--version', version, '--no-agent'], {
      maxBuffer: 1024 * 1024 * 256,
    });
  } catch (e) {
    const stdout = e instanceof Error && 'stdout' in e ? String((e as NodeJS.ErrnoException & { stdout?: unknown }).stdout ?? '') : '';
    let hint = '';
    try { hint = (JSON.parse(stdout) as { error?: { message?: string } })?.error?.message ?? ''; } catch { /* ignore */ }
    console.error(JSON.stringify({ error: 'download failed', extensionName, version, hint: hint || String(e) }));
    process.exit(1);
  }

  const outerZipPath = join(workDir, 'outer.zip');
  writeFileSync(outerZipPath, zipBytes);

  // Unwrap the double-zip: the artifact outer shell contains extension.zip.
  const outerEntries = listZipEntries(outerZipPath);
  const innerZipEntry = outerEntries.find((e) => e === 'extension.zip' || e.endsWith('/extension.zip'));
  let zipPath = outerZipPath;
  if (innerZipEntry) {
    const innerZipPath = join(workDir, 'extension.zip');
    writeFileSync(innerZipPath, readZipEntryBytes(outerZipPath, innerZipEntry));
    zipPath = innerZipPath;
  }

  const result = inspectArtifact(extensionName, version, zipPath);
  console.log(JSON.stringify(result, null, 2));
} finally {
  rmSync(workDir, { recursive: true, force: true });
}

function inspectArtifact(name: string, ver: string, zipPath: string) {
  const entries = listZipEntries(zipPath);
  const yamlEntry = entries.find((e) => e === 'extension.yaml' || e.endsWith('/extension.yaml'));

  if (!yamlEntry) {
    console.error(JSON.stringify({ error: 'extension.yaml not found in archive', extensionName: name, version: ver }));
    process.exit(2);
  }

  const sourceEntries = entries.filter((e) => e.endsWith('.source.json'));
  const pipelineEntries = entries.filter((e) => e.endsWith('.pipeline.json'));
  const yamlContent = readZipEntry(zipPath, yamlEntry);

  const topKeys = topLevelKeys(yamlContent);
  const flavour = detectFlavour(topKeys);
  const findings: Finding[] = [];

  // --- Topology / entity extraction ---
  // Node presence, source files, and pipeline files are independent signals --
  // conflating them into one "platform topology" boolean hid partial
  // conversions (e.g. the node wired in but the source/pipeline files never
  // generated) behind a false "ok". See topologyFinding for the full matrix.
  const hasClassicTopology = topKeys.has('topology');
  const hasOpenPipelineNode = topKeys.has('openpipeline');
  const hasSourceFiles = sourceEntries.length > 0;
  const hasPipelineFiles = pipelineEntries.length > 0;
  findings.push(topologyFinding(hasClassicTopology, hasOpenPipelineNode, hasSourceFiles, hasPipelineFiles));

  // minDynatraceVersion gates are relevant whenever any OpenPipeline signal is
  // present, not just a fully-wired one -- an extension with orphaned source
  // files still needs the version bump before the node can be added.
  if (hasClassicTopology || hasOpenPipelineNode || hasSourceFiles || hasPipelineFiles) {
    findings.push(...minVersionFindings(yamlContent));
  }

  // --- Dashboards ---
  const hasClassicDashboards = topKeys.has('dashboards');
  const hasPlatformDashboards = topKeys.has('documents') && topLevelBlock(yamlContent, 'documents').includes('dashboards:');
  findings.push(migrationFinding(
    'Dashboards',
    hasClassicDashboards,
    hasPlatformDashboards,
    'document dashboards',
    'classic dashboards (top-level `dashboards:` list)',
  ));

  // --- Alerting ---
  const hasClassicAlerts = topKeys.has('alerts');
  const hasPlatformAlerts = topKeys.has('alertTemplates');
  findings.push(migrationFinding(
    'Alerting',
    hasClassicAlerts,
    hasPlatformAlerts,
    'alertTemplates (Davis anomaly detectors)',
    'classic metric-event alerts (top-level `alerts:` list)',
  ));

  // --- UA screens ---
  const hasClassicScreens = topKeys.has('screens');
  const hasPlatformScreens = topKeys.has('documents') && topLevelBlock(yamlContent, 'documents').includes('screens:');
  findings.push(uaScreensFinding(hasClassicScreens, hasPlatformScreens));

  // --- Primary tags and dt.security_context ---
  if (hasSourceFiles) {
    findings.push(...processorFindings(zipPath, sourceEntries, flavour));
  } else if (hasOpenPipelineNode) {
    // openpipeline: node present but no source files -- incomplete conversion.
    // Reachable now that hasOpenPipelineNode no longer requires source and
    // pipeline files to also be present (previously this branch could never
    // fire, since the old hasPlatformTopology check required both).
    findings.push({
      name: 'Primary tags / dt.security_context',
      status: 'needs-migration',
      detail: 'openpipeline: node present but no *.source.json files found -- conversion appears incomplete',
    });
  } else if (hasClassicTopology) {
    findings.push({
      name: 'Primary tags',
      status: 'manual-check',
      detail: 'classic topology present but no *.source.json -- verify topology.types rules extract primary_tags.* in each entity type',
    });
  }

  // --- Source↔pipeline linkage ---
  if (hasSourceFiles && hasPipelineFiles) {
    findings.push(...linkageFindings(zipPath, sourceEntries, pipelineEntries));
  } else if (hasSourceFiles || hasPipelineFiles || hasOpenPipelineNode) {
    // Partial OpenPipeline signal but not enough of it to check the
    // pipelineId <-> customId cross-link -- surface as incomplete rather than
    // skipping silently, which previously let an incomplete conversion look
    // untouched by this check.
    findings.push({
      name: 'Source↔pipeline linkage',
      status: 'needs-migration',
      detail: `cannot verify staticRouting.pipelineId ↔ customId linkage -- missing ${missingFileKinds(hasSourceFiles, hasPipelineFiles)}`,
    });
  }

  const overallStatus: FindingStatus = findings.some((f) => f.status === 'needs-migration') ? 'needs-migration' : 'ok';
  const manualChecks = findings.filter((f) => f.status === 'manual-check').map((f) => f.name);

  return { extensionName: name, version: ver, extensionFlavour: flavour, overallStatus, manualChecks, findings };
}

// ---------------------------------------------------------------------------
// Decision-table helpers
// ---------------------------------------------------------------------------

/**
 * Classic topology, the openpipeline: node, and the *.source.json/*.pipeline.json
 * file pair are independent signals -- a node can exist without its files (an
 * incomplete conversion), and files can exist without a node (generated but
 * never wired in). Folding them into a single "platform topology present"
 * boolean hid the incomplete-conversion case behind a false "ok"; this checks
 * all four combinations of (classic, node) against file completeness.
 */
function topologyFinding(
  classicPresent: boolean,
  nodePresent: boolean,
  hasSourceFiles: boolean,
  hasPipelineFiles: boolean,
): Finding {
  const filesComplete = hasSourceFiles && hasPipelineFiles;
  const filesPresent = hasSourceFiles || hasPipelineFiles;
  const platformPresent = nodePresent && filesComplete;
  const base = { name: 'Topology / entity extraction', classicPresent, platformPresent };
  const migrationTarget = 'OpenPipeline entity extraction (Smartscape 2.0)';

  if (!classicPresent && !nodePresent) {
    if (!filesPresent) {
      return { ...base, status: 'ok', detail: 'no classic topology block and no OpenPipeline extraction -- no migration needed' };
    }
    return {
      ...base,
      status: 'needs-migration',
      migrationTarget,
      detail: 'OpenPipeline source/pipeline file(s) present but no top-level openpipeline: node references them -- wire them into extension.yaml or remove the orphaned files',
    };
  }

  if (!classicPresent && nodePresent) {
    if (filesComplete) {
      return { ...base, status: 'ok', detail: 'OpenPipeline entity extraction (Smartscape 2.0) present, no classic topology block' };
    }
    return {
      ...base,
      status: 'needs-migration',
      migrationTarget,
      detail: `openpipeline: node present but missing ${missingFileKinds(hasSourceFiles, hasPipelineFiles)} -- conversion appears incomplete`,
    };
  }

  if (classicPresent && !nodePresent) {
    const orphanNote = filesPresent ? ' (OpenPipeline file(s) exist but are not wired in via an openpipeline: node)' : '';
    return {
      ...base,
      status: 'needs-migration',
      migrationTarget,
      detail: `classic topology: block present -- use VS Code "Create Smartscape Topology" to generate openpipeline/ files${orphanNote}`,
    };
  }

  // both classicPresent and nodePresent
  if (filesComplete) {
    return {
      ...base,
      status: 'needs-migration',
      migrationTarget,
      detail: 'both classic topology: and openpipeline: node present -- migration in progress; verify extraction works then remove the classic topology: block',
    };
  }
  return {
    ...base,
    status: 'needs-migration',
    migrationTarget,
    detail: `both classic topology: and openpipeline: node present, but missing ${missingFileKinds(hasSourceFiles, hasPipelineFiles)} -- migration in progress and incomplete; generate the missing file(s) before removing the classic topology: block`,
  };
}

/** Names which of the two required OpenPipeline file kinds are absent, for use
 * in "incomplete conversion" finding details. */
function missingFileKinds(hasSourceFiles: boolean, hasPipelineFiles: boolean): string {
  return [!hasSourceFiles && '*.source.json', !hasPipelineFiles && '*.pipeline.json'].filter(Boolean).join(' and ');
}

function migrationFinding(
  name: string,
  classicPresent: boolean,
  platformPresent: boolean,
  migrationTarget: string,
  classicDescription: string,
): Finding {
  const base = { name, classicPresent, platformPresent };
  if (!classicPresent) {
    return { ...base, status: 'ok', detail: `no ${classicDescription} present` };
  }
  if (classicPresent && !platformPresent) {
    return { ...base, status: 'needs-migration', migrationTarget, detail: `${classicDescription} present -- migrate to ${migrationTarget}` };
  }
  // both present
  return { ...base, status: 'needs-migration', migrationTarget, detail: `${classicDescription} present alongside ${migrationTarget} -- complete the migration and remove the classic form` };
}

/** Verified live (v3.0.7 of a real F5 BIG-IP extension): `documents.screens`
 * is a plain `{path: screens/<name>.screen.json}` list, structurally
 * identical to `documents.dashboards` -- so screens fit the same
 * classic-vs-platform presence check as Dashboards/Alerting, not a permanent
 * manual-check. The remaining nuance (breadcrumbs, entity/metric tables, and
 * events/logs/problems cards have no equivalent in the new format; content
 * whose `target:` is CLASSIC-only is skipped by the converter entirely) is
 * about what to verify *while* converting, not about whether conversion is
 * needed at all -- so it's folded into the needs-migration detail text
 * instead of forcing a manual-check verdict. Per UA screen maintainers,
 * `target: CLASSIC` cards are Angular-only; `target: PLATFORM`/`BOTH` cards
 * also render on platform (though a few 2nd-gen card types still don't port)
 * -- that per-card nuance is orthogonal to this file-level presence check and
 * not evaluated here. */
function uaScreensFinding(classicPresent: boolean, platformPresent: boolean): Finding {
  const base = { name: 'UA screens', classicPresent, platformPresent };
  if (!classicPresent) {
    return { ...base, status: 'ok', detail: 'no classic `screens:` block present' };
  }
  const migrationTarget = 'document-based screens (documents.screens)';
  const converterGaps = 'breadcrumbs, entity/metric tables, and events/logs/problems cards have no equivalent in the new format and are skipped by "Convert Screens"; cards whose `target:` is CLASSIC-only are skipped entirely -- verify these were ported manually';
  if (!platformPresent) {
    return {
      ...base,
      status: 'needs-migration',
      migrationTarget,
      detail: `classic \`screens:\` block present, no documents.screens entries -- use VS Code "Convert Screens" to generate them (${converterGaps})`,
    };
  }
  // both present
  return {
    ...base,
    status: 'needs-migration',
    migrationTarget,
    detail: `classic \`screens:\` block present alongside documents.screens -- migration in progress; ${converterGaps}; then remove the classic \`screens:\` block`,
  };
}

// ---------------------------------------------------------------------------
// minDynatraceVersion capability checks
// ---------------------------------------------------------------------------

function minVersionFindings(yamlContent: string): Finding[] {
  const match = yamlContent.match(/minDynatraceVersion:\s*["']?([0-9.]+)/);
  if (!match) {
    return [{ name: 'minDynatraceVersion >= 1.345', status: 'needs-migration', detail: 'minDynatraceVersion not set -- must be at least 1.345 for OpenPipeline entity extraction to function' }];
  }
  const current = match[1];
  if (compareVersions(current, '1.345') >= 0) {
    return [{ name: 'minDynatraceVersion >= 1.345', status: 'ok', detail: current }];
  }
  if (compareVersions(current, '1.330') >= 0) {
    return [{
      name: 'minDynatraceVersion >= 1.345',
      status: 'needs-migration',
      detail: `found ${current} -- 1.330 allows the openpipeline: node but Smartscape 2.0 node/edge extraction requires 1.345; bump minDynatraceVersion to at least 1.345`,
    }];
  }
  return [{
    name: 'minDynatraceVersion >= 1.330',
    status: 'needs-migration',
    detail: `found ${current} -- below 1.330; the openpipeline: node cannot exist at all at this version; bump minDynatraceVersion to at least 1.345`,
  }];
}

// ---------------------------------------------------------------------------
// Processor-level checks (primary tags, dt.security_context, staticEdges)
// ---------------------------------------------------------------------------

function processorFindings(zipPath: string, sourceEntries: string[], flavour: ExtensionFlavour): Finding[] {
  if (flavour === 'python') {
    return [{ name: 'Primary tags / dt.security_context', status: 'not-applicable', detail: 'Python extension -- primary tags are injected globally, not per extractNode:true processor' }];
  }

  const missingPrimaryTags: string[] = [];
  const missingSecurityContext: string[] = [];
  const missingStaticEdges: string[] = [];
  const parseErrors: string[] = [];

  for (const entry of sourceEntries) {
    let source: unknown;
    try {
      source = JSON.parse(readZipEntry(zipPath, entry));
    } catch {
      parseErrors.push(entry);
      continue;
    }
    const processors = findExtractNodeProcessors(source);
    for (const proc of processors) {
      const label = (proc as Record<string, unknown>).name as string | undefined ?? entry;
      const fields: unknown[] = ((proc as Record<string, unknown>).fieldsToExtract as unknown[] | undefined) ?? [];

      const hasPrimaryTags = fields.some(
        (f) => typeof (f as Record<string, unknown>)?.referencedFieldName === 'string' &&
          ((f as Record<string, unknown>).referencedFieldName as string).startsWith('primary_tags.') &&
          (f as Record<string, unknown>).strategy === 'startsWith',
      );
      if (!hasPrimaryTags) missingPrimaryTags.push(label);

      const hasSecCtx = fields.some(
        (f) => (f as Record<string, unknown>)?.referencedFieldName === 'dt.security_context',
      );
      if (!hasSecCtx) missingSecurityContext.push(label);

      if (!('staticEdgesToExtract' in (proc as Record<string, unknown>))) {
        missingStaticEdges.push(label);
      }
    }
  }

  const results: Finding[] = [];
  if (parseErrors.length > 0) {
    results.push({ name: 'Source JSON parse', status: 'manual-check', detail: `could not parse: ${parseErrors.join(', ')}` });
  }
  if (missingPrimaryTags.length === 0 && missingSecurityContext.length === 0 && missingStaticEdges.length === 0) {
    results.push({ name: 'Primary tags / dt.security_context / staticEdges', status: 'ok' });
  } else {
    if (missingPrimaryTags.length > 0) {
      results.push({ name: 'Primary tags', status: 'needs-migration', detail: `processors missing primary_tags.* fieldsToExtract with strategy:startsWith: ${missingPrimaryTags.join(', ')}` });
    }
    if (missingSecurityContext.length > 0) {
      results.push({ name: 'dt.security_context', status: 'needs-migration', detail: `processors missing dt.security_context in fieldsToExtract: ${missingSecurityContext.join(', ')}` });
    }
    if (missingStaticEdges.length > 0) {
      results.push({ name: 'staticEdgesToExtract key', status: 'needs-migration', detail: `processors missing staticEdgesToExtract key (even [] is required): ${missingStaticEdges.join(', ')}` });
    }
  }
  return results;
}

function findExtractNodeProcessors(obj: unknown): unknown[] {
  if (!obj || typeof obj !== 'object') return [];
  if (Array.isArray(obj)) return obj.flatMap(findExtractNodeProcessors);
  const record = obj as Record<string, unknown>;
  const results: unknown[] = record.extractNode === true ? [record] : [];
  return results.concat(Object.values(record).flatMap(findExtractNodeProcessors));
}

// ---------------------------------------------------------------------------
// Source↔pipeline linkage check
// ---------------------------------------------------------------------------

function linkageFindings(zipPath: string, sourceEntries: string[], pipelineEntries: string[]): Finding[] {
  const findings: Finding[] = [];
  for (const srcEntry of sourceEntries) {
    let source: Record<string, unknown>;
    try { source = JSON.parse(readZipEntry(zipPath, srcEntry)) as Record<string, unknown>; } catch { continue; }
    const routing = source.staticRouting as Record<string, unknown> | undefined;
    const pipelineId = routing?.pipelineId;
    if (!pipelineId) continue;

    const matched = pipelineEntries.some((p) => {
      try { return (JSON.parse(readZipEntry(zipPath, p)) as Record<string, unknown>).customId === pipelineId; } catch { return false; }
    });
    if (!matched) {
      const found = pipelineEntries.map((p) => {
        try { return String((JSON.parse(readZipEntry(zipPath, p)) as Record<string, unknown>).customId ?? p); } catch { return p; }
      }).join(', ');
      findings.push({ name: 'Source↔pipeline linkage', status: 'needs-migration', detail: `${srcEntry} staticRouting.pipelineId="${pipelineId}" but no *.pipeline.json has matching customId (found: ${found})` });
    }
  }
  if (findings.length === 0) {
    findings.push({ name: 'Source↔pipeline linkage', status: 'ok' });
  }
  return findings;
}

// ---------------------------------------------------------------------------
// YAML helpers (no library dependency -- pure text operations)
// ---------------------------------------------------------------------------

/** Returns the set of keys that appear at column 0 (true top-level only). */
function topLevelKeys(yaml: string): Set<string> {
  const keys = new Set<string>();
  for (const m of yaml.matchAll(/^([A-Za-z_][\w-]*):/gm)) {
    keys.add(m[1]);
  }
  return keys;
}

/** Returns the raw text block of a top-level key (from "key:" to the next column-0 key). */
function topLevelBlock(yaml: string, key: string): string {
  const lines = yaml.split('\n');
  const start = lines.findIndex((l) => l.startsWith(`${key}:`));
  if (start === -1) return '';
  const relEnd = lines.slice(start + 1).findIndex((l) => /^[A-Za-z_][\w-]*:/.test(l));
  return relEnd === -1 ? lines.slice(start).join('\n') : lines.slice(start, start + 1 + relEnd).join('\n');
}

function detectFlavour(topKeys: Set<string>): ExtensionFlavour {
  if (topKeys.has('python')) return 'python';
  const declarativeDatasources = ['snmp', 'sqlOracle', 'prometheus', 'wmi', 'jmx', 'statsd', 'jdbc', 'script'];
  if (declarativeDatasources.some((k) => topKeys.has(k))) return 'declarative';
  if (topKeys.has('openpipeline') && !topKeys.has('topology')) return 'openpipeline';
  return 'unknown';
}

// ---------------------------------------------------------------------------
// Zip utilities
// ---------------------------------------------------------------------------

function listZipEntries(zipPath: string): string[] {
  const output = execFileSync('unzip', ['-Z1', zipPath], { encoding: 'utf-8' });
  return output.split('\n').filter(Boolean);
}

function readZipEntry(zipPath: string, entry: string): string {
  return execFileSync('unzip', ['-p', zipPath, entry], { encoding: 'utf-8', maxBuffer: 1024 * 1024 * 64 });
}

function readZipEntryBytes(zipPath: string, entry: string): Buffer {
  return execFileSync('unzip', ['-p', zipPath, entry], { maxBuffer: 1024 * 1024 * 256 });
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
