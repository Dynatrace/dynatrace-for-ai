// extract-mz-permission-scopes.ts — management-zone permission scopes for the
// dt-upgrade skill.
//
// Yields, for one Dynatrace account, every management zone that is actually
// referenced by a permission grant — and which groups and 2nd-gen roles
// reference it. This is not the same as listing the management zones that exist
// on a tenant: most of those may be unreferenced, and an RBAC migration is
// driven by the grants, not by the zone inventory.
//
// The Account Management API exposes this only indirectly:
//   GET /iam/v1/accounts/{account-uuid}/groups                        — all groups
//   GET /iam/v1/accounts/{account-uuid}/groups/{group-uuid}/permissions — per group
// The tenant is encoded inside the permission's `scope` string rather than being
// its own field: for scopeType "management-zone", scope is
// "{environment-id}:{management-zone-id}".
//
// Run with Node 22+ (native TypeScript type-stripping, no build step):
//
//   # capture — EXPENSIVE. One call per group. Run once per account.
//   node --experimental-strip-types extract-mz-permission-scopes.ts capture \
//     --account-id <uuid> --output run
//
//   # show — offline, free, repeatable. The ONLY read path into a capture.
//   node --experimental-strip-types extract-mz-permission-scopes.ts show \
//     --input run --tenant <tenantId> --zone <mzId>
//
// Credentials come from a .dtmigration file (dotenv-style). This script parses
// that file itself, so the calling agent never has to open it — the secret stays
// out of the transcript. The OAuth access token is held in memory only: never
// written to disk, never logged, never included in an error message.
//
// ---------------------------------------------------------------------------
// IMPORTANT — never read <prefix>.grants.jsonl directly.
//
// Use `show`. Do not open the capture with Read, cat, head, sed or tail. Every
// line of a JSONL file is an independent valid record, so a truncated view is
// indistinguishable from a smaller complete dataset: you get plausible,
// silently wrong answers. A capture is complete if and only if its last line is
// a `_meta` footer, and `show` enforces that check for you.
// ---------------------------------------------------------------------------

import { appendFileSync, existsSync, readFileSync, writeFileSync } from 'node:fs';
import { parseArgs } from 'node:util';

// ---------------------------------------------------------------------------
// Type schema — mirrors the Account Management API 1.0 DTOs
// (https://api.dynatrace.com/spec-json).
// ---------------------------------------------------------------------------

/** Group origin. `ALL_USERS` is a special LOCAL group holding every account user. */
type GroupOwner = 'LOCAL' | 'SCIM' | 'SAML' | 'DCS' | 'ALL_USERS';

/** Scope type of a permission grant. */
type ScopeType = 'account' | 'tenant' | 'management-zone';

/**
 * One entry of GET /groups. Note that `uuid` is OPTIONAL in the spec — only
 * name, owner, createdAt and updatedAt are required — so it must be guarded.
 */
interface GetGroupDto {
  uuid?: string;
  name: string;
  description?: string;
  owner: GroupOwner;
  createdAt: string;
  updatedAt: string;
}

/** Response of GET /groups. There is no pagination on this operation. */
interface GroupListDto {
  count: number;
  items: GetGroupDto[];
}

/** One permission grant on a group. */
interface PermissionsDto {
  permissionName: string;
  /**
   * Meaning depends on scopeType:
   *   account         — the account UUID
   *   tenant          — the environment ID
   *   management-zone — "{environment-id}:{management-zone-id}"
   */
  scope: string;
  scopeType: ScopeType;
  createdAt?: string;
  updatedAt?: string;
}

/** Response of GET /groups/{uuid}/permissions. */
interface PermissionsGroupDto {
  uuid?: string;
  name: string;
  owner: GroupOwner;
  permissions: PermissionsDto[];
}

// ---------------------------------------------------------------------------
// Capture record schema — <prefix>.grants.jsonl
//
// Four record kinds, distinguished by a leading key:
//   {"_meta":  {...}}  header (line 1) and footer (last line)
//   {"_group": {...}}  one per processed group, written after its grants
//   {"_error": {...}}  one per anomaly
//   everything else    a grant record
// ---------------------------------------------------------------------------

const SCHEMA_VERSION = 1;

interface MetaHeader {
  kind: 'header';
  accountUuid: string;
  groupsTotal: number;
  capturedAt: string;
  schemaVersion: number;
}

interface MetaFooter {
  kind: 'footer';
  status: 'complete' | 'complete-with-errors';
  groupsCaptured: number;
  grantsTotal: number;
  accountScopedGrantsSkipped: number;
}

interface GroupMarker {
  groupUuid: string;
  grantsEmitted: number;
  status: 'ok' | 'gone';
}

type ErrorReason = 'http-error' | 'malformed-scope' | 'missing-group-uuid' | 'count-mismatch';

interface CaptureError {
  groupUuid: string | null;
  groupName: string | null;
  stage: string;
  reason: ErrorReason;
  message: string;
}

/** A single management-zone- or tenant-scoped grant. */
interface GrantRecord {
  groupUuid: string;
  groupName: string;
  groupOwner: GroupOwner;
  permissionName: string;
  scopeType: 'management-zone' | 'tenant';
  tenantId: string;
  /** null for scopeType "tenant". */
  managementZoneId: string | null;
  createdAt?: string;
  updatedAt?: string;
}

