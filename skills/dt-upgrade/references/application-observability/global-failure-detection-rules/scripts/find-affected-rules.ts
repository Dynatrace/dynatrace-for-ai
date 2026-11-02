/**
 * Tracking query for global failure detection rules broken by Phase 3.
 *
 * Runs inside the Dynatrace JS runtime via `dtctl exec function -f`, or as a
 * dashboard code tile. The SDK client authenticates itself -- no token handling
 * here.
 *
 * Read-only: GETs Settings 2.0 only. It reports which rules are affected, never
 * whether they can be migrated -- that is the migrator's job.
 */

import { settingsObjectsClient } from '@dynatrace-sdk/client-classic-environment-v2';

// Only the rules schema carries conditions; a failure detection parameter set has
// none, so it can never be affected and fetching it is pure cost.
const SCHEMA_ID = 'builtin:failure-detection.environment.rules';

const FIELDS = ['objectId', 'value'].join(',');

const PRIMARY_TAG_PREFIX = 'primary_tags.';

/**
 * Context prefixes and enum names accepted by `UniversalTagContext.parse()`. A
 * `[...]` prefix outside this set is not a context: the parser keeps it as part
 * of the tag key, so such a key is never primary.
 */
const TAG_CONTEXTS = new Set([
  'CONTEXTLESS',
  'AWS',
  'Environment',
  'CloudFoundry',
  'Kubernetes',
  'GoogleCloud',
  'Azure',
  'AWSGeneric',
  'ENVIRONMENT',
  'CLOUD_FOUNDRY',
  'KUBERNETES',
  'GOOGLE_COMPUTE_ENGINE',
  'AZURE',
  'AWS_GENERIC',
]);

const REASON_MANAGEMENT_ZONE = 'management zone';
const REASON_PG_TAG = 'non-primary process group tag';
const REASON_SERVICE_TAG = 'service tag';

interface Predicate {
  predicateType?: string;
  managementZones?: string[];
  tags?: string[];
  tagKeys?: string[];
}

interface Condition {
  attribute?: string;
  predicate?: Predicate;
}

interface RuleValue {
  name?: string;
  enabled?: boolean;
  conditions?: Condition[];
}

interface SettingsItem {
  objectId?: string;
  value: RuleValue;
}

interface Finding {
  id: string;
  name: string;
  enabled: boolean;
  reasons: string[];
  managementZones: string[];
  nonPrimaryProcessGroupTags: string[];
  serviceTags: string[];
}

export default async function () {
  const items = await fetchRules();
  // A disabled rule is never evaluated, so it cannot be affected.
  const enabled = items.filter((item) => item.value.enabled !== false);
  const findings = enabled
    .map(toFinding)
    .filter((finding): finding is Finding => finding !== null);

  return {
    scanned: items.length,
    enabled: enabled.length,
    affected: findings.length,
    affectedByReason: {
      managementZone: countByReason(findings, REASON_MANAGEMENT_ZONE),
      nonPrimaryProcessGroupTag: countByReason(findings, REASON_PG_TAG),
      serviceTag: countByReason(findings, REASON_SERVICE_TAG),
    },
    rules: findings,
  };
}

function toFinding(item: SettingsItem): Finding | null {
  const conditions = item.value.conditions ?? [];
  const managementZones = managementZoneRefs(conditions);
  const nonPrimaryProcessGroupTags = nonPrimaryPgTagKeys(conditions);
  const serviceTags = serviceTagKeys(conditions);

  const reasons: string[] = [];
  if (managementZones.length > 0) reasons.push(REASON_MANAGEMENT_ZONE);
  if (nonPrimaryProcessGroupTags.length > 0) reasons.push(REASON_PG_TAG);
  if (serviceTags.length > 0) reasons.push(REASON_SERVICE_TAG);
  if (reasons.length === 0) return null;

  return {
    id: item.objectId ?? '<no id>',
    name: item.value.name ?? '<no name>',
    enabled: item.value.enabled !== false,
    reasons,
    managementZones,
    nonPrimaryProcessGroupTags,
    serviceTags,
  };
}

function countByReason(findings: Finding[], reason: string): number {
  return findings.filter((finding) => finding.reasons.includes(reason)).length;
}

function managementZoneRefs(conditions: Condition[]): string[] {
  return conditions
    .filter((condition) => condition.attribute === 'SERVICE_MANAGEMENT_ZONE')
    .flatMap((condition) => condition.predicate?.managementZones ?? []);
}

function nonPrimaryPgTagKeys(conditions: Condition[]): string[] {
  return conditions
    .filter((condition) => condition.attribute === 'PG_TAG')
    .flatMap((condition) => tagKeys(condition.predicate ?? {}))
    .filter((key) => !isPrimaryTagKey(key));
}

function serviceTagKeys(conditions: Condition[]): string[] {
  return conditions
    .filter((condition) => condition.attribute === 'SERVICE_TAG')
    .flatMap((condition) => tagKeys(condition.predicate ?? {}));
}

/**
 * Tag keys carried by a tag predicate. `tags` holds serialised universal tags
 * (`[Context]key:value`) and needs parsing; `tagKeys` holds bare keys and does
 * not. This mirrors `PGTagConditionValidator`, which parses `tags` before the
 * prefix test but passes `tagKeys` through raw.
 */
function tagKeys(predicate: Predicate): string[] {
  return [
    ...(predicate.tags ?? []).map(tagKeyOf),
    ...(predicate.tagKeys ?? []).map((key) => String(key)),
  ];
}

/**
 * Mirrors `UniversalTag.parse(...).getKey()`: strip an optional `[Context]`
 * prefix, then take the key up to the first colon not escaped with a backslash.
 */
function tagKeyOf(tag: string): string {
  let rest = String(tag).trim();
  const close = rest.indexOf(']');
  if (rest.startsWith('[') && close !== -1 && TAG_CONTEXTS.has(rest.slice(1, close))) {
    rest = rest.slice(close + 1);
  }
  let key = '';
  for (let i = 0; i < rest.length; i++) {
    if (rest[i] === '\\' && rest[i + 1] === ':') {
      key += ':';
      i++;
      continue;
    }
    if (rest[i] === ':') break;
    key += rest[i];
  }
  return key;
}

/**
 * Mirrors `PGTagConditionValidator.isPrimaryTagKey`, including the trim and the
 * rule that `primary_tags.` on its own is not a primary tag key.
 */
function isPrimaryTagKey(key: string): boolean {
  const trimmed = String(key ?? '').trim();
  return trimmed.startsWith(PRIMARY_TAG_PREFIX) && trimmed.length > PRIMARY_TAG_PREFIX.length;
}

// Collects all pages of settings objects.
async function fetchRules(): Promise<SettingsItem[]> {
  let page = await settingsObjectsClient.getSettingsObjects({
    schemaIds: SCHEMA_ID,
    fields: FIELDS,
  });
  let items = page.items as SettingsItem[];
  while (page.nextPageKey != undefined) {
    page = await settingsObjectsClient.getSettingsObjects({ nextPageKey: page.nextPageKey });
    items = items.concat(page.items as SettingsItem[]);
  }
  return items;
}
