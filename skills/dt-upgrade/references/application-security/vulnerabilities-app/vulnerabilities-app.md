# Vulnerabilities App

<!-- Jira: none -->

**Gen3 replacement**: Updated vulnerability monitoring with new monitoring rules

**Phase 2 required**: no (needed for Phase 3)

## What changes

The Vulnerabilities App requires enabling new monitoring rules and technology toggles for Phase 3 compatibility.

## Customer actions

- Go to Settings > Analyze and Alert > Application Security > General Settings and select "Third-Party Vulnerability Analytics" tab
- Enable the "Enable new monitoring rules" toggle
- Enable all technology toggles

## Tracking queries

Query the toggles in the `builtin:appsec.runtime-vulnerability-detection` schema.
