# Contributing

## Skill Content Is Read-Only

Skill content under `skills/` is **maintained internally at Dynatrace** and
published to this repository periodically. Every publish cycle overwrites the
`skills/` directory entirely, so **pull requests that modify files under
`skills/` will not be accepted** — the changes would be lost on the next
publish.

If you want to suggest improvements to a skill, please **open an issue**
instead. The Dynatrace team will pick it up and apply the change at the source.

## What You Can Contribute

The following files live exclusively in this repository and welcome PRs:

- `README.md`, `CONTRIBUTING.md`, `llms.txt`
- `prompts/**` — reusable prompt templates
- `plugins/**` — plugin manifests and agent configurations
- `tests/**` — CI test scripts
- `.github/**` — GitHub Actions workflows

## Reporting Issues

To report bugs, suggest new skills, or request improvements to existing skill
content, please [open a GitHub issue](../../issues/new).

## Releasing a New Version

The canonical version is the `version` field in `.claude-plugin/plugin.json`. It must match the GitHub release tag (e.g., release `v7.0.0` → `"version": "7.0.0"`).

When bumping the version, update all of the following to match:

- `.claude-plugin/plugin.json` → `"version"` (canonical)
- `.cursor-plugin/plugin.json` → `"version"`
- `mcp.json` → `"X-Http-Source": "dynatrace-for-ai/<version>"`
- `.mcp.json` → `"X-Http-Source": "dynatrace-for-ai/<version>"`

Run `node scripts/check-versions.js` to verify — CI also enforces this on every PR.

## License

All contributions are licensed under Apache-2.0.
