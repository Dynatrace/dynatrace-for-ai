/**
 * Tracking query for request attributes broken by Phase 3.
 *
 * Runs inside the Dynatrace JS runtime via `dtctl exec function -f`, or as a
 * dashboard code tile. A relative fetch is authenticated by the runtime -- no
 * token handling here.
 *
 * Read-only: GETs classic Config v1 only. It reports which request attributes
 * are affected, never whether they can be migrated -- that is the migrator's
 * job.
 */

const BASE_URL = '/platform-reserved/classic-config/v1/service/requestAttributes';
const PRIMARY_TAGS_PREFIX = 'primary_tags.';
const FETCH_CONCURRENCY = 4;
const MAX_RETRIES = 5;
const RETRY_BASE_MS = 250;

/**
 * Capture location that targets client-side external/opaque web request calls
 * only (`CaptureAndStore.OUTGOING_OUTGOING`). External services are obsolete in
 * Phase 3, so a request attribute capturing only there is obsolete too.
 */
const CLIENT_ONLY_LOCATION = 'CAPTURE_AND_STORE_ON_CLIENT';

/**
 * Context prefixes and enum names accepted by `UniversalTagContext.parse()`. A
 * `[...]` prefix outside this set is not a context: `UniversalTag.parse` keeps
 * it as part of the tag key, so such a key is never primary.
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

const REASON_SERVICE_TECHNOLOGY = 'service technology';
const REASON_PG_TAG = 'non-primary process group tag';

interface Scope {
  serviceTechnology?: string | null;
  processGroup?: string | null;
  hostGroup?: string | null;
  tagOfProcessGroup?: string | null;
}

interface DataSource {
  enabled?: boolean;
  capturingAndStorageLocation?: string | null;
  scope?: Scope | null;
}

interface RequestAttribute {
  id: string;
  name?: string;
  enabled?: boolean;
  dataSources?: DataSource[];
}

interface Finding {
  id: string;
  name: string;
  reasons: string[];
}

interface Obsolete {
  id: string;
  name: string;
}

export default async function () {
  const items = await fetchRequestAttributes();
  // A disabled request attribute is never evaluated, so it cannot be affected.
  const enabled = items.filter((item) => item.enabled !== false);

  const obsolete: Obsolete[] = [];
  const findings: Finding[] = [];
  for (const item of enabled) {
    // Obsolescence is decided first: an obsolete request attribute is reported
    // for deletion, never for migration, so the two buckets stay disjoint.
    if (isObsolete(item)) {
      obsolete.push({ id: item.id, name: name(item) });
      continue;
    }
    const finding = toFinding(item);
    if (finding !== null) {
      findings.push(finding);
    }
  }

  return {
    scanned: items.length,
    enabled: enabled.length,
    affected: findings.length,
    affectedByReason: {
      serviceTechnology: countByReason(findings, REASON_SERVICE_TECHNOLOGY),
      nonPrimaryProcessGroupTag: countByReason(findings, REASON_PG_TAG),
    },
    rules: findings,
    obsolete,
  };
}

/**
 * No enabled data source still captures anything that survives Phase 3: either
 * every one of them captures on client-side external calls only, or there is no
 * enabled data source at all. Both cases are to be deleted, not migrated.
 */
function isObsolete(item: RequestAttribute): boolean {
  return enabledDataSources(item).every(
    (source) => source.capturingAndStorageLocation === CLIENT_ONLY_LOCATION,
  );
}