/** A capture file parsed into its four record kinds. */
interface ParsedCapture {
  header: MetaHeader | null;
  footer: MetaFooter | null;
  groups: GroupMarker[];
  errors: CaptureError[];
  grants: GrantRecord[];
}

// ---------------------------------------------------------------------------
// Credentials
// ---------------------------------------------------------------------------

interface Credentials {
  accountUuid: string;
  clientId: string;
  clientSecret: string;
  tokenUrl: string;
  apiUrl: string;
  scopes: string;
  /** OAuth `resource` parameter; empty string omits it. */
  resource: string;
}

const DEFAULT_TOKEN_URL = 'https://sso.dynatrace.com/sso/oauth2/token';
const DEFAULT_API_URL = 'https://api.dynatrace.com';
const DEFAULT_SCOPES = 'account-idm-read';

/**
 * Read a .dtmigration file (dotenv-style; `export KEY=VALUE` or `KEY=VALUE`,
 * `#` comments, optional surrounding quotes) into a key/value map.
 *
 * The .dtmigration file is a HARD REQUIREMENT — it is the only place this
 * script looks for credentials. It never falls back to dtctl, the OS keychain,
 * or environment variables.
 */
export function parseDotenv(configPath: string): Record<string, string> {
  let raw: string;
  try {
    raw = readFileSync(configPath, 'utf8');
  } catch {
    throw new Error(
      `Credential file "${configPath}" not found. This file is required.\n` +
        `Stop and ask the user to create it (copy .dtmigration.example to ` +
        `.dtmigration and fill in DT_IAM_CLIENT_ID and DT_IAM_CLIENT_SECRET).\n` +
        `Do NOT source credentials from dtctl, the OS keychain, or environment ` +
        `variables — they must come from .dtmigration.`,
    );
  }

  const env: Record<string, string> = {};
  for (const line of raw.split('\n')) {
    const trimmed = line.trim();
    if (trimmed === '' || trimmed.startsWith('#')) continue;
    const assignment = trimmed.replace(/^export\s+/, '');
    const eq = assignment.indexOf('=');
    if (eq === -1) continue;
    const key = assignment.slice(0, eq).trim();
    let value = assignment.slice(eq + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    env[key] = value;
  }
  return env;
}

function loadCredentials(configPath: string, accountIdFlag?: string): Credentials {
  const env = parseDotenv(configPath);

  const clientId = env['DT_IAM_CLIENT_ID'] ?? '';
  const clientSecret = env['DT_IAM_CLIENT_SECRET'] ?? '';
  if (clientId === '' || clientSecret === '') {
    throw new Error(
      `DT_IAM_CLIENT_ID and DT_IAM_CLIENT_SECRET must both be set in "${configPath}". ` +
        `Create an account-level OAuth client (dt0s02.*) with the ` +
        `"account-idm-read" scope under Account Management > Identity & access ` +
        `management > OAuth clients.`,
    );
  }

  const accountUuid = accountIdFlag ?? env['DT_IAM_ACCOUNT_UUID'] ?? '';
  if (accountUuid === '') {
    throw new Error(
      'No account UUID given. Pass --account-id <uuid> or set ' +
        `DT_IAM_ACCOUNT_UUID in "${configPath}".`,
    );
  }

  // The OAuth `resource` parameter identifies the target account. Set
  // DT_IAM_OAUTH_RESOURCE to an empty value to omit it entirely, for
  // deployments whose SSO does not expect it.
  const resource =
    'DT_IAM_OAUTH_RESOURCE' in env ? env['DT_IAM_OAUTH_RESOURCE'] : `urn:dtaccount:${accountUuid}`;

  return {
    accountUuid,
    clientId,
    clientSecret,
    tokenUrl: env['DT_IAM_TOKEN_URL'] || DEFAULT_TOKEN_URL,
    apiUrl: (env['DT_IAM_API_URL'] || DEFAULT_API_URL).replace(/\/+$/, ''),
    scopes: env['DT_IAM_SCOPES'] || DEFAULT_SCOPES,
    resource,
  };
}

/**
 * Exchange the OAuth client credentials for a bearer JWT. The returned token is
 * kept in memory by the caller and must never be logged or persisted.
 */
async function getAccessToken(creds: Credentials): Promise<string> {
  const body = new URLSearchParams({
    grant_type: 'client_credentials',
    client_id: creds.clientId,
    client_secret: creds.clientSecret,
    scope: creds.scopes,
  });
  if (creds.resource !== '') body.set('resource', creds.resource);

  const res = await fetch(creds.tokenUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  });

  if (!res.ok) {
    // Deliberately does not echo the request body — it holds the client secret.
    throw new Error(
      `OAuth token request to ${creds.tokenUrl} failed: HTTP ${res.status}. ` +
        `Check DT_IAM_CLIENT_ID / DT_IAM_CLIENT_SECRET and that the client has ` +
        `the "${creds.scopes}" scope.`,
    );
  }

  const parsed = (await res.json()) as { access_token?: string };
  if (!parsed.access_token) {
    throw new Error(`OAuth token response from ${creds.tokenUrl} contained no access_token.`);
  }
  return parsed.access_token;
}

