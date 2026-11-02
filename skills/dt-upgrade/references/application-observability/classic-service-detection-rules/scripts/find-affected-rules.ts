// find-affected-rules.ts — tracking query for the classic service detection
// rule (SDv1) migration.
//
// Lists the enabled FULL_WEB_REQUEST / FULL_WEB_SERVICE detection rules that use
// a condition Phase 3 removes: a management zone scope, or a `PG_Tag` whose key
// does not start with `primary_tags.`. Reads Settings 2.0 via dtctl. Read-only.
//
// Run:  node --experimental-strip-types find-affected-rules.ts
// See:  ../classic-service-detection-rules.md (#tracking-query).
//
// Verified against a live tenant 2026-08-10: of 52 rules it flagged the 48 enabled
// ones using a non-primary tag or a management zone, and cleared the rest —
// including one whose PG_Tag conditions were all under `primary_tags.`. Both
// TagEquals and TagKeyEquals forms occur in real data; both are handled.

import { execSync } from "node:child_process";

const SCHEMAS = [
  "builtin:service-detection.full-web-request",
  "builtin:service-detection.full-web-service",
];

const PRIMARY_TAG_PREFIX = "primary_tags.";

interface Condition {
  attribute: string;
  compareOperationType: string;
  // TagEquals carries tag values here, TagKeyEquals carries bare keys in textValues.
  tagValues?: string[];
  textValues?: string[];
}

interface SettingsObject {
  schemaId: string;
  value: {
    name: string;
    enabled: boolean;
    managementZones: string[];
    conditions?: Condition[];
  };
}

function fetchRules(schema: string): SettingsObject[] {
  const output = execSync(`dtctl get settings --schema ${schema} -o json`, {
    encoding: "utf-8",
    maxBuffer: 64 * 1024 * 1024,
  });
  return JSON.parse(output) as SettingsObject[];
}

// A PG_Tag condition is deprecated unless every value it references sits under
// `primary_tags.`. Returns the offending values so the customer knows which tags
// to convert.
function deprecatedTags(conditions: Condition[]): string[] {
  return conditions
    .filter((c) => c.attribute === "PG_Tag")
    .flatMap((c) =>
      c.compareOperationType === "TagEquals" ? (c.tagValues ?? []) : (c.textValues ?? []),
    )
    .filter((value) => !value.startsWith(PRIMARY_TAG_PREFIX));
}

function main(): void {
  const affected = SCHEMAS.flatMap(fetchRules)
    // Disabled rules never match traffic, so Phase 3 cannot break them.
    .filter((o) => o.value.enabled)
    .map((o) => ({
      name: o.value.name,
      type: o.schemaId.endsWith("full-web-request") ? "FULL_WEB_REQUEST" : "FULL_WEB_SERVICE",
      managementZones: (o.value.managementZones ?? []).length,
      tags: deprecatedTags(o.value.conditions ?? []),
    }))
    .filter((r) => r.managementZones > 0 || r.tags.length > 0);

  if (affected.length === 0) {
    console.log("No rules use deprecated conditions. No action needed for Phase 3.");
    return;
  }

  console.log(`${affected.length} rule(s) use deprecated conditions:\n`);
  for (const r of affected) {
    const reasons = [
      r.managementZones > 0 ? "management zone scope" : "",
      r.tags.length > 0 ? `non-primary PG_Tag: ${r.tags.join(", ")}` : "",
    ].filter(Boolean);
    console.log(`  [${r.type}] ${r.name}\n      ${reasons.join("; ")}`);
  }
}

main();
