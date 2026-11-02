/**
 * migration-lookup.ts — Deterministic core for classic→new cloud metric detection and lookup.
 *
 * Pure functions over JSON inputs — no file I/O.  Runs in DT Assist (file-read + document
 * tools) and in Node for IDE use.  Callers load JSON files and pass the parsed data in.
 *
 * Primary API:
 *   loadDetectionPatterns(json)                      → DetectionPatterns
 *   detectClassicMetrics(text, provider, patterns)   → string[]
 *   extractClassicMetricKeys(text, provider, patterns) → string[]
 *   detectClassicEntities(text, provider, patterns)  → string[]
 *   scanAsset(...)                                   → DetectionFinding[]
 *   lookupMetricKey(key, index)                      → MetricMapping | null
 *
 * High-level aggregators (mirror detect-classic-patterns.py scanners):
 *   scanDashboards / scanNotebooks / scanClassicDashboards
 *   scanMetricEvents / scanSlos / scanInfrastructureDetection / scanDavisDetectors
 *   detectAll(assessmentData, providers, patterns)   → AllFindings
 *
 * JSON output field names use snake_case to match the Python script schema and enable
 * byte-for-byte parity tests without field-name normalization.
 *
 * Data sources expected from callers (pre-parsed JSON):
 *   classic-detection-patterns.json   → loadDetectionPatterns()
 *   per-key-mappings.json             → lookupMetricKey() index parameter
 */

// ── Types ────────────────────────────────────────────────────────────────────

export type Provider = "aws" | "azure" | "gcp";
export type Availability = "recommended" | "autodiscovered" | "none";
export type Confidence = "high" | "low";

export interface MetricMapping {
  bestDacKey: string;
  availability: Availability;
}

export interface DetectionPatterns {
  prefixes: Partial<Record<Provider, string[]>>;
  streamsRe: Partial<Record<Provider, RegExp | null>>;
  entityTypes: Partial<Record<Provider, string[]>>;
}

export interface DetectionFinding {
  asset_id: string;
  asset_name: string;
  asset_type: string;
  provider: Provider;
  metric_prefixes: string[];
  metric_keys: string[];
  entity_types: string[];
  entity_selectors: string[];
  confidence: Confidence;
  blockers: string[];
  location: string;
  details: Record<string, unknown>;
}

export interface AllFindings {
  schema_version: "1.0";
  dashboards: DetectionFinding[];
  metric_events: DetectionFinding[];
  slos: DetectionFinding[];
  infrastructure_detection: DetectionFinding[];
  davis_detectors: DetectionFinding[];
  notebooks: DetectionFinding[];
  classic_dashboards: DetectionFinding[];
}

// Input shapes (loosely typed — we only access fields we know about)
type JsonObject = Record<string, unknown>;
type JsonValue = string | number | boolean | null | JsonObject | JsonValue[];

// ── Pattern loading ──────────────────────────────────────────────────────────

const DEFAULT_STREAMS_RE_AWS =
  /^cloud\.aws\.[a-z][a-z0-9_]*\.[a-z][a-zA-Z0-9]*By[A-Z][a-zA-Z0-9]*$/;

export function loadDetectionPatterns(json: unknown): DetectionPatterns {
  const data = json as JsonObject;
  const providers = ((data["providers"] ?? {}) as Record<string, JsonObject>);
  const prefixes: Partial<Record<Provider, string[]>> = {};
  const streamsRe: Partial<Record<Provider, RegExp | null>> = {};
  const entityTypes: Partial<Record<Provider, string[]>> = {};

  for (const [p, d] of Object.entries(providers)) {
    const provider = p as Provider;
    prefixes[provider] = (d["classic_metric_prefixes"] ?? []) as string[];
    entityTypes[provider] = (d["classic_entity_types"] ?? []) as string[];
    const reStr = d["metric_streams_re"] as string | null | undefined;
    if (reStr) {
      streamsRe[provider] = new RegExp(reStr);
    } else {
      streamsRe[provider] = provider === "aws" ? DEFAULT_STREAMS_RE_AWS : null;
    }
  }
  return { prefixes, streamsRe, entityTypes };
}

