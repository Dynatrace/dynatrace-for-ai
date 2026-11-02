// transpile.ts — Metric Transpiler client for the dt-upgrade skill.
//
// Converts classic 2nd-gen (2G) metric selectors / expressions into Grail DQL
// via the Classic Environment API v2:
//   GET  /api/v2/metrics/transpile        — one selector at a time
//   POST /api/v2/metrics/transpileBulk    — many selectors in one request
//
// Run with Node 22+ (native TypeScript type-stripping, no build step):
//   node --experimental-strip-types scripts/transpile.ts single --selector '<sel>'
//   node --experimental-strip-types scripts/transpile.ts bulk   --input selectors.json
//
// The API token is read from a .dtmigration file (dotenv-style). This script
// parses that file itself, so the calling agent never has to open it — the
// token stays out of the transcript. Never print or log the resolved header.
//
// The environment URL is NOT taken from .dtmigration: it is resolved from the
// active dtctl context (`dtctl config current-context`) and converted from the
// platform URL to the classic Environment API URL the transpiler is served
// from. (Override with DT_TRANSPILE_ENV_URL in .dtmigration only for unusual
// deployments.)
//
// Output: a JSON array of normalized results, one per input selector (see
// TranspileResult), in input order. By default it is written to stdout, which
// also carries no other output from this script — but a subprocess it calls
// (dtctl) may print incidental warnings to stderr, so if you merge streams
// (`> out.json 2>&1`) those can land in the file. To get a guaranteed-clean
// result file, pass --output <path>: the JSON is written straight to that file
// and stdout is left for logs. Prefer --output whenever you machine-read the
// result (e.g. bulk runs piped into a .json).

import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
import { parseArgs } from 'node:util';

// ---------------------------------------------------------------------------
// Type schema — mirrors the service DTOs
// (com.compuware.apm.rest.dto.metrics.api.*). Kept in sync with the Java
// interfaces documented in metric-transpiler.md.
// ---------------------------------------------------------------------------

/** Query parameters accepted by BOTH endpoints. */
interface CommonOptions {
  /**
   * Timestep or data-point count. Accepts a timestep with a positive factor
   * ("1m", "5m", "1h", "1w", "4M", "3y"), a unit-less point count >= 2 ("120",
   * "500"), or "Inf" for a single aggregated point. NOT "auto" — the server
   * rejects it with 400. Omit to use the server default (120 points).
   */
  resolution?: string;
  /** Query timeframe start; ISO-8601 or relative ("now-2h"). Default: now-2h. */
  from?: string;
  /** Query timeframe end; ISO-8601 or relative ("now"). Default: now. */
  to?: string;
  /** Diagnostic strictness. Default: "lenient". */
  mode?: 'lenient' | 'strict';
  /** Target consumer of the DQL. Default: "api". */
  consumer?: 'api' | 'notebook';
}

/** Extra query parameters accepted ONLY by the single-selector GET endpoint. */
interface SingleOptions extends CommonOptions {
  /**
   * Scalar rollup applied to the series, e.g. "auto", "avg", "min", "max",
   * "sum", "count", "last", "median", "value", or "percentile(<n>)".
   */
  scalarFunction?: string;
  /** "pretty" returns pretty-printed DQL; otherwise the DQL is compact. */
  format?: 'pretty';
  /**
   * When true, each diagnostic carries a {start,end} character range and is
   * serialized as an object; when false (default) diagnostics are plain
   * strings. This script normalizes both shapes to {message, range?}.
   */
  errorLocations?: boolean;
}

/** A single diagnostic (warning or error) from the transpiler. */
interface TranspileDiagnostic {
  message: string;
  /** Present only when the request set errorLocations=true. */
  range?: { start: number; end: number };
}

/** Per-column metadata; one entry per output column of the DQL. */
interface FieldMetadata {
  /** Index into the input selector list. */
  index: number;
  /** Output column name (e.g. "expression"). */
  id: string;
  /** True if the column holds a single value rather than a series. */
  scalar: boolean;
  /** The original selector this column derives from. */
  metricId: string;
  /** Unit of the values; omitted by the API when unknown. */
  unit?: string;
  /** True if a timeshift operator was applied. */
  shifted: boolean;
}

