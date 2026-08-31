#!/usr/bin/env node
// Verifies that all version fields are consistent with .claude-plugin/plugin.json (canonical source).
// Run on CI and locally before releasing.
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");

function read(file) {
  return JSON.parse(fs.readFileSync(path.join(root, file), "utf8"));
}

const { version } = read(".claude-plugin/plugin.json");
const expectedHeader = `dynatrace-for-ai/${version}`;

const serverJson = read("server.json");
const serverJsonXHttpSource = serverJson.remotes?.[0]?.headers?.find(
  (h) => h.name === "X-Http-Source"
)?.value;

const checks = [
  {
    file: ".cursor-plugin/plugin.json",
    actual: read(".cursor-plugin/plugin.json").version,
    expected: version,
  },
  {
    file: "mcp.json",
    actual: read("mcp.json").mcpServers?.dynatrace?.headers?.["X-Http-Source"],
    expected: expectedHeader,
  },
  {
    file: ".mcp.json",
    actual: read(".mcp.json").mcpServers?.dynatrace?.headers?.["X-Http-Source"],
    expected: expectedHeader,
  },
  {
    file: "server.json (version)",
    actual: serverJson.version,
    expected: version,
  },
  {
    file: "server.json (X-Http-Source)",
    actual: serverJsonXHttpSource,
    expected: expectedHeader,
  },
];

let failed = false;
for (const { file, actual, expected } of checks) {
  if (actual !== expected) {
    console.error(`FAIL ${file}: got "${actual}", expected "${expected}"`);
    failed = true;
  } else {
    console.log(`OK   ${file}: "${actual}"`);
  }
}

if (failed) {
  console.error(`\nCanonical version is "${version}" from .claude-plugin/plugin.json`);
  process.exit(1);
}