// ---------------------------------------------------------------------------
// HTTP with retry
// ---------------------------------------------------------------------------

const MAX_ATTEMPTS = 5;

/** Raised for a non-retryable or retry-exhausted HTTP failure. */
class HttpError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function backoffMs(attempt: number): number {
  // 500ms, 1s, 2s, 4s … plus jitter, so a fan-out does not retry in lockstep.
  return 2 ** (attempt - 1) * 500 + Math.floor(Math.random() * 250);
}

/**
 * GET a JSON resource, retrying 429 and 5xx up to MAX_ATTEMPTS while honoring
 * Retry-After. 4xx other than 429 fail immediately — retrying them is pointless.
 */
async function apiGetJson<T>(url: string, token: string): Promise<T> {
  let lastMessage = '';
  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    let res: Response;
    try {
      res = await fetch(url, {
        headers: { Authorization: `Bearer ${token}`, Accept: 'application/json' },
      });
    } catch (e) {
      // Network-level failure; treat as retryable.
      lastMessage = `network error: ${e instanceof Error ? e.message : String(e)}`;
      if (attempt === MAX_ATTEMPTS) break;
      await sleep(backoffMs(attempt));
      continue;
    }

    if (res.ok) return (await res.json()) as T;

    const retryable = res.status === 429 || res.status >= 500;
    lastMessage = `HTTP ${res.status}`;
    if (!retryable || attempt === MAX_ATTEMPTS) {
      throw new HttpError(res.status, `GET ${url} failed: ${lastMessage}`);
    }

    const retryAfter = Number(res.headers.get('retry-after') ?? '');
    await sleep(Number.isFinite(retryAfter) && retryAfter > 0 ? retryAfter * 1000 : backoffMs(attempt));
  }
  throw new HttpError(0, `GET ${url} failed after ${MAX_ATTEMPTS} attempts: ${lastMessage}`);
}

// ---------------------------------------------------------------------------
// Pure logic — unit-tested, no network, no filesystem
// ---------------------------------------------------------------------------

export interface ScopeParseOk {
  ok: true;
  tenantId: string;
  managementZoneId: string;
}
export interface ScopeParseErr {
  ok: false;
  message: string;
}

/**
 * Split a management-zone scope into its tenant and zone halves.
 *
 * The documented format is "{environment-id}:{management-zone-id}". Neither an
 * environment ID nor a numeric zone ID contains a colon, so splitting on the
 * FIRST colon is unambiguous. Both halves must be non-empty: emitting a junk
 * tenant is worse than recording the anomaly.
 */
export function parseManagementZoneScope(scope: string): ScopeParseOk | ScopeParseErr {
  const trimmed = scope.trim();
  const colon = trimmed.indexOf(':');
  if (colon === -1) {
    return { ok: false, message: `scope "${scope}" has no ":" separator` };
  }
  const tenantId = trimmed.slice(0, colon).trim();
  const managementZoneId = trimmed.slice(colon + 1).trim();
  if (tenantId === '') {
    return { ok: false, message: `scope "${scope}" has an empty environment ID` };
  }
  if (managementZoneId === '') {
    return { ok: false, message: `scope "${scope}" has an empty management zone ID` };
  }
  return { ok: true, tenantId, managementZoneId };
}

export type Classification =
  | { kind: 'grant'; grant: GrantRecord }
  | { kind: 'skipped-account' }
  | { kind: 'error'; message: string };

/**
 * Turn one permission into a grant record, a skip, or an anomaly.
 *
 * `account`-scoped grants are deliberately skipped — this tool is about
 * tenant-level RBAC — but they are counted so their omission is visible.
 */
export function classifyGrant(
  group: { uuid: string; name: string; owner: GroupOwner },
  permission: PermissionsDto,
): Classification {
  if (permission.scopeType === 'account') return { kind: 'skipped-account' };

  let tenantId: string;
  let managementZoneId: string | null;

  if (permission.scopeType === 'management-zone') {
    const parsed = parseManagementZoneScope(permission.scope);
    if (!parsed.ok) return { kind: 'error', message: parsed.message };
    tenantId = parsed.tenantId;
    managementZoneId = parsed.managementZoneId;
  } else if (permission.scopeType === 'tenant') {
    tenantId = permission.scope.trim();
    if (tenantId === '') {
      return { kind: 'error', message: 'tenant-scoped permission has an empty scope' };
    }
    managementZoneId = null;
  } else {
    return { kind: 'error', message: `unknown scopeType "${String(permission.scopeType)}"` };
  }

  // Keys are written in a fixed order so the JSONL is byte-stable across runs.
  const grant: GrantRecord = {
    groupUuid: group.uuid,
    groupName: group.name,
    groupOwner: group.owner,
    permissionName: permission.permissionName,
    scopeType: permission.scopeType,
    tenantId,
    managementZoneId,
  };
  if (permission.createdAt !== undefined) grant.createdAt = permission.createdAt;
  if (permission.updatedAt !== undefined) grant.updatedAt = permission.updatedAt;

  return { kind: 'grant', grant };
}