// ── Key normalization ────────────────────────────────────────────────────────

export function stripSelectorModifiers(key: string): string {
  // Prefixed keys: builtin:x.y or ext:x.y — the first colon is part of the key;
  // any subsequent colon starts a selector modifier chain.
  const lower = key.toLowerCase();
  if (lower.startsWith("builtin:") || lower.startsWith("ext:")) {
    const prefixEnd = key.indexOf(":") + 1;
    const rest = key.slice(prefixEnd);
    const colon = rest.indexOf(":");
    return colon !== -1 ? key.slice(0, prefixEnd + colon) : key;
  }
  // Unprefixed (dt.cloud.aws.* / cloud.aws.*): first colon starts modifiers.
  const colon = key.indexOf(":");
  return colon !== -1 ? key.slice(0, colon) : key;
}

export function normalizeBuiltinKey(key: string): string | null {
  // builtin:cloud.aws.ec2.* → builtin:aws.ec2.*
  const lower = key.toLowerCase();
  if (lower.startsWith("builtin:cloud.")) {
    return "builtin:" + key.slice("builtin:cloud.".length);
  }
  // dt.cloud.aws.ec2.cpu → builtin:aws.ec2.cpu
  const m = /^dt\.cloud\.(\w+)\.(.+)$/i.exec(key);
  if (m) return `builtin:${m[1]}.${m[2]}`;
  return null;
}

export function stripDimensionSuffix(key: string): string | null {
  // ext:cloud.aws.lambda.durationByResource → ext:cloud.aws.lambda.duration
  const m = /By[A-Z][a-zA-Z]*$/.exec(key);
  return m ? key.slice(0, m.index) : null;
}

export function extractServiceSegment(key: string, provider: Provider): string | null {
  const patterns: Partial<Record<Provider, RegExp[]>> = {
    aws: [
      /^(?:ext|builtin):cloud\.aws\.([^.]+)\./i,
      /^builtin:aws\.([^.]+)\./i,
      /^(?:dt\.)?cloud\.aws\.([^.]+)\./i,
    ],
    azure: [
      /^(?:ext|builtin):cloud\.azure\.([^.]+)\./i,
      /^builtin:azure\.([^.]+)\./i,
      /^(?:dt\.)?cloud\.azure\.([^.]+)\./i,
    ],
    gcp: [
      /^(?:ext|builtin):cloud\.gcp\.([^.]+)\./i,
      /^(?:dt\.)?cloud\.gcp\.([^.]+)\./i,
    ],
  };
  for (const re of patterns[provider] ?? []) {
    const m = re.exec(key);
    if (m) return m[1];
  }
  return null;
}

// Public alias — use when grouping findings by service to avoid naive prefix stripping.
export const getServiceSegment = extractServiceSegment;

// ── Metric lookup via pre-built index ────────────────────────────────────────

/**
 * Look up a classic metric key in the pre-built per-key-mappings.json index.
 * Applies the normalization chain (steps 1–4) before giving up:
 *   1. Exact match
 *   2. Strip selector modifiers (:avg, :splitBy, …)
 *   3a. dt.cloud.* → builtin:cloud.* (Grail prefix; matches current DAC builtInMetricKey format)
 *   3b. builtin:cloud.* → builtin:* (Cassandra prefix; fallback for older DAC entries)
 *   4. Strip dimension suffix (By[A-Z].*) and retry (also with normalized keys)
 * Step 5 (service-segment → namespace scan) requires the full DAC database and is
 * handled at index-build time by build-per-key-mappings.py — not at query time.
 */
