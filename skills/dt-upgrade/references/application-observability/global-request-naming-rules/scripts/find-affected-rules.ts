/**
 * Tracking query for global request naming rules broken by Phase 3.
 *
 * Runs inside the Dynatrace JS runtime via `dtctl exec function -f`, where a
 * relative fetch is authenticated by the runtime -- no token handling here.
 *
 * Read-only: GETs classic Config v1 only. It reports which rules are affected,
 * never whether they can be migrated -- that is the migrator's job.
 */

const BASE_URL = '/platform-reserved/classic-config/v1/service/requestNaming';
const PRIMARY_TAGS_PREFIX = 'primary_tags.';
const FETCH_CONCURRENCY = 4;
const MAX_RETRIES = 5;
const RETRY_BASE_MS = 250;

type TagEntry = { context?: string; key?: string; value?: string } | string;

interface ComparisonInfo {
  type?: string;
  value?: TagEntry | null;
  values?: TagEntry[] | null;
}

interface Condition {
  attribute?: string;
  comparisonInfo?: ComparisonInfo;
}

interface Rule {
  id: string;
  namingPattern?: string;
  enabled?: boolean;
  conditions?: Condition[];
  managementZones?: string[];
}

interface Finding {
  id: string;
  namingPattern: string;
  reasons: string[];
}

export default async function () {
  const rules = await fetchRequestNamingRules();
  const enabled = rules.filter((rule) => rule.enabled !== false);
  const findings = enabled
    .map(toFinding)
    .filter((finding): finding is Finding => finding !== null);

  return {
    scanned: rules.length,
    enabled: enabled.length,
    affected: findings.length,
    rules: findings,
  };
}

function toFinding(rule: Rule): Finding | null {
  const reasons: string[] = [];

  if ((rule.managementZones ?? []).length > 0) {
    reasons.push('management zone scope');
  }

  for (const cond of rule.conditions ?? []) {
    if (cond.attribute === 'SERVICE_TAG') {
      reasons.push('SERVICE_TAG condition');
      continue;
    }
    if (cond.attribute === 'PROCESS_GROUP_TAG' && cond.comparisonInfo?.type === 'TAG') {
      const nonPrimary = tagKeys(cond.comparisonInfo).filter((key) => !isPrimaryTagKey(key));
      if (nonPrimary.length > 0) {
        reasons.push(`non-primary PROCESS_GROUP_TAG: ${nonPrimary.join(', ')}`);
      }
    }
  }

  return reasons.length > 0
    ? { id: rule.id, namingPattern: rule.namingPattern ?? '<no name>', reasons: dedupe(reasons) }
    : null;
}

/**
 * Tag keys carried by a TAG comparison, normalised across both serialisations:
 * a TagDto object (`{context, key, value}`) and the bare `key:value` string.
 * Either may arrive under `value` or `values`; reading only one shape from only
 * one field silently misclassifies conditions.
 */
function tagKeys(ci: ComparisonInfo): string[] {
  const entries: TagEntry[] = [...(ci.values ?? []), ...(ci.value != null ? [ci.value] : [])];
  return entries
    .map((entry) => (typeof entry === 'string' ? entry.split(':')[0] : entry.key))
    .filter((key): key is string => typeof key === 'string' && key.length > 0);
}

function isPrimaryTagKey(key: string): boolean {
  return key.startsWith(PRIMARY_TAGS_PREFIX);
}

function dedupe(values: string[]): string[] {
  return [...new Set(values)];
}

async function fetchRequestNamingRules(): Promise<Rule[]> {
  const listResponse = await fetch(BASE_URL, { headers: { Accept: 'application/json' } });
  if (!listResponse.ok) {
    throw new Error(`listing rules failed: ${listResponse.status} ${await listResponse.text()}`);
  }
  const list = (await listResponse.json()) as { values?: { id: string }[] };
  const stubs = list.values ?? [];

  // Config v1 rate-limits per-rule GETs; fetching all stubs at once returns 429.
  const rules: Rule[] = [];
  for (let i = 0; i < stubs.length; i += FETCH_CONCURRENCY) {
    const batch = stubs.slice(i, i + FETCH_CONCURRENCY);
    rules.push(...(await Promise.all(batch.map((stub) => fetchRule(stub.id)))));
  }
  return rules;
}

async function fetchRule(id: string): Promise<Rule> {
  for (let attempt = 0; ; attempt++) {
    const res = await fetch(`${BASE_URL}/${id}`, { headers: { Accept: 'application/json' } });
    if (res.ok) {
      return (await res.json()) as Rule;
    }
    if (res.status !== 429 || attempt >= MAX_RETRIES) {
      throw new Error(`fetching rule ${id} failed: ${res.status}`);
    }
    await sleep(RETRY_BASE_MS * 2 ** attempt);
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