/**
 * Compare two management zone IDs numerically.
 *
 * Zone IDs are 64-bit signed integers, which can exceed Number.MAX_SAFE_INTEGER,
 * so Number() would lose precision and make the ordering unstable. BigInt is
 * exact; non-numeric IDs fall back to a string compare so the sort is still
 * total and deterministic.
 */
export function compareZoneIds(a: string, b: string): number {
  try {
    const bigA = BigInt(a);
    const bigB = BigInt(b);
    return bigA < bigB ? -1 : bigA > bigB ? 1 : 0;
  } catch {
    return a < b ? -1 : a > b ? 1 : 0;
  }
}

export interface ZoneSummary {
  managementZoneId: string;
  grantCount: number;
}
export interface TenantSummary {
  tenantId: string;
  tenantWideGrants: number;
  managementZones: ZoneSummary[];
}

/**
 * Roll grants up per tenant.
 *
 * Arrays, not objects keyed by ID: JavaScript reorders integer-like object keys
 * numerically ahead of insertion order, so a mix of positive and negative zone
 * IDs would serialize inconsistently and the summary would stop being diffable.
 * Ordering here is explicit and total, so a shuffled input yields byte-identical
 * output.
 */
export function groupByTenant(grants: GrantRecord[]): TenantSummary[] {
  const tenants = new Map<string, { tenantWide: number; zones: Map<string, number> }>();

  for (const grant of grants) {
    let entry = tenants.get(grant.tenantId);
    if (entry === undefined) {
      entry = { tenantWide: 0, zones: new Map() };
      tenants.set(grant.tenantId, entry);
    }
    if (grant.scopeType === 'tenant') {
      entry.tenantWide += 1;
    } else if (grant.managementZoneId !== null) {
      entry.zones.set(grant.managementZoneId, (entry.zones.get(grant.managementZoneId) ?? 0) + 1);
    }
  }

  return [...tenants.entries()]
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
    .map(([tenantId, entry]) => ({
      tenantId,
      tenantWideGrants: entry.tenantWide,
      managementZones: [...entry.zones.entries()]
        .sort(([a], [b]) => compareZoneIds(a, b))
        .map(([managementZoneId, grantCount]) => ({ managementZoneId, grantCount })),
    }));
}

/** Sort grants into a stable, human-sensible order. */
export function sortGrants(grants: GrantRecord[]): GrantRecord[] {
  return [...grants].sort(
    (a, b) =>
      (a.groupName < b.groupName ? -1 : a.groupName > b.groupName ? 1 : 0) ||
      (a.permissionName < b.permissionName
        ? -1
        : a.permissionName > b.permissionName
          ? 1
          : 0) ||
      compareZoneIds(a.managementZoneId ?? '', b.managementZoneId ?? ''),
  );
}

export interface Summary {
  accountUuid: string;
  capturedAt: string;
  complete: boolean;
  summary: {
    groupsTotal: number;
    groupsCaptured: number;
    groupsFailed: number;
    groupsGone: number;
    grantsTotal: number;
    accountScopedGrantsSkipped: number;
    tenantsTotal: number;
    managementZonesTotal: number;
    groupsWithManagementZoneGrants: number;
    groupsByOwner: Record<GroupOwner, number>;
  };
  tenants: TenantSummary[];
  errors: CaptureError[];
}

/** Build the small, agent-readable summary from a fully parsed capture. */
export function buildSummary(capture: ParsedCapture, accountScopedSkipped: number): Summary {
  const tenants = groupByTenant(capture.grants);

  const groupsWithMz = new Set<string>();
  const ownerCounts: Record<GroupOwner, number> = {
    LOCAL: 0,
    SCIM: 0,
    SAML: 0,
    DCS: 0,
    ALL_USERS: 0,
  };
  const seenGroups = new Set<string>();
  for (const grant of capture.grants) {
    if (grant.scopeType === 'management-zone') groupsWithMz.add(grant.groupUuid);
    if (!seenGroups.has(grant.groupUuid)) {
      seenGroups.add(grant.groupUuid);
      if (grant.groupOwner in ownerCounts) ownerCounts[grant.groupOwner] += 1;
    }
  }

  // Only group-specific reasons count as a failed group; count-mismatch is an
  // account-level anomaly and has no group to attribute.
  const failedGroups = new Set(
    capture.errors
      .filter((e) => e.reason === 'http-error' || e.reason === 'missing-group-uuid')
      .map((e) => e.groupUuid ?? e.groupName)
      .filter((key): key is string => key !== null),
  );

  return {
    accountUuid: capture.header?.accountUuid ?? '',
    capturedAt: capture.header?.capturedAt ?? '',
    complete: capture.footer !== null,
    summary: {
      groupsTotal: capture.header?.groupsTotal ?? 0,
      groupsCaptured: capture.groups.length,
      groupsFailed: failedGroups.size,
      groupsGone: capture.groups.filter((g) => g.status === 'gone').length,
      grantsTotal: capture.grants.length,
      accountScopedGrantsSkipped: accountScopedSkipped,
      tenantsTotal: tenants.length,
      managementZonesTotal: tenants.reduce((n, t) => n + t.managementZones.length, 0),
      groupsWithManagementZoneGrants: groupsWithMz.size,
      groupsByOwner: ownerCounts,
    },
    tenants,
    errors: capture.errors,
  };
}

