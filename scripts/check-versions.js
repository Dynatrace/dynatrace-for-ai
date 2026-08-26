#!/usr/bin/env node
// Verifies that X-Http-Source in mcp.json and .mcp.json matches the version in .cursor-plugin/plugin.json
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");

function read(file) {
  return JSON.parse(fs.readFileSync(path.join(root, file), "utf8"));
}

const { version } = read(".cursor-plugin/plugin.json");
const expected = `dynatrace-for-ai/${version}`;

const checks = [
  { file: "mcp.json", actual: read("mcp.json").mcpServers?.dynatrace?.headers?.["X-Http-Source"] },
  { file: ".mcp.json", actual: read(".mcp.json").mcpServers?.dynatrace?.headers?.["X-Http-Source"] },
];

let failed = false;
for (const { file, actual } of checks) {
  if (actual !== expected) {
    console.error(`FAIL ${file}: X-Http-Source is "${actual}", expected "${expected}"`);
    failed = true;
  } else {
    console.log(`OK   ${file}: X-Http-Source = "${actual}"`);
  }
}

if (failed) process.exit(1);
