// run-analyzer.js
//
// Generic Davis analyzer runner for a TimeseriesDQLQuerySet
// (the output of extract-timeseries-dashboard.js / extract-timeseries-notebook.js).
//
// Wraps the common execute → poll → concurrent pattern so each Davis analyzer
// call doesn't need its own script.
//
// Run with dtctl (no jq needed — the script normalizes the array / envelope /
// dtctl-output shapes internally, and unwraps the -o json {"result":{...}} wrapper):
//   dtctl exec function -f scripts/extract-timeseries-dashboard.js \
//     --payload '{"id":"<dashboard-id>"}' -o json > queryset.json
//
//   dtctl exec function -f scripts/run-analyzer.js \
//     --payload '{
//       "analyzerName": "dt.statistics.NoveltyScoreAnalyzer",
//       "queries": '"$(cat queryset.json)"'
//     }' -o json
//
// For large querysets, build a payload file and use --data instead of inlining:
//   { printf '{"analyzerName":"dt.statistics.NoveltyScoreAnalyzer","queries":'; \
//     cat queryset.json; printf '}'; } > payload.json
//   dtctl exec function -f scripts/run-analyzer.js --data payload.json -o json
//
// Payload:
//   {
//     "analyzerName":   "dt.statistics.NoveltyScoreAnalyzer"   (required)
//     "queries":        TimeseriesDQLQuery[]                    (required)
//                       Accepts the raw array OR the extractor envelope (reads .queries).
//     "timeframe":      { "startTime": "now-1h", "endTime": "now" }
//                       also accepts { "from": "...", "to": "..." }
//                       (optional, default last 1 hour)
//     "analyzerParams": { ... }
//                       Extra fields merged into each analyzer call body.
//                       Use for analyzer-specific knobs that don't belong in
//                       generalParameters. Examples:
//                         Anomaly detection: { "trainingTimeframe": { "startTime": "now-8d", "endTime": "now-1d" } }
//                         Novelty scoring:   { "detectionMode": "ALL", "minNoveltyScore": 0 }
//                       (optional, default {})
//     "metricQuery":    "timeseries avg(dt.host.cpu.usage)"
//                       When set, switches to correlation mode.
//                       For Pearson analyzers (name contains "pearson"):
//                         referenceTimeseries    = metricQuery (the primary)
//                         toCorrelateTimeseries  = each query in the set
//                       For other correlation analyzers:
//                         timeSeriesData           = metricQuery (the primary)
//                         correlatedTimeSeriesData = each query in the set
//                       When unset, each query is used as timeSeriesData independently.
//                       (optional)
//     "metricQueryFrom": <full output of a previous run-analyzer.js call>
//                       Alternative to metricQuery: accepts the raw dtctl output
//                       (or unwrapped result) of a prior run and picks the
//                       highest-scored result's dqlQuery as the primary.
//                       Useful for chaining anomaly detection → correlation without
//                       a local jq step. metricQuery takes precedence if both are set.
//                       (optional)
//     "variables":      { "varName": "value", ... }
//                       Substitutes $varName tokens in DQL before execution.
//                       Build from URL vfilter_* params: strip the "vfilter_" prefix.
//                       Trailing * wildcards on values are stripped automatically.
//                       (optional)
//     "maxConcurrent":  4   (optional, default 4)
//     "minScore":       0.5
//                       When set, only results whose detected score >= minScore are returned.
//                       Results with no detectable score are dropped. (optional)
//     "scoreField":     "noveltyScore"
//                       Explicit field name to read the score from. When omitted, auto-detects
//                       from: noveltyScore, anomalyScore, correlationCoefficient, correlation,
//                       coefficient, or any field whose name contains "score". (optional)
//   }
//
// Response:
//   {
//     "ok": true,
//     "checkedAt": "...",
//     "analyzerName": "...",
//     "summary": { "checked": N, "completed": K, "errors": E },
//     "results": [
//       {
//         "id": "...", "title": "...", "dqlQuery": "...",
//         "output": <raw analyzer output>,
//         "executionStatus": "COMPLETED"
//       }
//     ],
//     "errors": [ { "id": "...", "error": "..." } ]
//   }