export function lookupMetricKey(
  key: string,
  index: Record<string, MetricMapping>,
): MetricMapping | null {
  const hit = (k: string) => index[k.toLowerCase()] ?? null;

  let result = hit(key);
  if (result) return result;

  const clean = stripSelectorModifiers(key);
  if (clean !== key) {
    result = hit(clean);
    if (result) return result;
  }
  const base = clean !== key ? clean : key;

  // Step 3a: dt.cloud.<provider>.* → builtin:cloud.<provider>.* (current DAC Grail format)
  const grailMatch = /^dt\.cloud\.(\w+)\.(.+)$/i.exec(base);
  if (grailMatch) {
    result = hit(`builtin:cloud.${grailMatch[1]}.${grailMatch[2]}`);
    if (result) return result;
  }

  // Step 3b: builtin:cloud.* → builtin:* (Cassandra format for older DAC entries)
  const normalized = normalizeBuiltinKey(base);
  if (normalized) {
    result = hit(normalized);
    if (result) return result;
  }

  // Step 4: strip dimension suffix (ByFoo) and retry both normalized forms
  const stripped = stripDimensionSuffix(base);
  if (stripped && stripped !== base) {
    result = hit(stripped);
    if (result) return result;
    if (grailMatch) {
      const grailStripped = stripDimensionSuffix(`builtin:cloud.${grailMatch[1]}.${grailMatch[2]}`);
      if (grailStripped) { result = hit(grailStripped); if (result) return result; }
    }
    if (normalized) {
      const normStripped = stripDimensionSuffix(normalized);
      if (normStripped && normStripped !== normalized) {
        result = hit(normStripped);
        if (result) return result;
      }
    }
  }

  return null;
}

// ── Classic pattern detection ────────────────────────────────────────────────

export function detectClassicMetrics(
  text: string,
  provider: Provider,
  patterns: DetectionPatterns,
): string[] {
  const prefixes = patterns.prefixes[provider] ?? [];
  const found = new Set<string>();
  const lower = text.toLowerCase();

  for (const prefix of prefixes) {
    // AWS cloud.aws.*: accept any valid key token (classic built-in, non-built-in, or Metric Streams).
    // New-connection keys share the .By.PascalCase format; disambiguation is a later step.
    if (provider === "aws" && prefix === "cloud.aws.") {
      if (/cloud\.aws\.[a-z0-9_]+\.[a-zA-Z0-9]/.test(text)) {
        found.add(prefix);
      }
      continue;
    }
    // GCP: only flag classic keys (2nd segment ends _googleapis_com)
    if (provider === "gcp" && prefix === "cloud.gcp.") {
      if (/cloud\.gcp\.[a-z0-9]+_googleapis_com\./.test(text)) {
        found.add(prefix);
      }
      continue;
    }
    if (lower.includes(prefix.toLowerCase())) {
      found.add(prefix);
    }
  }
  return [...found].sort();
}

export function extractClassicMetricKeys(
  text: string,
  provider: Provider,
  patterns: DetectionPatterns,
): string[] {
  const prefixes = patterns.prefixes[provider] ?? [];
  const found = new Set<string>();
  // Normalize quoted segments: ext:cloud.aws.foo."4xxErrorSum" → ...foo.4xxErrorSum
  const normalizedText = text.replace(/\."([^"]+)"/g, ".$1");
  const lower = normalizedText.toLowerCase();

  for (const prefix of prefixes) {
    const lp = prefix.toLowerCase();
    let pos = 0;
    while (pos < lower.length) {
      const idx = lower.indexOf(lp, pos);
      if (idx === -1) break;

      // Skip if this occurrence is embedded in a longer prefix (e.g. ext:cloud.aws.*)
      if (idx > 0 && lower[idx - 1] === ":") {
        pos = idx + lp.length;
        continue;
      }

      const tokenMatch = /^[\w.:-]+/.exec(normalizedText.slice(idx));
      if (tokenMatch) {
        let key = tokenMatch[0];
        // Strip aggregation suffixes and everything after (:avg, :sum, :count, …)
        key = key.replace(
          /:(?:avg|min|max|sum|count|value|auto|fold|default|first|last|percentile\d*).*/i,
          "",
        );
        // Strip trailing DQL method-call suffix that the token extractor left behind
        key = key.replace(/:[a-zA-Z][a-zA-Z0-9]*$/, "");

        // AWS: require at least svc.metric — reject bare cloud.aws. or cloud.aws.foo
        if (provider === "aws" && key.startsWith("cloud.aws.")) {
          if (!/^cloud\.aws\.[a-z0-9_]+\.[a-zA-Z0-9]/.test(key)) {
            pos = idx + 1;
            continue;
          }
        }
        // GCP: only accept _googleapis_com keys
        if (provider === "gcp" && key.startsWith("cloud.gcp.")) {
          if (!/^cloud\.gcp\.[a-z0-9]+_googleapis_com\./.test(key)) {
            pos = idx + 1;
            continue;
          }
        }

        found.add(key);
      }
      pos = idx + prefix.length;
    }
  }
  return [...found].sort();
}