/** Parse a capture file's raw text into its record kinds. */
export function parseCapture(text: string): ParsedCapture {
  const result: ParsedCapture = {
    header: null,
    footer: null,
    groups: [],
    errors: [],
    grants: [],
  };

  for (const line of text.split('\n')) {
    const trimmed = line.trim();
    if (trimmed === '') continue;
    let record: Record<string, unknown>;
    try {
      record = JSON.parse(trimmed) as Record<string, unknown>;
    } catch {
      continue; // A partially written final line; ignore it.
    }

    if (record['_meta'] !== undefined) {
      const meta = record['_meta'] as MetaHeader | MetaFooter;
      if (meta.kind === 'header') result.header = meta as MetaHeader;
      else if (meta.kind === 'footer') result.footer = meta as MetaFooter;
    } else if (record['_group'] !== undefined) {
      result.groups.push(record['_group'] as GroupMarker);
    } else if (record['_error'] !== undefined) {
      result.errors.push(record['_error'] as CaptureError);
    } else {
      result.grants.push(record as unknown as GrantRecord);
    }
  }
  return result;
}

/**
 * A capture is complete if and only if its last non-empty line is a `_meta`
 * footer. This one rule covers both a crashed run and a truncated read, which
 * warrant the same distrust.
 */
export function isComplete(text: string): boolean {
  const lines = text.split('\n').filter((l) => l.trim() !== '');
  const last = lines[lines.length - 1];
  if (last === undefined) return false;
  try {
    const record = JSON.parse(last) as Record<string, unknown>;
    const meta = record['_meta'] as { kind?: string } | undefined;
    return meta?.kind === 'footer';
  } catch {
    return false;
  }
}

/**
 * Which group UUIDs are already captured and may be skipped on resume.
 *
 * A group whose permissions were all account-scoped emits zero grant lines, so
 * the `_group` marker — not the presence of grants — is what makes resume
 * correct. Failed groups have no marker, so they are naturally retried.
 */
export function resumeSetFrom(capture: ParsedCapture): Set<string> {
  return new Set(capture.groups.map((g) => g.groupUuid));
}

// ---------------------------------------------------------------------------
// Concurrency
// ---------------------------------------------------------------------------

/** Run `worker` over `items` with at most `limit` in flight, preserving input order. */
async function mapWithConcurrency<T, R>(
  items: T[],
  limit: number,
  worker: (item: T, index: number) => Promise<R>,
): Promise<R[]> {
  const results = new Array<R>(items.length);
  let next = 0;

  async function run(): Promise<void> {
    while (true) {
      const index = next++;
      if (index >= items.length) return;
      results[index] = await worker(items[index] as T, index);
    }
  }

  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, run));
  return results;
}

// ---------------------------------------------------------------------------
// File naming
// ---------------------------------------------------------------------------

const DEFAULT_PREFIX = 'mz-permission-scopes';

function grantsPath(prefix: string): string {
  return `${prefix}.grants.jsonl`;
}
function summaryPath(prefix: string): string {
  return `${prefix}.summary.json`;
}

// ---------------------------------------------------------------------------
// capture
// ---------------------------------------------------------------------------

interface GroupOutcome {
  lines: string[];
  grantsEmitted: number;
  status: 'ok' | 'gone' | 'failed';
  accountSkipped: number;
}

async function processGroup(
  creds: Credentials,
  token: string,
  group: GetGroupDto,
): Promise<GroupOutcome> {
  const lines: string[] = [];
  let accountSkipped = 0;

  if (group.uuid === undefined || group.uuid === '') {
    // Schema-legal but unusable: permissions can only be fetched by UUID.
    lines.push(
      JSON.stringify({
        _error: {
          groupUuid: null,
          groupName: group.name,
          stage: 'groups',
          reason: 'missing-group-uuid',
          message: `group "${group.name}" has no uuid and cannot be queried`,
        } satisfies CaptureError,
      }),
    );
    return { lines, grantsEmitted: 0, status: 'failed', accountSkipped };
  }

  const url =
    `${creds.apiUrl}/iam/v1/accounts/${encodeURIComponent(creds.accountUuid)}` +
    `/groups/${encodeURIComponent(group.uuid)}/permissions`;

  let dto: PermissionsGroupDto;
  try {
    dto = await apiGetJson<PermissionsGroupDto>(url, token);
  } catch (e) {
    // 410 Gone is the only documented non-200: the group was deleted between
    // the listing and this call. Not an error — mark it so resume stops asking.
    if (e instanceof HttpError && e.status === 410) {
      lines.push(
        JSON.stringify({
          _group: { groupUuid: group.uuid, grantsEmitted: 0, status: 'gone' } satisfies GroupMarker,
        }),
      );
      return { lines, grantsEmitted: 0, status: 'gone', accountSkipped };
    }
    lines.push(
      JSON.stringify({
        _error: {
          groupUuid: group.uuid,
          groupName: group.name,
          stage: 'permissions',
          reason: 'http-error',
          message: e instanceof Error ? e.message : String(e),
        } satisfies CaptureError,
      }),
    );
    return { lines, grantsEmitted: 0, status: 'failed', accountSkipped };
  }

  const identity = { uuid: group.uuid, name: group.name, owner: group.owner };
  let grantsEmitted = 0;

  for (const permission of dto.permissions ?? []) {
    const classified = classifyGrant(identity, permission);
    if (classified.kind === 'grant') {
      lines.push(JSON.stringify(classified.grant));
      grantsEmitted += 1;
    } else if (classified.kind === 'skipped-account') {
      accountSkipped += 1;
    } else {
      lines.push(
        JSON.stringify({
          _error: {
            groupUuid: group.uuid,
            groupName: group.name,
            stage: 'permissions',
            reason: 'malformed-scope',
            message: classified.message,
          } satisfies CaptureError,
        }),
      );
    }
  }

  lines.push(
    JSON.stringify({
      _group: { groupUuid: group.uuid, grantsEmitted, status: 'ok' } satisfies GroupMarker,
    }),
  );
  return { lines, grantsEmitted, status: 'ok', accountSkipped };
}