import { analyzersClient } from '@dynatrace-sdk/client-davis-analyzers';

const DEFAULT_TIMEFRAME = { startTime: 'now-1h', endTime: 'now' };

// ─── Analyzer execute + poll ──────────────────────────────────────────────────

async function pollAnalyzer(analyzerName, requestToken, maxAttempts = 30) {
  for (let i = 0; i < maxAttempts; i++) {
    const poll = await analyzersClient.pollAnalyzerExecution({ analyzerName, requestToken });
    if (poll?.result?.executionStatus === 'COMPLETED') return poll;
    if (poll?.result?.executionStatus === 'FAILED') {
      const msg = poll?.result?.errorMessage ?? 'analyzer execution failed';
      const err = new Error(msg);
      err.code = 'analyzer_failed';
      throw err;
    }
    await new Promise((r) => setTimeout(r, 2000));
  }
  const err = new Error('analyzer execution timed out');
  err.code = 'timeout';
  throw err;
}

async function executeAnalyzer(analyzerName, body) {
  const res = await analyzersClient.executeAnalyzer({ analyzerName, body });
  if (res?.requestToken && res?.result === undefined) {
    return await pollAnalyzer(analyzerName, res.requestToken);
  }
  // Immediate (non-polled) response: surface a terminal FAILED status as an error
  // rather than returning it as a successful item. (The polled path already throws
  // on FAILED via pollAnalyzer; RUNNING/COMPLETED are left to the caller.)
  if (res?.result?.executionStatus === 'FAILED') {
    const err = new Error(res?.result?.errorMessage ?? 'analyzer execution failed');
    err.code = 'analyzer_failed';
    throw err;
  }
  return res;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function normalizeTimeframe(tf) {
  if (!tf) return null;
  // Fall back to defaults per-field so a partial timeframe (e.g. only startTime,
  // or an empty {}) never yields undefined fields in the analyzer request body.
  return {
    startTime: tf.startTime ?? tf.from ?? DEFAULT_TIMEFRAME.startTime,
    endTime: tf.endTime ?? tf.to ?? DEFAULT_TIMEFRAME.endTime,
  };
}

function normalizeQueries(payload) {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.queries)) return payload.queries;
  if (Array.isArray(payload?.result?.queries)) return payload.result.queries; // dtctl -o json wrapper
  return null;
}

// Accepts the full output of a previous run-analyzer.js call (raw dtctl output or
// unwrapped result) and returns the dqlQuery of the highest-scored result.
function topDqlFromResults(input, scoreField) {
  const results = input?.result?.results ?? input?.results;
  if (!Array.isArray(results) || results.length === 0) return null;
  const sorted = [...results].sort((a, b) => {
    const sa = extractScore(a.output, scoreField) ?? -Infinity;
    const sb = extractScore(b.output, scoreField) ?? -Infinity;
    return sb - sa;
  });
  return sorted[0]?.dqlQuery ?? null;
}

// Strip `| timeframe ...` pipeline stages embedded in dashboard DQL so that
// caller-supplied defaultTimeframe parameters take effect for historical windows.
// Only strips when the caller provides an absolute (non-now) start timestamp.
function stripEmbeddedTimeframe(dql, startTime) {
  if (!startTime || typeof startTime !== 'string' || startTime.startsWith('now')) return dql;
  return dql.replace(/\|\s*timeframe\b[^|]*/gi, ' ').replace(/\s+/g, ' ').trim();
}