export function detectClassicEntities(
  text: string,
  provider: Provider,
  patterns: DetectionPatterns,
): string[] {
  const types = patterns.entityTypes[provider] ?? [];
  const found = new Set<string>();
  for (const et of types) {
    if (new RegExp(`fetch\\s+dt\\.entity\\.${et}\\b`, "i").test(text)) {
      found.add(`dt.entity.${et}`);
    }
  }
  // Azure wildcard — any dt.entity.azure_* fetch
  if (provider === "azure" && /fetch\s+dt\.entity\.azure_/i.test(text)) {
    found.add("dt.entity.azure_*");
  }
  return [...found].sort();
}

export function detectClassicEntitySelectors(
  text: string,
  provider: Provider,
  patterns: DetectionPatterns,
): string[] {
  const types = patterns.entityTypes[provider] ?? [];
  const found = new Set<string>();
  for (const et of types) {
    const upper = et.toUpperCase();
    if (new RegExp(`type\\(${upper}\\)`, "i").test(text)) {
      found.add(upper);
    }
  }
  return [...found].sort();
}

// ── Deep text extraction ─────────────────────────────────────────────────────

export function deepTextExtract(obj: JsonValue): string {
  if (typeof obj === "string") return obj + "\n";
  if (Array.isArray(obj)) return obj.map(deepTextExtract).join("");
  if (obj !== null && typeof obj === "object") {
    return Object.values(obj).map((v) => deepTextExtract(v as JsonValue)).join("");
  }
  return "";
}

// ── Asset scanning ───────────────────────────────────────────────────────────

export function scanAsset(
  assetId: string,
  assetName: string,
  assetType: string,
  text: string,
  providers: Provider[],
  patterns: DetectionPatterns,
  options: { location?: string } = {},
): DetectionFinding[] {
  const findings: DetectionFinding[] = [];

  for (const provider of providers) {
    const metricPrefixes = detectClassicMetrics(text, provider, patterns);
    const metricKeys = extractClassicMetricKeys(text, provider, patterns);
    const entityTypes = detectClassicEntities(text, provider, patterns);
    const entitySelectors = detectClassicEntitySelectors(text, provider, patterns);

    if (!metricPrefixes.length && !metricKeys.length && !entityTypes.length && !entitySelectors.length) {
      continue;
    }

    const details: Record<string, unknown> = {};
    const blockers: string[] = [];

    if (provider === "aws" && metricKeys.length) {
      const re = patterns.streamsRe["aws"];
      if (re) {
        const streams = metricKeys.filter((k) => re.test(k));
        if (streams.length) {
          details["metric_streams_keys"] = streams;
          blockers.push("metric_streams");
        }
      }
    }

    findings.push({
      asset_id: assetId,
      asset_name: assetName,
      asset_type: assetType,
      provider,
      metric_prefixes: metricPrefixes,
      metric_keys: metricKeys,
      entity_types: entityTypes,
      entity_selectors: entitySelectors,
      confidence: metricKeys.length > 0 ? "high" : "low",
      blockers,
      location: options.location ?? "",
      details,
    });
  }
  return findings;
}

// ── Tile / cell query extraction ─────────────────────────────────────────────