/**
 * Raw response DTO for one selector (TsmMetricSelectorTranspilationDTO).
 * Fields are omitted by the API when null/empty, so all but status are
 * optional here.
 */
interface TranspilationDTO {
  /** SUCCESS = clean; PARTIAL_SUCCESS = warnings present; ERROR = failed. */
  status: 'SUCCESS' | 'PARTIAL_SUCCESS' | 'ERROR';
  dql?: string;
  errors?: (string | TranspileDiagnostic)[];
  warnings?: (string | TranspileDiagnostic)[];
  infos?: string[];
  metadata?: FieldMetadata[];
}

/** Raw response DTO for the bulk endpoint (TsmMetricSelectorTranspilationCollectionDTO). */
interface CollectionDTO {
  transpilationResults?: TranspilationDTO[];
}

/** Normalized, uniform result this script emits — one per input selector. */
interface TranspileResult {
  /** The original 2G selector/expression that was transpiled. */
  input: string;
  status: 'SUCCESS' | 'PARTIAL_SUCCESS' | 'ERROR';
  /** The generated DQL, or null when transpilation failed. */
  dql: string | null;
  /** Non-fatal notes, e.g. a metric that was auto-substituted in Grail. */
  infos: string[];
  warnings: TranspileDiagnostic[];
  errors: TranspileDiagnostic[];
  metadata: FieldMetadata[];
}

// ---------------------------------------------------------------------------
// Credentials
// ---------------------------------------------------------------------------

interface Credentials {
  baseUrl: string;
  authHeader: string;
}

/**
 * Read a .dtmigration file (dotenv-style; `export KEY=VALUE` or `KEY=VALUE`,
 * `#` comments, optional surrounding quotes) into a key/value map.
 *
 * The .dtmigration file is a HARD REQUIREMENT — this is the only place the
 * script looks for the token. It never falls back to dtctl, the OS keychain,
 * or environment variables.
 */