// Substitute $varName tokens from URL vfilter_* parameters before execution.
// Values that look like plain numbers are inserted unquoted; everything else
// is JSON-quoted. Trailing wildcard (*) is stripped (DQL in() doesn't support
// wildcards). Unresolved $variables are cleaned up from filter clauses to avoid
// silently dropping entity filters or generating DQL errors.
function applyVariables(dql, variables) {
  if (!variables || typeof variables !== 'object') return dql;
  let result = dql;
  for (const [name, rawVal] of Object.entries(variables)) {
    const val = String(rawVal).replace(/\*$/, '');
    const quoted = /^\d+(\.\d+)?$/.test(val) ? val : JSON.stringify(val);
    const re = new RegExp(
      '\\$' + name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '(?=[^a-zA-Z0-9_]|$)',
      'g',
    );
    result = result.replace(re, quoted);
  }
  // Drop filter clauses referencing still-unresolved $variables.
  const EXPR = '[^$]*?';
  const VARNAME = '\\$[a-zA-Z_][a-zA-Z0-9_]*';
  result = result.replace(new RegExp(`\\s*\\band\\b\\s+(?:not\\s+)?in\\s*\\(${EXPR},\\s*${VARNAME}\\s*\\)`, 'gi'), '');
  result = result.replace(new RegExp(`(?:not\\s+)?in\\s*\\(${EXPR},\\s*${VARNAME}\\s*\\)\\s*\\band\\b\\s*`, 'gi'), '');
  result = result.replace(new RegExp(`\\bnot\\s+in\\s*\\(${EXPR},\\s*${VARNAME}\\s*\\)`, 'gi'), 'false');
  result = result.replace(new RegExp(`\\bin\\s*\\(${EXPR},\\s*${VARNAME}\\s*\\)`, 'gi'), 'true');
  result = result.replace(/\$[a-zA-Z_][a-zA-Z0-9_]*/g, 'null');
  return result;
}

const SCORE_FIELDS = ['noveltyScore', 'anomalyScore', 'correlationCoefficient', 'correlation', 'coefficient'];

// Analyzer outputs are nested (arrays of per-dimension objects, and scores can sit
// one or two levels in — e.g. correlationCoefficient in each array element, or
// novelties[].noveltyScore). Walk the structure looking for an explicit scoreField
// or one of the known score fields, then fall back to any top-level "*score*" number.
function findKnownScore(node, scoreField) {
  if (node == null || typeof node !== 'object') return null;
  if (Array.isArray(node)) {
    for (const el of node) {
      const s = findKnownScore(el, scoreField);
      if (s != null) return s;
    }
    return null;
  }
  if (scoreField && typeof node[scoreField] === 'number') return node[scoreField];
  for (const field of SCORE_FIELDS) {
    if (typeof node[field] === 'number') return node[field];
  }
  for (const v of Object.values(node)) {
    if (v && typeof v === 'object') {
      const s = findKnownScore(v, scoreField);
      if (s != null) return s;
    }
  }
  return null;
}

function extractScore(output, scoreField) {
  const known = findKnownScore(output, scoreField);
  if (known != null) return known;
  // Best-effort fallback for unknown analyzers: any top-level "*score*" number.
  if (output && typeof output === 'object' && !Array.isArray(output)) {
    for (const [k, v] of Object.entries(output)) {
      if (k.toLowerCase().includes('score') && typeof v === 'number') return v;
    }
  }
  return null;
}

async function mapConcurrent(items, n, fn) {
  const out = new Array(items.length);
  let cursor = 0;
  const workers = Array.from({ length: Math.min(n, items.length) }, async () => {
    while (true) {
      const i = cursor++;
      if (i >= items.length) return;
      out[i] = await fn(items[i], i);
    }
  });
  await Promise.all(workers);
  return out;
}

// ─── Main export ──────────────────────────────────────────────────────────────