function extractTileQueriesWithLocation(dash: JsonObject): Array<[string, string]> {
  const content = (dash["content"] ?? {}) as JsonObject;
  const rawTiles =
    content["tiles"] ??
    dash["tiles"] ??
    ((dash["layoutV2"] as JsonObject | undefined)?.["tiles"]) ??
    [];
  const tilesArr: unknown[] = typeof rawTiles === "object" && !Array.isArray(rawTiles)
    ? Object.values(rawTiles as Record<string, unknown>)
    : (rawTiles as unknown[]);

  const results: Array<[string, string]> = [];
  tilesArr.forEach((tile, tileIndex) => {
    if (typeof tile !== "object" || tile === null) return;
    const t = tile as JsonObject;
    if (typeof t["query"] === "string" && t["query"]) {
      results.push([t["query"] as string, `tile:${tileIndex}`]);
    }
    const queries = (t["queries"] ?? []) as unknown[];
    queries.forEach((q, qIndex) => {
      if (typeof q === "object" && q !== null) {
        const qo = q as JsonObject;
        if (typeof qo["query"] === "string" && qo["query"]) {
          results.push([qo["query"] as string, `tile:${tileIndex}/queries:${qIndex}`]);
        }
      }
    });
  });
  return results;
}

function extractNotebookQueriesWithLocation(nb: JsonObject): Array<[string, string]> {
  const content = (nb["content"] ?? {}) as JsonObject;
  const sections = (content["sections"] ?? []) as unknown[];
  const results: Array<[string, string]> = [];

  sections.forEach((section, si) => {
    if (typeof section !== "object" || section === null) return;
    const sec = section as JsonObject;
    const rawCells = sec["cells"] ?? sec["items"] ?? [];
    const cells = Array.isArray(rawCells) ? rawCells : [];
    cells.forEach((cell, ci) => {
      if (typeof cell !== "object" || cell === null) return;
      const c = cell as JsonObject;
      const cellType = ((c["type"] as string) ?? "").toLowerCase();
      if (["code", "dql", "query"].includes(cellType)) {
        const q = (c["content"] ?? c["code"] ?? c["query"] ?? "") as string;
        if (q) results.push([q, `section:${si}/cell:${ci}`]);
      }
    });
  });
  return results;
}

function extractClassicTileText(dash: JsonObject): string {
  const tiles = (dash["tiles"] ?? []) as unknown[];
  if (!Array.isArray(tiles)) return deepTextExtract(dash as JsonValue);

  const parts: string[] = [];
  for (const tile of tiles) {
    if (typeof tile !== "object" || tile === null) continue;
    const t = tile as JsonObject;
    const tt = (t["tileType"] as string) ?? "";
    if (tt === "DATA_EXPLORER") {
      const queries = (t["queries"] ?? []) as unknown[];
      for (const q of queries) {
        if (typeof q === "object" && q !== null) {
          const qo = q as JsonObject;
          const text = ((qo["query"] ?? qo["metricSelector"] ?? "") as string);
          if (text) parts.push(text);
        }
      }
    } else if (tt === "CUSTOM_CHARTING") {
      const metrics = (t["assignedMetrics"] ?? []) as unknown[];
      for (const m of metrics) {
        if (typeof m === "object" && m !== null) {
          const selectors = ((m as JsonObject)["metricSelectors"] ?? []) as unknown[];
          for (const sel of selectors) {
            if (typeof sel === "string" && sel) parts.push(sel);
          }
        }
      }
    } else if (tt === "DTAQL") {
      const q = (t["query"] as string) ?? "";
      if (q) parts.push(q);
    } else {
      parts.push(deepTextExtract(t as JsonValue));
    }
  }
  return parts.join("\n");
}

// ── Asset-type scanners ──────────────────────────────────────────────────────

