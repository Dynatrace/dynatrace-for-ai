// extract-timeseries-dashboard.js
//
// Token-efficient extractor: pulls every DQL query out of a Dynatrace dashboard
// and returns a compact TimeseriesDQLQuerySet[]. The caller (model or shell
// pipeline) never has to read the full dashboard JSON.
//
// Run with dtctl:
//   dtctl exec function -f scripts/extract-timeseries-dashboard.js \
//     --payload '{"id":"<dashboard-id-or-name>"}' -o json > queryset.json
//
// Payload shape:
//   { "id": "<id-or-name>", "titleFilter": "...", "listOnly": true, "compact": true, "includeSkipped": true }
//   - id              required. Document id, or a name (resolved via Document API search).
//   - titleFilter     optional. Case-insensitive substring match against tile title;
//                     when set, only matching tiles are returned. Pass a string like
//                     "Hosts network traffic" or a /regex/ string ("/^cpu/i").
//   - listOnly        optional. When true, return tile names without DQL — lightweight
//                     disambiguation call. Response has "tiles" instead of "queries".
//   - compact         optional. When true, each query object contains only {id, title, dqlQuery}
//                     (drops description, visualization, isTimeseries). In listOnly mode,
//                     drops visualization, returning {id, title} only.
//   - includeSkipped  optional. When true, include the full skipped[] array in the response.
//                     Default: only skippedCount is returned.
//
// Response (TimeseriesDQLQuerySet[] wrapped in an envelope):
//   {
//     "ok": true,
//     "documentId": "...", "documentName": "...", "documentVersion": 7,
//     "queries": [
//       { "id": "<tile-key>", "title": "...", "description": "...",
//         "dqlQuery": "timeseries avg(dt.host.cpu.usage)",
//         "visualization": "lineChart", "isTimeseries": true }
//     ],
//     "skipped": [ { "id": "...", "reason": "non-data tile" } ]
//   }
//
// On error: { "ok": false, "error": { "code": "...", "message": "..." } }

import { documentsClient } from '@dynatrace-sdk/client-document';

// Match `timeseries` either at the start of the query or after a pipe. The
// regex is run after stripping leading `//` line comments / `/* … */` block
// comments / blank lines, so a query like
//   `// some comment\ntimeseries sum(...)` still classifies as timeseries.
const TIMESERIES_RE = /(^|\|)\s*timeseries\b/i;

function stripLeadingCommentsAndWhitespace(query) {
  let s = String(query);
  while (true) {
    const trimmed = s.replace(/^\s+/, '');
    if (trimmed.startsWith('//')) {
      const nl = trimmed.indexOf('\n');
      s = nl === -1 ? '' : trimmed.slice(nl + 1);
      continue;
    }
    if (trimmed.startsWith('/*')) {
      const end = trimmed.indexOf('*/');
      s = end === -1 ? '' : trimmed.slice(end + 2);
      continue;
    }
    return trimmed;
  }
}

function classify(query) {
  if (typeof query !== 'string' || query.trim() === '') return false;
  const stripped = stripLeadingCommentsAndWhitespace(query);
  return TIMESERIES_RE.test(stripped);
}

// Accepts either a plain string (case-insensitive substring) or a /pattern/flags
// literal expressed as a string (e.g. "/^cpu/i") for regex matching.
//
// Tile titles often contain $variable placeholders (e.g. "CPU Usage $workload
// [Top $limit_graph_lines]"). When a direct substring match fails and the title
// has such placeholders, we convert the title into a regex by replacing each
// $word token with .* and test the caller's filter string against it. This lets
// a filter like "CPU Usage ppx-service [Top 500]" match the template title.
function compileTitleMatcher(filter) {
  if (filter === undefined || filter === null || filter === '') return null;
  const s = String(filter);
  const m = s.match(/^\/(.+)\/([gimsuy]*)$/);
  if (m) {
    try {
      // Strip stateful flags (g/y): re.test() is called per tile, and a stateful
      // regex advances lastIndex between calls, causing intermittent false negatives.
      const re = new RegExp(m[1], m[2].replace(/[gy]/g, ''));
      return (title) => re.test(String(title ?? ''));
    } catch (_) {
      // fall through to substring match
    }
  }
  const needle = s.toLowerCase();
  return (title) => {
    const raw = String(title ?? '');
    // 1. Direct case-insensitive substring match (fast path).
    if (raw.toLowerCase().includes(needle)) return true;
    // 2. If the tile title has $variable placeholders, build a regex from it
    //    so resolved values like "ppx-service" or "500" match the template.
    if (/\$\w/.test(raw)) {
      const escaped = raw.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const pattern = escaped.replace(/\\\$\w+/g, '.*');
      try {
        if (new RegExp(pattern, 'i').test(s)) return true;
      } catch (_) { /* ignore malformed pattern */ }
    }
    return false;
  };
}

// The dashboard tile schema has moved around across versions. Try the known
// locations in order and return the first non-empty DQL string found.
function pickQuery(tile) {
  const candidates = [
    tile.query,
    tile?.queryConfig?.query,
    tile?.querySettings?.query,
    tile?.data?.query,
    tile?.input?.value,
  ];
  for (const q of candidates) {
    if (typeof q === 'string' && q.trim() !== '') return q;
  }
  return null;
}

function pickDescription(tile) {
  return (
    tile?.description ||
    tile?.queryConfig?.description ||
    tile?.visualizationSettings?.description ||
    ''
  );
}

function pickVisualization(tile) {
  return (
    tile?.visualization ||
    tile?.visualizationSettings?.visualizationType ||
    tile?.type ||
    ''
  );
}

