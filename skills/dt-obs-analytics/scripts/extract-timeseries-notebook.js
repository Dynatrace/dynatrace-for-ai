// extract-timeseries-notebook.js
//
// Same idea as extract-timeseries-dashboard.js but for notebooks. Notebooks
// store DQL inside sections/cells, not tiles, and the cell schema has a couple
// of variants — `sections[].content.input.value` (modern) and
// `cells[].state.input.value` (older). Both are handled.
//
// Run with dtctl:
//   dtctl exec function -f scripts/extract-timeseries-notebook.js \
//     --payload '{"id":"<notebook-id-or-name>"}' -o json > queryset.json
//
// Payload:
//   { "id": "<id-or-name>", "titleFilter": "...", "compact": true, "includeSkipped": true }
//   - titleFilter     optional. Case-insensitive substring or "/regex/flags" literal.
//   - compact         optional. When true, each query object contains only {id, title, dqlQuery}.
//   - includeSkipped  optional. When true, return full skipped[] array. Default: skippedCount only.
//
// Response: same envelope as extract-timeseries-dashboard.js.

import { documentsClient } from '@dynatrace-sdk/client-document';

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

function compileTitleMatcher(filter) {
  if (filter === undefined || filter === null || filter === '') return null;
  const s = String(filter);
  const m = s.match(/^\/(.+)\/([gimsuy]*)$/);
  if (m) {
    try {
      // Strip stateful flags (g/y): re.test() is called per cell, and a stateful
      // regex advances lastIndex between calls, causing intermittent false negatives.
      const re = new RegExp(m[1], m[2].replace(/[gy]/g, ''));
      return (title) => re.test(String(title ?? ''));
    } catch (_) {
      // fall through to substring match
    }
  }
  const needle = s.toLowerCase();
  return (title) => String(title ?? '').toLowerCase().includes(needle);
}

function pickQuery(cell) {
  const candidates = [
    cell?.content?.input?.value,
    cell?.state?.input?.value,
    cell?.input?.value,
    cell?.query,
    cell?.content?.query,
  ];
  for (const q of candidates) {
    if (typeof q === 'string' && q.trim() !== '') return q;
  }
  return null;
}

function pickTitle(cell) {
  return (
    cell?.title ||
    cell?.content?.title ||
    cell?.state?.title ||
    ''
  );
}

function pickDescription(cell) {
  return (
    cell?.description ||
    cell?.content?.description ||
    cell?.state?.description ||
    ''
  );
}

function pickKind(cell) {
  return (
    cell?.content?.type ||
    cell?.state?.type ||
    cell?.type ||
    ''
  );
}

function pickVisualization(cell) {
  return (
    cell?.content?.visualization ||
    cell?.state?.visualization ||
    cell?.visualization ||
    ''
  );
}

// Notebooks have either `sections` (modern) or `cells` (older). Both come back
// as arrays. Normalise to [ {id, cell}, ... ].
function normaliseCells(content) {
  const arr =
    (Array.isArray(content?.sections) && content.sections) ||
    (Array.isArray(content?.cells) && content.cells) ||
    [];
  return arr.map((c, i) => ({ id: c?.id ?? String(i), cell: c }));
}

// See extract-timeseries-dashboard.js — downloadDocumentContent returns a
// _Binary whose `.data` is a ReadableStream of UTF-8 JSON bytes.
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
  try {
    const list = await documentsClient.listDocuments({
      filter: `type=='notebook' and name=='${idOrName.replace(/'/g, "\\'")}'`,
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
    `notebook not found: ${idOrName} (lookup error: ${lookupError?.message ?? lookupError})`,
  );
  err.code = 'not_found';
  throw err;
}

export default async function ({
  id,
  titleFilter,
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
    if (doc.type && doc.type !== 'notebook') {
      return {
        ok: false,
        error: {
          code: 'wrong_type',
          message: `document ${doc.id} is type "${doc.type}", expected "notebook"`,
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
    const cells = normaliseCells(content);
    const titleMatches = compileTitleMatcher(titleFilter);

    const queries = [];
    const skipped = [];
    for (const { id: cellId, cell } of cells) {
      if (!cell || typeof cell !== 'object') continue;
      const kind = pickKind(cell);
      // Notebooks support many cell kinds: dql, markdown, sql, businessEvent
      // queries, etc. Anything not a DQL/query cell is skipped.
      if (kind && !['dql', 'query', 'data'].includes(kind)) {
        skipped.push({ id: cellId, reason: `non-DQL cell (${kind})` });
        continue;
      }
      const cellTitle = pickTitle(cell);
      if (titleMatches && !titleMatches(cellTitle)) {
        skipped.push({ id: cellId, reason: 'title did not match filter' });
        continue;
      }
      const dqlQuery = pickQuery(cell);
      if (!dqlQuery) {
        skipped.push({ id: cellId, reason: 'no DQL query found' });
        continue;
      }
      const isTimeseries = classify(dqlQuery);
      if (!isTimeseries) {
        skipped.push({ id: cellId, reason: 'not a timeseries query' });
        continue;
      }
      queries.push(compact
        ? { id: cellId, title: cellTitle, dqlQuery }
        : { id: cellId, title: cellTitle, description: pickDescription(cell), dqlQuery, visualization: pickVisualization(cell), isTimeseries });
    }

    const skippedSummary = includeSkipped
      ? { skipped }
      : { skippedCount: skipped.length };

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