export function scanDashboards(
  data: unknown,
  providers: Provider[],
  patterns: DetectionPatterns,
): DetectionFinding[] {
  const items = Array.isArray(data) ? data : [];
  const findings: DetectionFinding[] = [];

  for (const dash of items) {
    if (typeof dash !== "object" || dash === null) continue;
    const d = dash as JsonObject;
    const did = (d["id"] as string) ?? "unknown";
    if ("error" in d && Object.keys(d).length <= 2) continue;
    const meta = (d["dashboardMetadata"] as JsonObject | undefined) ?? {};
    const name = (d["name"] ?? meta["name"] ?? did) as string;

    const tileQueries = extractTileQueriesWithLocation(d);
    if (tileQueries.length) {
      for (const [text, loc] of tileQueries) {
        findings.push(...scanAsset(did, name, "dashboard", text, providers, patterns, { location: loc }));
      }
    } else {
      findings.push(...scanAsset(did, name, "dashboard", deepTextExtract(d as JsonValue), providers, patterns));
    }
  }
  return findings;
}

export function scanNotebooks(
  data: unknown,
  providers: Provider[],
  patterns: DetectionPatterns,
): DetectionFinding[] {
  const items = Array.isArray(data) ? data : [];
  const findings: DetectionFinding[] = [];

  for (const nb of items) {
    if (typeof nb !== "object" || nb === null) continue;
    const n = nb as JsonObject;
    const nid = (n["id"] as string) ?? "unknown";
    if ("error" in n && Object.keys(n).length <= 2) continue;
    const name = (n["name"] ?? nid) as string;

    const cellQueries = extractNotebookQueriesWithLocation(n);
    if (cellQueries.length) {
      for (const [text, loc] of cellQueries) {
        findings.push(...scanAsset(nid, name, "notebook", text, providers, patterns, { location: loc }));
      }
    } else {
      findings.push(...scanAsset(nid, name, "notebook", deepTextExtract(n as JsonValue), providers, patterns));
    }
  }
  return findings;
}

export function scanClassicDashboards(
  data: unknown,
  providers: Provider[],
  patterns: DetectionPatterns,
): DetectionFinding[] {
  const items = Array.isArray(data) ? data : [];
  const findings: DetectionFinding[] = [];

  for (const dash of items) {
    if (typeof dash !== "object" || dash === null) continue;
    const d = dash as JsonObject;
    const did = (d["id"] as string) ?? "unknown";
    if ("error" in d && Object.keys(d).length <= 2) continue;
    const meta = (d["dashboardMetadata"] as JsonObject | undefined) ?? {};
    const name = ((meta["name"] ?? d["name"] ?? did) as string);
    const rawTiles = (d["tiles"] ?? []) as unknown[];

    if (Array.isArray(rawTiles) && rawTiles.length) {
      rawTiles.forEach((tile, ti) => {
        if (typeof tile !== "object" || tile === null) return;
        const t = tile as JsonObject;
        const tileType = (t["tileType"] as string) ?? "UNKNOWN";
        const loc = `tile:${ti}/${tileType}`;
        const parts: string[] = [];

        if (tileType === "DATA_EXPLORER") {
          const queries = (t["queries"] ?? []) as unknown[];
          for (const q of queries) {
            if (typeof q === "object" && q !== null) {
              const qo = q as JsonObject;
              const text = ((qo["query"] ?? qo["metricSelector"] ?? "") as string);
              if (text) parts.push(text);
            }
          }
        } else if (tileType === "CUSTOM_CHARTING") {
          const metrics = (t["assignedMetrics"] ?? []) as unknown[];
          for (const m of metrics) {
            if (typeof m === "object" && m !== null) {
              const sels = ((m as JsonObject)["metricSelectors"] ?? []) as unknown[];
              for (const sel of sels) {
                if (typeof sel === "string" && sel) parts.push(sel);
              }
            }
          }
        } else if (tileType === "DTAQL") {
          const q = (t["query"] as string) ?? "";
          if (q) parts.push(q);
        } else {
          parts.push(deepTextExtract(t as JsonValue));
        }

        const tileText = parts.join("\n");
        if (tileText.trim()) {
          findings.push(...scanAsset(did, name, "classic_dashboard", tileText, providers, patterns, { location: loc }));
        }
      });
    } else {
      const tileText = extractClassicTileText(d);
      const text = tileText.trim() ? tileText : deepTextExtract(d as JsonValue);
      findings.push(...scanAsset(did, name, "classic_dashboard", text, providers, patterns));
    }
  }
  return findings;
}