// Tiles can be either an object (modern dashboards) keyed by string indices or
// an array (older variants). Normalise to [ {id, tile}, ... ].
function normaliseTiles(tilesRaw) {
  if (!tilesRaw) return [];
  if (Array.isArray(tilesRaw)) {
    return tilesRaw.map((t, i) => ({ id: t?.id ?? String(i), tile: t }));
  }
  if (typeof tilesRaw === 'object') {
    return Object.entries(tilesRaw).map(([k, v]) => ({ id: k, tile: v }));
  }
  return [];
}

// The SDK's getDocument returns only metadata + an empty content shell. The
// real dashboard body comes back from downloadDocumentContent as a `_Binary`
// wrapper whose `.data` is a ReadableStream of UTF-8 JSON bytes.
async function readBinaryStream(bin) {
  const stream = bin?.data;
  if (!stream || typeof stream.getReader !== 'function') {
    throw new Error(
      `downloadDocumentContent returned ${bin?.constructor?.name ?? typeof bin}, expected _Binary`,
    );
  }
  const reader = stream.getReader();
  const chunks = [];
  let total = 0;
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    chunks.push(value);
    total += value.byteLength;
  }
  const buf = new Uint8Array(total);
  let off = 0;
  for (const c of chunks) {
    buf.set(c, off);
    off += c.byteLength;
  }
  return new TextDecoder().decode(buf);
}

async function fetchContent(id) {
  const bin = await documentsClient.downloadDocumentContent({ id });
  const text = await readBinaryStream(bin);
  return JSON.parse(text);
}

async function fetchDocument(idOrName) {
  let lookupError;
  // Try as ID first — preset/template dashboards (e.g. `my.dynatrace.*`) only
  // resolve this way.
  try {
    const raw = await documentsClient.getDocument({ id: idOrName });
    const metadata = raw?.metadata ?? raw;
    if (metadata?.id) {
      const content = await fetchContent(metadata.id);
      return { metadata, content };
    }
    lookupError = new Error(
      `getDocument returned no id; raw response: ${JSON.stringify(raw).slice(0, 200)}`,
    );
  } catch (e) {
    lookupError = e;
  }
  // Fall back to searching by exact name (only useful when the caller passed a
  // name).
  try {
    const list = await documentsClient.listDocuments({
      filter: `type=='dashboard' and name=='${idOrName.replace(/'/g, "\\'")}'`,
    });
    const items = list?.documents ?? list?.items ?? [];
    if (items.length === 1) {
      const metadata = items[0];
      const content = await fetchContent(metadata.id);
      return { metadata, content };
    }
    if (items.length > 1) {
      const err = new Error(
        `name is ambiguous (${items.length} matches): pass the document id instead`,
      );
      err.code = 'ambiguous';
      throw err;
    }
  } catch (e) {
    if (e.code === 'ambiguous') throw e;
  }
  const err = new Error(
    `dashboard not found: ${idOrName} (lookup error: ${lookupError?.message ?? lookupError})`,
  );
  err.code = 'not_found';
  throw err;
}

export default async function ({
  id,
  titleFilter,
  listOnly = false,
  compact = false,
  includeSkipped = false,
} = {}) {
  try {
    if (!id) {
      return {
        ok: false,
        error: { code: 'invalid_input', message: 'payload.id is required' },
      };
    }

    const { metadata: doc, content } = await fetchDocument(id);
    if (doc.type && doc.type !== 'dashboard') {
      return {
        ok: false,
        error: {
          code: 'wrong_type',
          message: `document ${doc.id} is type "${doc.type}", expected "dashboard"`,
        },
      };
    }

    if (!content) {
      return {
        ok: false,
        error: {
          code: 'no_content',
          message: `document ${doc.id} returned no content`,
        },
      };
    }
    const tiles = normaliseTiles(content?.tiles);
    const titleMatches = compileTitleMatcher(titleFilter);

    const queries = [];
    const tileList = [];
    const skipped = [];
    for (const { id: tileId, tile } of tiles) {
      if (!tile || typeof tile !== 'object') continue;
      const tileType = tile.type ?? '';
      if (['markdown', 'image', 'group'].includes(tileType)) {
        skipped.push({ id: tileId, reason: `non-data tile (${tileType})` });
        continue;
      }
      const tileTitle = tile.title ?? '';
      if (titleMatches && !titleMatches(tileTitle)) {
        skipped.push({ id: tileId, reason: 'title did not match filter' });
        continue;
      }
      if (listOnly) {
        tileList.push(compact
          ? { id: tileId, title: tileTitle }
          : { id: tileId, title: tileTitle, visualization: pickVisualization(tile) });
        continue;
      }
      const dqlQuery = pickQuery(tile);
      if (!dqlQuery) {
        skipped.push({ id: tileId, reason: 'no DQL query found' });
        continue;
      }
      const isTimeseries = classify(dqlQuery);
      if (!isTimeseries) {
        skipped.push({ id: tileId, reason: 'not a timeseries query' });
        continue;
      }
      queries.push(compact
        ? { id: tileId, title: tileTitle, dqlQuery }
        : { id: tileId, title: tileTitle, description: pickDescription(tile), dqlQuery, visualization: pickVisualization(tile), isTimeseries });
    }

    const skippedSummary = includeSkipped
      ? { skipped }
      : { skippedCount: skipped.length };

    if (listOnly) {
      return {
        ok: true,
        documentId: doc.id,
        documentName: doc.name,
        documentVersion: doc.version,
        tiles: tileList,
        ...skippedSummary,
      };
    }

    return {
      ok: true,
      documentId: doc.id,
      documentName: doc.name,
      documentVersion: doc.version,
      queries,
      ...skippedSummary,
    };
  } catch (e) {
    return {
      ok: false,
      error: {
        code: e.code ?? 'internal_error',
        message: e.message ?? String(e),
      },
    };
  }
}