function parseDotenv(configPath: string): Record<string, string> {
  let raw: string;
  try {
    raw = readFileSync(configPath, 'utf8');
  } catch {
    throw new Error(
      `Credential file "${configPath}" not found. This file is required.\n` +
        `Stop and ask the user to create it (copy .dtmigration.example to ` +
        `.dtmigration and set DT_TRANSPILE_TOKEN).\n` +
        `Do NOT source a token from dtctl, the OS keychain, or environment ` +
        `variables — the token must come from .dtmigration.`,
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

/**
 * Convert a Dynatrace *platform* URL (what dtctl stores) to the *classic*
 * environment URL that serves the Environment API v2 the transpiler lives on.
 * The two hosts differ, so the platform URL cannot be used directly.
 *
 *   SaaS prod:  <env>.apps.dynatrace.com              -> <env>.live.dynatrace.com
 *   SaaS labs:  <env>.<stage>.apps.dynatracelabs.com  -> <env>.<stage>.dynatracelabs.com
 *   Managed / custom (no "apps" label): used unchanged (path preserved).
 */
function toClassicBaseUrl(platformUrl: string): string {
  const url = new URL(platformUrl);
  const labels = url.hostname.split('.');
  const appsIdx = labels.indexOf('apps');
  if (appsIdx !== -1) {
    if (url.hostname.endsWith('.dynatrace.com')) {
      labels[appsIdx] = 'live'; // production SaaS classic tenant
    } else {
      labels.splice(appsIdx, 1); // lab/dev stages just drop the apps label
    }
    url.hostname = labels.join('.');
  }
  const path = url.pathname.replace(/\/+$/, ''); // keep Managed's /e/<uuid>
  return `${url.origin}${path}`;
}

/**
 * Resolve the classic environment base URL. By default it is derived from the
 * current dtctl context, so the target tenant always matches the user's active
 * context and never has to be repeated in .dtmigration. An explicit
 * DT_TRANSPILE_ENV_URL in .dtmigration overrides this (an escape hatch for
 * unusual deployments) and is used verbatim.
 */
function resolveBaseUrl(override?: string): string {
  if (override && override.length > 0) {
    return override.replace(/\/+$/, '');
  }

  let currentContext: string;
  try {
    currentContext = execFileSync('dtctl', ['config', 'current-context', '--no-agent'], {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'inherit'],
    }).trim();
  } catch (e) {
    throw new Error(
      `Could not run "dtctl config current-context" to determine the environment URL. Ensure ` +
        `dtctl is installed and a context is configured. ` +
        `(${e instanceof Error ? e.message : String(e)})`,
    );
  }

  if (!currentContext) {
    throw new Error(
      'No current dtctl context found. Select one with "dtctl config use-context <name>".',
    );
  }

  let stdout: string;
  try {
    stdout = execFileSync(
      'dtctl',
      ['config', 'view', `--context=${currentContext}`, '-o', 'json', '--no-agent'],
      { encoding: 'utf8', stdio: ['ignore', 'pipe', 'inherit'] },
    );
  } catch (e) {
    throw new Error(
      `Could not run "dtctl config view --context=${currentContext} -o json" to read the environment URL. ` +
        `(${e instanceof Error ? e.message : String(e)})`,
    );
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(stdout) as unknown;
  } catch {
    throw new Error(
      `Could not parse "dtctl config view --context=${currentContext} -o json" output as JSON.`,
    );
  }

  type DtctlViewContext = {
    Name?: string;
    name?: string;
    Context?: { Environment?: string; environment?: string };
    context?: { Environment?: string; environment?: string };
  };
  type DtctlViewResponse = {
    Contexts?: DtctlViewContext[];
    contexts?: DtctlViewContext[];
    result?: { Contexts?: DtctlViewContext[]; contexts?: DtctlViewContext[] };
  };
  const parsedView = (parsed as DtctlViewResponse) ?? {};
  const contexts: DtctlViewContext[] =
    Array.isArray(parsedView.Contexts)
      ? parsedView.Contexts
      : Array.isArray(parsedView.contexts)
        ? parsedView.contexts
      : Array.isArray(parsedView.result?.Contexts)
        ? parsedView.result.Contexts
        : Array.isArray(parsedView.result?.contexts)
          ? parsedView.result.contexts
        : [];

  const current = contexts.find((c) => (c.Name ?? c.name) === currentContext);
  const environment =
    current?.Context?.Environment ??
    current?.Context?.environment ??
    current?.context?.Environment ??
    current?.context?.environment;
  if (!environment) {
    throw new Error(
      `Context "${currentContext}" has no Environment URL in dtctl config. Check with ` +
        `"dtctl config view --context=${currentContext} -o json".`,
    );
  }
  return toClassicBaseUrl(environment);
}

function loadCredentials(configPath: string): Credentials {
  // Parse .dtmigration first: a missing file is the most common, most
  // actionable error, and we should surface it before shelling out to dtctl.
  const env = parseDotenv(configPath);
  const token = env['DT_TRANSPILE_TOKEN'];
  if (!token || token.length === 0) {
    throw new Error(
      `DT_TRANSPILE_TOKEN is not set in "${configPath}". Create an API token ` +
        `under Personal access tokens > Create token with the "metrics:read" ` +
        `scope, then set it in .dtmigration.`,
    );
  }
  const baseUrl = resolveBaseUrl(env['DT_TRANSPILE_ENV_URL']);
  return { baseUrl, authHeader: `Api-Token ${token}` };
}

// ---------------------------------------------------------------------------
// API calls
// ---------------------------------------------------------------------------

function applyCommonParams(url: URL, o: CommonOptions): void {
  if (o.resolution) url.searchParams.set('resolution', o.resolution);
  if (o.from) url.searchParams.set('from', o.from);
  if (o.to) url.searchParams.set('to', o.to);
  if (o.mode) url.searchParams.set('mode', o.mode);
  if (o.consumer) url.searchParams.set('consumer', o.consumer);
}

function normalizeDiagnostic(d: string | TranspileDiagnostic): TranspileDiagnostic {
  return typeof d === 'string' ? { message: d } : d;
}

function normalize(input: string, dto: TranspilationDTO): TranspileResult {
  return {
    input,
    status: dto.status,
    dql: dto.dql ?? null,
    infos: dto.infos ?? [],
    warnings: (dto.warnings ?? []).map(normalizeDiagnostic),
    errors: (dto.errors ?? []).map(normalizeDiagnostic),
    metadata: dto.metadata ?? [],
  };
}

async function transpileSingle(
  creds: Credentials,
  selector: string,
  o: SingleOptions,
): Promise<TranspileResult> {
  const url = new URL(`${creds.baseUrl}/api/v2/metrics/transpile`);
  url.searchParams.set('metricSelector', selector);
  applyCommonParams(url, o);
  if (o.scalarFunction) url.searchParams.set('scalarFunction', o.scalarFunction);
  if (o.format) url.searchParams.set('format', o.format);
  if (o.errorLocations) url.searchParams.set('errorLocations', 'true');

  const res = await fetch(url, { headers: { Authorization: creds.authHeader } });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status} from /api/v2/metrics/transpile: ${await res.text()}`);
  }
  const dto = (await res.json()) as TranspilationDTO;
  return normalize(selector, dto);
}

async function transpileBulk(
  creds: Credentials,
  selectors: string[],
  o: CommonOptions,
): Promise<TranspileResult[]> {
  const url = new URL(`${creds.baseUrl}/api/v2/metrics/transpileBulk`);
  applyCommonParams(url, o);

  const res = await fetch(url, {
    method: 'POST',
    headers: {
      Authorization: creds.authHeader,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ metricSelectors: selectors }),
  });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status} from /api/v2/metrics/transpileBulk: ${await res.text()}`);
  }
  const dto = (await res.json()) as CollectionDTO;
  const results = dto.transpilationResults ?? [];
  // Results come back in input order; guard against a short/misaligned list.
  return selectors.map((sel, i) =>
    normalize(
      sel,
      results[i] ?? {
        status: 'ERROR',
        errors: ['No transpilation result returned for this selector.'],
      },
    ),
  );
}

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