async function runCapture(opts: {
  configPath: string;
  accountId?: string;
  prefix: string;
  resume: boolean;
  concurrency: number;
}): Promise<number> {
  const creds = loadCredentials(opts.configPath, opts.accountId);
  const outPath = grantsPath(opts.prefix);

  let alreadyDone = new Set<string>();
  let carriedLines: string[] = [];
  let accountSkippedCarried = 0;
  let carriedCapturedAt: string | null = null;

  if (existsSync(outPath)) {
    if (!opts.resume) {
      throw new Error(
        `"${outPath}" already exists. A capture is expensive, so it is never ` +
          `overwritten: pass --resume to continue it, or choose another --output prefix.`,
      );
    }
    const existingText = readFileSync(outPath, 'utf8');
    const existing = parseCapture(existingText);

    // Resuming into another account's capture would silently merge two accounts.
    if (
      existing.header !== null &&
      existing.header.accountUuid !== '' &&
      existing.header.accountUuid !== creds.accountUuid
    ) {
      throw new Error(
        `"${outPath}" is a capture of account ${existing.header.accountUuid}, but ` +
          `this run targets ${creds.accountUuid}. Use a different --output prefix.`,
      );
    }

    alreadyDone = resumeSetFrom(existing);
    accountSkippedCarried = existing.footer?.accountScopedGrantsSkipped ?? 0;
    carriedCapturedAt = existing.header?.capturedAt ?? null;

    // Carry over grants and completed groups. Drop both _meta records (a fresh
    // header and footer are written below) and drop errors belonging to groups
    // that are about to be retried, so they are not double-counted.
    carriedLines = existingText
      .split('\n')
      .filter((line) => line.trim() !== '')
      .filter((line) => {
        try {
          const record = JSON.parse(line) as Record<string, unknown>;
          if (record['_meta'] !== undefined) return false;
          const err = record['_error'] as CaptureError | undefined;
          if (err !== undefined) {
            const key = err.groupUuid;
            return key !== null && alreadyDone.has(key);
          }
          return true;
        } catch {
          return false;
        }
      });
    console.error(`Resuming: ${alreadyDone.size} group(s) already captured.`);
  } else if (opts.resume) {
    console.error(`No existing capture at "${outPath}" — starting a fresh one.`);
  }

  const token = await getAccessToken(creds);

  const listUrl = `${creds.apiUrl}/iam/v1/accounts/${encodeURIComponent(creds.accountUuid)}/groups`;
  const groupList = await apiGetJson<GroupListDto>(listUrl, token);
  const groups = groupList.items ?? [];
  console.error(`Account ${creds.accountUuid}: ${groups.length} group(s).`);

  const preambleErrors: string[] = [];
  if (typeof groupList.count === 'number' && groupList.count !== groups.length) {
    preambleErrors.push(
      JSON.stringify({
        _error: {
          groupUuid: null,
          groupName: null,
          stage: 'groups',
          reason: 'count-mismatch',
          message: `GroupListDto.count is ${groupList.count} but items has ${groups.length} entries; trusting items`,
        } satisfies CaptureError,
      }),
    );
  }

  // Header first: groupsTotal is knowable here, before the fan-out. A resumed
  // run keeps the original capturedAt so the artifact still dates the data.
  const header: MetaHeader = {
    kind: 'header',
    accountUuid: creds.accountUuid,
    groupsTotal: groups.length,
    capturedAt: carriedCapturedAt ?? new Date().toISOString(),
    schemaVersion: SCHEMA_VERSION,
  };

  // Rewrite from scratch: carriedLines already excludes both _meta records.
  const initial = [JSON.stringify({ _meta: header }), ...carriedLines, ...preambleErrors];
  writeFileSync(outPath, `${initial.join('\n')}\n`);

  const pending = groups.filter((g) => g.uuid === undefined || !alreadyDone.has(g.uuid));
  if (pending.length === 0) {
    console.error('Nothing to do: every group is already captured.');
  }

  let processed = 0;
  let accountSkipped = accountSkippedCarried;
  let failures = 0;

  await mapWithConcurrency(pending, opts.concurrency, async (group) => {
    const outcome = await processGroup(creds, token, group);
    // Append as each group finishes so an interrupted run keeps its work.
    appendFileSync(outPath, `${outcome.lines.join('\n')}\n`);
    processed += 1;
    accountSkipped += outcome.accountSkipped;
    if (outcome.status === 'failed') failures += 1;
    if (processed % 25 === 0 || processed === pending.length) {
      console.error(`  ${processed}/${pending.length} group(s) processed`);
    }
    return outcome;
  });

  const finalText = readFileSync(outPath, 'utf8');
  const parsed = parseCapture(finalText);

  const footer: MetaFooter = {
    kind: 'footer',
    status: failures > 0 || parsed.errors.length > 0 ? 'complete-with-errors' : 'complete',
    groupsCaptured: parsed.groups.length,
    grantsTotal: parsed.grants.length,
    accountScopedGrantsSkipped: accountSkipped,
  };
  appendFileSync(outPath, `${JSON.stringify({ _meta: footer })}\n`);

  const summary = buildSummary({ ...parsed, footer }, accountSkipped);
  writeFileSync(summaryPath(opts.prefix), `${JSON.stringify(summary, null, 2)}\n`);

  console.error('');
  console.error(`Capture:  ${outPath}   (${footer.grantsTotal} grant(s)) — do not read directly, use "show"`);
  console.error(`Summary:  ${summaryPath(opts.prefix)}`);
  console.error(
    `Tenants:  ${summary.summary.tenantsTotal}, management zones: ${summary.summary.managementZonesTotal}`,
  );
  if (parsed.errors.length > 0) {
    console.error(`Errors:   ${parsed.errors.length} — see "errors" in the summary`);
  }
  return failures > 0 || parsed.errors.length > 0 ? 1 : 0;
}