export function scanMetricEvents(
  data: unknown,
  providers: Provider[],
  patterns: DetectionPatterns,
): DetectionFinding[] {
  const raw = data as JsonObject | null;
  const items = Array.isArray(data)
    ? (data as unknown[])
    : ((raw?.["items"] as unknown[]) ?? []);
  const findings: DetectionFinding[] = [];

  for (const evt of items) {
    if (typeof evt !== "object" || evt === null) continue;
    const e = evt as JsonObject;
    const eid = ((e["objectId"] ?? e["id"] ?? "unknown") as string);
    const val = (e["value"] ?? e) as JsonObject;
    const qd = (val["queryDefinition"] ?? {}) as JsonObject;
    const name = ((val["summary"] ?? (qd["metricKey"] as string | undefined) ?? eid) as string);
    const targeted = [qd["metricKey"], qd["metricSelector"]].filter(Boolean).join("\n");
    const text = targeted.trim() ? targeted : deepTextExtract(e as JsonValue);
    findings.push(...scanAsset(eid, name, "metric_event", text, providers, patterns, { location: `objectId:${eid}` }));
  }
  return findings;
}

export function scanSlos(
  data: unknown,
  providers: Provider[],
  patterns: DetectionPatterns,
): DetectionFinding[] {
  if (data === null || data === undefined) return [];
  const raw = data as JsonObject;
  const items = Array.isArray(data)
    ? (data as unknown[])
    : ((raw["slo"] ?? raw["items"] ?? []) as unknown[]);
  const findings: DetectionFinding[] = [];

  for (const slo of items) {
    if (typeof slo !== "object" || slo === null) continue;
    const s = slo as JsonObject;
    const sid = (s["id"] as string) ?? "unknown";
    const name = (s["name"] as string) ?? sid;
    const customSli = (s["customSli"] as JsonObject | undefined) ?? {};
    const targeted = (customSli["indicator"] as string) ?? "";
    const text = targeted.trim() ? targeted : deepTextExtract(s as JsonValue);
    findings.push(...scanAsset(sid, name, "slo", text, providers, patterns, { location: `slo:${sid}` }));
  }
  return findings;
}

export function scanInfrastructureDetection(
  data: unknown,
  providers: Provider[],
  patterns: DetectionPatterns,
): DetectionFinding[] {
  // Any object in this schema signals classic AWS entity type monitoring.
  if (!providers.includes("aws")) return [];

  const raw = data as JsonObject | null;
  const items = Array.isArray(data)
    ? (data as unknown[])
    : ((raw?.["items"] as unknown[]) ?? []);
  const findings: DetectionFinding[] = [];

  for (const obj of items) {
    if (typeof obj !== "object" || obj === null) continue;
    const o = obj as JsonObject;
    const oid = ((o["objectId"] ?? o["id"] ?? "unknown") as string);
    const val = (o["value"] ?? o) as JsonObject;
    const scope = (o["scope"] as string) ?? "environment";
    const customisedServices = detectCustomisedInfraServices(val);

    findings.push({
      asset_id: oid,
      asset_name: "AWS Infrastructure Anomaly Detection",
      asset_type: "infra_detection",
      provider: "aws",
      metric_prefixes: [],
      metric_keys: [],
      entity_types: patterns.entityTypes["aws"] ?? [],
      entity_selectors: [],
      confidence: customisedServices.length > 0 ? "high" : "low",
      blockers: [],
      location: `scope:${scope}`,
      details: {
        settings_scope: scope,
        has_custom_settings: customisedServices.length > 0,
        customised_services: customisedServices,
      },
    });
  }
  return findings;
}