const USAGE = `Usage:
  node --experimental-strip-types scripts/transpile.ts single --selector '<selector>' [options]
  node --experimental-strip-types scripts/transpile.ts bulk   --input <file.json>     [options]

Subcommands:
  single   Transpile one selector/expression (GET /api/v2/metrics/transpile).
  bulk     Transpile many selectors in one call (POST /api/v2/metrics/transpileBulk).
           --input is a JSON file: either ["sel1","sel2"] or {"metricSelectors":[...]}.
           Use "-" to read the JSON from stdin.

Common options:
  --config <path>        Path to the credential file (default: .dtmigration).
  --output <path>        Write the JSON result to this file instead of stdout.
                         Use this when machine-reading the result: the file is
                         guaranteed to contain only the JSON, with no risk of
                         subprocess/log lines mixing in.
  --resolution <r>       Timestep (1m, 5m, 1h, 1w, 4M, 3y), a unit-less point
                         count >= 2 (120, 500), or Inf for a single point.
                         NOT "auto". Omit for the server default (120 points).
  --from <t>             Timeframe start (ISO-8601 or now-2h). Default: now-2h.
  --to <t>               Timeframe end (ISO-8601 or now).      Default: now.
  --mode <m>             lenient (default) | strict.
  --consumer <c>         api (default) | notebook.

single-only options:
  --scalar-function <f>  auto|avg|min|max|sum|count|last|median|value|percentile(n).
  --format pretty        Return pretty-printed DQL (default: compact).
  --error-locations      Attach {start,end} ranges to diagnostics.

Output: JSON array of normalized results, one per input selector. Written to
--output <path> when given, otherwise to stdout.`;

function readSelectorsFromInput(inputPath: string): string[] {
  const raw = inputPath === '-' ? readFileSync(0, 'utf8') : readFileSync(inputPath, 'utf8');
  const parsed = JSON.parse(raw) as unknown;
  const selectors = Array.isArray(parsed)
    ? parsed
    : (parsed as any)?.metricSelectors;
  if (!Array.isArray(selectors) || selectors.some((s) => typeof s !== 'string')) {
    throw new Error(
      `--input must be a JSON array of strings or {"metricSelectors": [...]}. Got: ${inputPath}`,
    );
  }
  if (selectors.length === 0) {
    throw new Error('--input contained no selectors.');
  }
  return selectors as string[];
}