function toFinding(item: RequestAttribute): Finding | null {
  const scopes = enabledDataSources(item)
    .map((source) => source.scope)
    .filter((scope): scope is Scope => scope != null);

  const technologies = dedupe(
    scopes
      .map((scope) => scope.serviceTechnology)
      .filter((technology): technology is string => technology != null),
  );
  const nonPrimaryTags = dedupe(
    scopes
      .map((scope) => scope.tagOfProcessGroup)
      .filter((tag): tag is string => tag != null)
      .map(tagKeyOf)
      .filter((key) => !isPrimaryTagKey(key)),
  );

  const reasons: string[] = [];
  if (technologies.length > 0) {
    reasons.push(`${REASON_SERVICE_TECHNOLOGY}: ${technologies.join(', ')}`);
  }
  if (nonPrimaryTags.length > 0) {
    reasons.push(`${REASON_PG_TAG}: ${nonPrimaryTags.join(', ')}`);
  }
  if (reasons.length === 0) {
    return null;
  }

  return { id: item.id, name: name(item), reasons };
}

/**
 * `ServiceCallTaggerCache` skips a disabled data source before it tests for a
 * forbidden condition, so only an enabled data source can make a request
 * attribute affected.
 */
function enabledDataSources(item: RequestAttribute): DataSource[] {
  return (item.dataSources ?? []).filter((source) => source != null && source.enabled !== false);
}

function countByReason(findings: Finding[], reason: string): number {
  return findings.filter((finding) =>
    finding.reasons.some((entry) => entry.startsWith(`${reason}: `)),
  ).length;
}

function name(item: RequestAttribute): string {
  return item.name ?? '<no name>';
}

/**
 * Mirrors `UniversalTag.parse(...).getKey()`: strip a leading `[Context]`
 * prefix when the context is a known one, then take the key up to the first
 * colon not escaped with a backslash, unescaping `\:` on the way. An unknown
 * `[...]` prefix stays part of the key, exactly as the parser leaves it.
 */
function tagKeyOf(tag: string): string {
  let rest = String(tag);
  let unknownPrefix = '';
  const close = rest.indexOf(']');
  if (rest.startsWith('[') && close !== -1) {
    const prefix = rest.slice(1, close).split('\\:').join(':');
    rest = rest.slice(close + 1);
    if (!TAG_CONTEXTS.has(prefix)) {
      unknownPrefix = `[${prefix}]`;
    }
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
  return unknownPrefix + key;
}

/**
 * Mirrors `RequestAttributePgTagPhase3Validator.isPrimaryTagKey`, including the
 * rule that `primary_tags.` on its own is not a primary tag key. It does not
 * trim: neither the validator nor `UniversalTag.parse` does.
 */
function isPrimaryTagKey(key: string): boolean {
  return key.startsWith(PRIMARY_TAGS_PREFIX) && key.length > PRIMARY_TAGS_PREFIX.length;
}

function dedupe(values: string[]): string[] {
  return [...new Set(values)];
}

async function fetchRequestAttributes(): Promise<RequestAttribute[]> {
  const listResponse = await fetch(BASE_URL, { headers: { Accept: 'application/json' } });
  if (!listResponse.ok) {
    throw new Error(
      `listing request attributes failed: ${listResponse.status} ${await listResponse.text()}`,
    );
  }
  const list = (await listResponse.json()) as { values?: { id: string }[] };
  const stubs = list.values ?? [];

  // Config v1 rate-limits per-id GETs; fetching all stubs at once returns 429,
  // and a 429 body parses into an object with no data sources -- which would
  // under-report silently.
  const items: RequestAttribute[] = [];
  for (let i = 0; i < stubs.length; i += FETCH_CONCURRENCY) {
    const batch = stubs.slice(i, i + FETCH_CONCURRENCY);
    items.push(...(await Promise.all(batch.map((stub) => fetchRequestAttribute(stub.id)))));
  }
  return items;
}

async function fetchRequestAttribute(id: string): Promise<RequestAttribute> {
  for (let attempt = 0; ; attempt++) {
    const res = await fetch(`${BASE_URL}/${id}`, { headers: { Accept: 'application/json' } });
    if (res.ok) {
      return (await res.json()) as RequestAttribute;
    }
    if (res.status !== 429 || attempt >= MAX_RETRIES) {
      throw new Error(`fetching request attribute ${id} failed: ${res.status}`);
    }
    await sleep(RETRY_BASE_MS * 2 ** attempt);
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
