# External Services

**Gen3 replacement**: Service App

**Phase 2 required**: yes

## What changes

External services, including database, opaque, and third-party services, are handled in the Service App. The classic database services
screen will be removed in Phase 3. Configurations that refer to classic external service entity IDs must be reviewed before the classic
service entities are removed.

## Instructions

Run these steps in order. The agent never writes to the tenant.

### Prerequisites

- **Python 3.7+**.
- The bundled scripts live in the `src/` subdirectory next to this file (`src/scan_external_services.py`, `src/external_services_report.py`).
- A Dynatrace **platform token** (`dt0s16.*`) with these scopes:
  - `Storage read` (built into platform tokens — needed for DQL entity query)
  - `settings.read` (classic Settings API)
  - `document:read` (dashboards and notebooks)
- If `DT_PLATFORM_TOKEN` is not already set in the environment, ask the customer for a token before proceeding. Prefer setting `DT_PLATFORM_TOKEN` over passing `--token` on the command line — a token given as a CLI argument is visible to other users via `ps` and is written to shell history.

### Step 1 — Scan configs for external service references

Run `scan_external_services.py` from the `src/` directory:

```bash
python src/scan_external_services.py --tenant https://<env>.apps.dynatrace.com --token <token>
```

The token can also come from the environment variable instead of `--token`:

```bash
export DT_PLATFORM_TOKEN=dt0s16.XXX
python src/scan_external_services.py --tenant https://<env>.apps.dynatrace.com
```

The script:
- Discovers all classic external service entities via DQL (database, opaque, and third-party).
- Scans SLOs, SRGs, Davis alerts, custom metric events, dashboards, and notebooks for references to those `SERVICE-*` IDs.
- Writes `report_<tenant>.json` and a `report_<tenant>_details/` directory in its own directory.

Wait for the script to finish. Note the output path printed at the end (`Report written to`).

### Step 2 — Generate the consolidated report

Run `external_services_report.py` from the `src/` directory, passing the same `--tenant`:

```bash
python src/external_services_report.py --tenant https://<env>.apps.dynatrace.com
```

The script reads `report_<tenant>.json` and the `report_<tenant>_details/` files written in Step 1,
and produces two output files in the same directory:
- `external_services_report_<tenant>.json` — machine-readable consolidated report
- `external_services_report_<tenant>.html` — human-readable report grouped by config type

If the scan in Step 1 was only partially complete (token lacked a scope, or some docs failed),
the report script will refuse to run unless `--allow-incomplete` is passed.

### Step 3 — Report findings

After both scripts succeed, summarise findings for the customer:

- **External services found**: total count on the tenant, broken down as:
  - Database (`serviceType == "DATABASE_SERVICE"`)
  - Third-party (`serviceSubType == "WEB_REQUEST_WATCHED"`)
  - Opaque (all remaining)
- **Configs scanned**: total number of SLOs, SRGs, alerts, dashboards, and notebooks checked.
- **Affected configs**: list each affected config by type and name, with the referenced service(s).
- **Scan completeness**: report the `scan_completeness.status` field from the JSON report (`complete`, `truncated`, or `partial`). If not `complete`, list the warnings.
- Tell the customer that the HTML report at `external_services_report_<tenant>.html` contains links directly to affected settings, dashboards, and notebooks on their tenant.