// ---------------------------------------------------------------------------
// show
// ---------------------------------------------------------------------------

interface ShowFilters {
  tenant?: string;
  zone?: string;
  scopeType?: string;
  groupName?: string;
  owner?: string;
}

export function applyFilters(grants: GrantRecord[], f: ShowFilters): GrantRecord[] {
  return grants.filter((g) => {
    if (f.tenant !== undefined && g.tenantId !== f.tenant) return false;
    if (f.zone !== undefined && g.managementZoneId !== f.zone) return false;
    if (f.scopeType !== undefined && g.scopeType !== f.scopeType) return false;
    if (f.groupName !== undefined && g.groupName !== f.groupName) return false;
    if (f.owner !== undefined && g.groupOwner !== f.owner) return false;
    return true;
  });
}

function runShow(opts: {
  prefix: string;
  filters: ShowFilters;
  allowIncomplete: boolean;
}): number {
  const inPath = grantsPath(opts.prefix);
  if (!existsSync(inPath)) {
    throw new Error(`Capture "${inPath}" not found. Run the "capture" subcommand first.`);
  }
  const text = readFileSync(inPath, 'utf8');

  if (!isComplete(text) && !opts.allowIncomplete) {
    throw new Error(
      `Capture "${inPath}" is incomplete: its last line is not a _meta footer, so ` +
        `the run was interrupted or the file is truncated. Any answer from it may ` +
        `silently omit grants. Re-run "capture --resume", or pass ` +
        `--allow-incomplete to query it anyway.`,
    );
  }

  const capture = parseCapture(text);
  const matched = sortGrants(applyFilters(capture.grants, opts.filters));

  const output = {
    complete: capture.footer !== null,
    filters: opts.filters,
    grantCount: matched.length,
    grants: matched,
  };
  process.stdout.write(`${JSON.stringify(output, null, 2)}\n`);
  return 0;
}

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

const USAGE = `Usage:
  node --experimental-strip-types extract-mz-permission-scopes.ts capture [options]
  node --experimental-strip-types extract-mz-permission-scopes.ts show    [options]

Subcommands:
  capture  Walk every group in the account and record its management-zone- and
           tenant-scoped permission grants. EXPENSIVE: one API call per group.
           Run once per account, then query the result with "show".
  show     Query a capture offline. This is the ONLY supported read path —
           never open <prefix>.grants.jsonl with Read, cat, head or sed, because
           a truncated view of a JSONL file looks like valid complete data.

capture options:
  --account-id <uuid>   Account UUID (falls back to DT_IAM_ACCOUNT_UUID).
  --config <path>       Credential file (default: .dtmigration).
  --output <prefix>     Output prefix (default: ${DEFAULT_PREFIX}). Writes
                        <prefix>.grants.jsonl and <prefix>.summary.json.
  --resume              Continue an existing capture, skipping captured groups.
                        Without it, an existing capture is never overwritten.
  --concurrency <n>     Parallel permission requests (default: 8).

show options:
  --input <prefix>      Capture prefix to read (default: ${DEFAULT_PREFIX}).
  --tenant <id>         Filter by environment ID.
  --zone <id>           Filter by management zone ID.
  --scope-type <t>      management-zone | tenant.
  --group-name <name>   Filter by group name.
  --owner <o>           LOCAL | SCIM | SAML | DCS | ALL_USERS.
  --allow-incomplete    Query a capture with no footer (results may be partial).
  At least one filter is required.

Read <prefix>.summary.json first: it is small, safe to read whole, and lists
every tenant and management zone with grant counts. Then use "show" per zone.`;