function detectCustomisedInfraServices(val: unknown): string[] {
  if (typeof val !== "object" || val === null) return [];
  const customised: string[] = [];
  for (const [key, serviceObj] of Object.entries(val as Record<string, unknown>)) {
    if (typeof serviceObj !== "object" || serviceObj === null) continue;
    const so = serviceObj as JsonObject;
    const thresholds = so["customThresholds"];
    if (typeof thresholds === "object" && thresholds !== null && Object.keys(thresholds).length) {
      customised.push(key);
    } else if (
      ["threshold", "sensitivity", "alertingEnabled"].some(
        (k) => k in so && so[k] !== null && so[k] !== true && so[k] !== false && so[k] !== "DEFAULT" && so[k] !== "",
      )
    ) {
      customised.push(key);
    }
  }
  return customised;
}

export function scanDavisDetectors(
  data: unknown,
  providers: Provider[],
  patterns: DetectionPatterns,
): DetectionFinding[] {
  const raw = data as JsonObject | null;
  const items = Array.isArray(data)
    ? (data as unknown[])
    : ((raw?.["items"] as unknown[]) ?? []);
  const findings: DetectionFinding[] = [];

  for (const obj of items) {
    if (typeof obj !== "object" || obj === null) continue;
    const o = obj as JsonObject;
    const oid = ((o["objectId"] ?? o["id"] ?? "unknown") as string);
    const val = (o["value"] ?? o) as JsonObject;

    const analyzer = (val["analyzer"] ?? {}) as JsonObject;
    const inputFields = Array.isArray(analyzer["input"]) ? (analyzer["input"] as unknown[]) : [];
    const textsToScan: Array<[number, string]> = [];
    inputFields.forEach((field, i) => {
      if (typeof field === "object" && field !== null) {
        const f = field as JsonObject;
        if (typeof f["value"] === "string" && f["value"]) {
          textsToScan.push([i, f["value"] as string]);
        }
      }
    });

    if (!textsToScan.length) continue;

    const name = ((val["title"] ?? val["name"] ?? oid) as string);

    for (const provider of providers) {
      const allKeys = new Set<string>();
      const matchingInputs: string[] = [];
      const matchingIndices: number[] = [];

      for (const [i, text] of textsToScan) {
        if (detectClassicMetrics(text, provider, patterns).length) {
          extractClassicMetricKeys(text, provider, patterns).forEach((k) => allKeys.add(k));
          matchingInputs.push(text);
          matchingIndices.push(i);
        }
      }

      if (!allKeys.size) continue;

      const loc = matchingIndices.length >= 1 ? `analyzer_input:${matchingIndices[0]}` : "";

      findings.push({
        asset_id: oid,
        asset_name: name,
        asset_type: "davis_detector",
        provider,
        metric_prefixes: [],
        metric_keys: [...allKeys].sort(),
        entity_types: [],
        entity_selectors: [],
        confidence: "high",
        blockers: [],
        location: loc,
        details: {
          matching_inputs: matchingInputs,
          analyzer_type: (analyzer["type"] as string) ?? "",
          full_config: analyzer,
        },
      });
    }
  }
  return findings;
}

// ── Top-level aggregator ─────────────────────────────────────────────────────

export interface AssessmentData {
  dashboards?: unknown;
  metric_events?: unknown;
  slos?: unknown;
  infrastructure_detection?: unknown;
  davis_detectors?: unknown;
  notebooks?: unknown;
  classic_dashboards?: unknown;
}

/**
 * Run all scanners over the assessment data and return the combined findings.
 * Equivalent to the main() aggregation in detect-classic-patterns.py.
 */
export function detectAll(
  data: AssessmentData,
  providers: Provider[],
  patterns: DetectionPatterns,
): AllFindings {
  return {
    schema_version: "1.0",
    dashboards: scanDashboards(data.dashboards, providers, patterns),
    metric_events: scanMetricEvents(data.metric_events, providers, patterns),
    slos: scanSlos(data.slos, providers, patterns),
    infrastructure_detection: scanInfrastructureDetection(data.infrastructure_detection, providers, patterns),
    davis_detectors: scanDavisDetectors(data.davis_detectors, providers, patterns),
    notebooks: scanNotebooks(data.notebooks, providers, patterns),
    classic_dashboards: scanClassicDashboards(data.classic_dashboards, providers, patterns),
  };
}