async function main(): Promise<void> {
  const subcommand = process.argv[2];
  const args = process.argv.slice(3);

  // Support --help/-h after the subcommand as well; parseArgs in strict mode would throw otherwise.
  if (args.includes('--help') || args.includes('-h')) {
    console.log(USAGE);
    process.exit(0);
  }

  if (!subcommand || subcommand === '--help' || subcommand === '-h') {
    console.log(USAGE);
    process.exit(subcommand ? 0 : 1);
  }
  if (subcommand !== 'single' && subcommand !== 'bulk') {
    throw new Error(`Unknown subcommand "${subcommand}".\n\n${USAGE}`);
  }

  const { values } = parseArgs({
    args,
    options: {
      config: { type: 'string', default: '.dtmigration' },
      output: { type: 'string' },
      selector: { type: 'string' },
      input: { type: 'string' },
      resolution: { type: 'string' },
      from: { type: 'string' },
      to: { type: 'string' },
      mode: { type: 'string' },
      consumer: { type: 'string' },
      'scalar-function': { type: 'string' },
      format: { type: 'string' },
      'error-locations': { type: 'boolean', default: false },
    },
    allowPositionals: false,
  });

  if (values.mode && values.mode !== 'lenient' && values.mode !== 'strict') {
    throw new Error(`--mode must be "lenient" or "strict"; got "${values.mode}".`);
  }
  if (values.consumer && values.consumer !== 'api' && values.consumer !== 'notebook') {
    throw new Error(`--consumer must be "api" or "notebook"; got "${values.consumer}".`);
  }
  if (values.format && values.format !== 'pretty') {
    throw new Error(`--format only accepts "pretty"; got "${values.format}".`);
  }

  if (subcommand === 'bulk') {
    if (values.selector !== undefined) {
      throw new Error(`bulk does not accept --selector.\n\n${USAGE}`);
    }
    if (values['scalar-function'] !== undefined) {
      throw new Error(`bulk does not accept --scalar-function.\n\n${USAGE}`);
    }
    if (values.format !== undefined) {
      throw new Error(`bulk does not accept --format.\n\n${USAGE}`);
    }
    if (values['error-locations']) {
      throw new Error(`bulk does not accept --error-locations.\n\n${USAGE}`);
    }
  } else {
    if (values.input !== undefined) {
      throw new Error(`single does not accept --input.\n\n${USAGE}`);
    }
  }

  const creds = loadCredentials(values.config as string);
  const common: CommonOptions = {
    resolution: values.resolution,
    from: values.from,
    to: values.to,
    mode: values.mode as CommonOptions['mode'],
    consumer: values.consumer as CommonOptions['consumer'],
  };

  let results: TranspileResult[];
  if (subcommand === 'single') {
    if (!values.selector) {
      throw new Error(`single requires --selector.\n\n${USAGE}`);
    }
    const single: SingleOptions = {
      ...common,
      scalarFunction: values['scalar-function'],
      format: values.format as SingleOptions['format'],
      errorLocations: values['error-locations'] as boolean,
    };
    results = [await transpileSingle(creds, values.selector as string, single)];
  } else {
    if (!values.input) {
      throw new Error(`bulk requires --input.\n\n${USAGE}`);
    }
    const selectors = readSelectorsFromInput(values.input as string);
    results = await transpileBulk(creds, selectors, common);
  }

  const json = `${JSON.stringify(results, null, 2)}\n`;
  const outputPath = values.output as string | undefined;
  if (outputPath) {
    // Write straight to the file so the result can never be contaminated by
    // stray stdout/stderr lines (e.g. dtctl warnings). Progress note goes to
    // stderr, keeping the file byte-for-byte the JSON payload.
    writeFileSync(outputPath, json);
    console.error(`Wrote ${results.length} result(s) to ${outputPath}`);
  } else {
    process.stdout.write(json);
  }
}

main().catch((err: unknown) => {
  console.error(err instanceof Error ? err.message : String(err));
  process.exit(1);
});