/** Options that take a value and may legitimately receive a dash-leading one. */
const VALUE_OPTIONS = new Set([
  '--account-id',
  '--config',
  '--output',
  '--input',
  '--concurrency',
  '--tenant',
  '--zone',
  '--scope-type',
  '--group-name',
  '--owner',
]);

/**
 * Rewrite `--opt value` into `--opt=value` for value-taking options.
 *
 * Management zone IDs are usually negative, and parseArgs rejects
 * `--zone -1234567890` as ambiguous because the value looks like a flag.
 * Requiring `--zone=-1234567890` would be a trap in the most common case, so
 * both forms are accepted. A following `--flag` is left alone, so a genuinely
 * missing value is still reported by parseArgs rather than silently swallowed.
 */
export function normalizeArgv(args: string[]): string[] {
  const out: string[] = [];
  for (let i = 0; i < args.length; i++) {
    const arg = args[i] as string;
    const next = args[i + 1];
    if (
      VALUE_OPTIONS.has(arg) &&
      next !== undefined &&
      !next.startsWith('--')
    ) {
      out.push(`${arg}=${next}`);
      i++;
    } else {
      out.push(arg);
    }
  }
  return out;
}

async function main(): Promise<number> {
  const subcommand = process.argv[2];
  const args = normalizeArgv(process.argv.slice(3));

  if (args.includes('--help') || args.includes('-h')) {
    console.log(USAGE);
    return 0;
  }
  if (subcommand === undefined || subcommand === '--help' || subcommand === '-h') {
    console.log(USAGE);
    return subcommand === undefined ? 1 : 0;
  }
  if (subcommand !== 'capture' && subcommand !== 'show') {
    throw new Error(`Unknown subcommand "${subcommand}".\n\n${USAGE}`);
  }

  const { values } = parseArgs({
    args,
    options: {
      'account-id': { type: 'string' },
      config: { type: 'string', default: '.dtmigration' },
      output: { type: 'string' },
      input: { type: 'string' },
      resume: { type: 'boolean', default: false },
      concurrency: { type: 'string' },
      tenant: { type: 'string' },
      zone: { type: 'string' },
      'scope-type': { type: 'string' },
      'group-name': { type: 'string' },
      owner: { type: 'string' },
      'allow-incomplete': { type: 'boolean', default: false },
    },
    allowPositionals: false,
  });

  if (subcommand === 'capture') {
    for (const rejected of ['input', 'tenant', 'zone', 'scope-type', 'group-name', 'owner'] as const) {
      if (values[rejected] !== undefined) {
        throw new Error(`capture does not accept --${rejected}.\n\n${USAGE}`);
      }
    }
    const concurrency = values.concurrency === undefined ? 8 : Number(values.concurrency);
    if (!Number.isInteger(concurrency) || concurrency < 1) {
      throw new Error(`--concurrency must be a positive integer; got "${values.concurrency}".`);
    }
    return runCapture({
      configPath: values.config as string,
      accountId: values['account-id'],
      prefix: (values.output as string | undefined) ?? DEFAULT_PREFIX,
      resume: values.resume as boolean,
      concurrency,
    });
  }

  if (values.output !== undefined) {
    throw new Error(`show does not accept --output (did you mean --input?).\n\n${USAGE}`);
  }
  const scopeType = values['scope-type'];
  if (scopeType !== undefined && scopeType !== 'management-zone' && scopeType !== 'tenant') {
    throw new Error(`--scope-type must be "management-zone" or "tenant"; got "${scopeType}".`);
  }
  const owner = values.owner;
  const OWNERS = ['LOCAL', 'SCIM', 'SAML', 'DCS', 'ALL_USERS'];
  if (owner !== undefined && !OWNERS.includes(owner)) {
    throw new Error(`--owner must be one of ${OWNERS.join(', ')}; got "${owner}".`);
  }

  const filters: ShowFilters = {};
  if (values.tenant !== undefined) filters.tenant = values.tenant;
  if (values.zone !== undefined) filters.zone = values.zone;
  if (scopeType !== undefined) filters.scopeType = scopeType;
  if (values['group-name'] !== undefined) filters.groupName = values['group-name'];
  if (owner !== undefined) filters.owner = owner;

  if (Object.keys(filters).length === 0) {
    throw new Error(
      `show requires at least one filter (--tenant, --zone, --scope-type, ` +
        `--group-name or --owner). An unfiltered show would dump the whole ` +
        `capture, which is what this subcommand exists to avoid — read ` +
        `<prefix>.summary.json instead for the overview.\n\n${USAGE}`,
    );
  }

  return runShow({
    prefix: (values.input as string | undefined) ?? DEFAULT_PREFIX,
    filters,
    allowIncomplete: values['allow-incomplete'] as boolean,
  });
}

// Only run the CLI when executed directly, so the pure functions above can be
// imported by the test file.
if (process.argv[1] !== undefined && import.meta.filename === process.argv[1]) {
  main()
    .then((code) => process.exit(code))
    .catch((err: unknown) => {
      console.error(err instanceof Error ? err.message : String(err));
      process.exit(1);
    });
}