export default async function ({
  analyzerName,
  queries: queriesInput,
  timeframe,
  analyzerParams = {},
  metricQuery,
  metricQueryFrom,
  variables,
  maxConcurrent = 4,
  minScore,
  scoreField,
} = {}) {
  try {
    if (typeof analyzerName !== 'string' || analyzerName.trim() === '') {
      return {
        ok: false,
        error: { code: 'invalid_input', message: 'payload.analyzerName must be a non-empty string' },
      };
    }

    // Resolve metricQuery from a previous run's output when not given directly.
    if (metricQuery == null && metricQueryFrom != null) {
      metricQuery = topDqlFromResults(metricQueryFrom, scoreField);
      if (metricQuery == null) {
        return {
          ok: false,
          error: { code: 'invalid_input', message: 'metricQueryFrom contained no results with a dqlQuery' },
        };
      }
    }

    const queries = normalizeQueries(queriesInput);
    if (!Array.isArray(queries) || queries.length === 0) {
      return {
        ok: false,
        error: {
          code: 'invalid_input',
          message: 'payload.queries must be a non-empty TimeseriesDQLQuerySet (array or extractor envelope)',
        },
      };
    }

    const tf = normalizeTimeframe(timeframe) ?? DEFAULT_TIMEFRAME;
    const work = queries.filter((q) => q && typeof q.dqlQuery === 'string' && q.isTimeseries !== false);

    // The primary/correlation query gets the same treatment as the per-tile queries:
    // strip embedded `| timeframe` for absolute windows and substitute $variables.
    // Otherwise a primary sourced from an extracted tile (or metricQueryFrom) could
    // still carry $var tokens or a different embedded window than the correlated set.
    const resolvedMetricQuery = metricQuery != null
      ? applyVariables(stripEmbeddedTimeframe(metricQuery, tf.startTime), variables)
      : null;

    // Sanitize fan-out: coerce to a positive integer so a bad value (0, negative,
    // non-numeric) can't silently produce zero workers and an empty result set.
    const concurrency = Math.max(1, Math.floor(Number(maxConcurrent)) || 4);

    const results = await mapConcurrent(work, concurrency, async (q) => {
      try {
        const resolvedDQL = applyVariables(
          stripEmbeddedTimeframe(q.dqlQuery, tf.startTime),
          variables,
        );

        const pearsonMode = /pearson/i.test(analyzerName);
        const body = resolvedMetricQuery
          ? pearsonMode
            ? {
                referenceTimeseries: resolvedMetricQuery,
                toCorrelateTimeseries: resolvedDQL,
                generalParameters: { timeframe: tf, resolveDimensionalQueryData: true },
                ...analyzerParams,
              }
            : {
                timeSeriesData: resolvedMetricQuery,
                correlatedTimeSeriesData: resolvedDQL,
                generalParameters: { timeframe: tf, resolveDimensionalQueryData: true },
                ...analyzerParams,
              }
          : {
              timeSeriesData: resolvedDQL,
              generalParameters: { timeframe: tf, resolveDimensionalQueryData: true },
              ...analyzerParams,
            };

        const raw = await executeAnalyzer(analyzerName, body);
        return {
          ok: true,
          item: {
            id: q.id,
            title: q.title ?? '',
            dqlQuery: q.dqlQuery,
            output: raw?.result?.output ?? null,
            executionStatus: raw?.result?.executionStatus ?? 'COMPLETED',
          },
        };
      } catch (e) {
        return { ok: false, id: q.id, error: e.message ?? String(e) };
      }
    });

    const completed = [];
    const errors = [];
    for (const r of results) {
      if (r.ok) completed.push(r.item);
      else errors.push({ id: r.id, error: r.error });
    }

    const filtered = minScore != null
      ? completed.filter((item) => {
          const score = extractScore(item.output, scoreField);
          return score != null && score >= minScore;
        })
      : completed;

    return {
      ok: true,
      checkedAt: new Date().toISOString(),
      analyzerName,
      summary: { checked: work.length, completed: completed.length, errors: errors.length },
      results: filtered,
      errors,
    };
  } catch (e) {
    return {
      ok: false,
      error: { code: e.code ?? 'internal_error', message: e.message ?? String(e) },
    };
  }
}
