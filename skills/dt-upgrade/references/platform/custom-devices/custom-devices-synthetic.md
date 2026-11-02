# Synthetic Migration Guide - Network Devices and Connectivity Monitoring

**Gen3 replacement**: SNMP extension (`com.dynatrace.extension.snmp`) for custom device monitoring; ICMP/TCP connectivity checks via `NETWORK_AVAILABILITY` monitors (dtctl YAML or Settings API) or via `MULTI_PROTOCOL` monitors with explicit `targetList` (Environment API v2)

**Phase 2 required**: no

Monitor network infrastructure via SNMP and validate connectivity using ICMP ping and TCP port checks.

## Overview

Three complementary approaches — use them together for full network observability:

| Approach | What it monitors | Entity ID prefix |
|----------|-----------------|------------------|
| SNMP Autodiscovery | Routers, switches, firewalls — SNMP OID metrics | `CUSTOM_DEVICE-` |
| ICMP Monitor | Host/IP reachability via ping | `MULTIPROTOCOL_MONITOR-` (current); `NETWORK_AVAILABILITY_MONITOR-` when using dtctl/Settings API |
| TCP Monitor | Port availability via TCP connection attempt | `MULTIPROTOCOL_MONITOR-` (current); `NETWORK_AVAILABILITY_MONITOR-` when using dtctl/Settings API |

> **Smartscape status:** The `NETWORK_AVAILABILITY_MONITOR` Smartscape node type and the `dt.smartscape.network_availability_monitor` signal dimension may not be available on all tenants yet. Classic entity queries use `dt.entity.multiprotocol_monitor` and the `MULTIPROTOCOL_MONITOR-` entity ID prefix; use the Smartscape dimension only when confirmed available on the target tenant. See [`entity-synthetic`](../entity-queries/entity-synthetic.md) for the classic → Smartscape mapping table and dual-mode query patterns.


## Extension Architecture

```
ActiveGate (EEC) ──SNMP UDP 161──► Network Devices
     │                                    │
     │ discovers via SNMP GET             │ returns OID values
     │                                    │
     ▼                                    ▼
Custom Device entities          Metrics ingested to Grail
(CUSTOM_DEVICE in Smartscape)   (ext:snmp.* metric keys)
```

The SNMP extension runs on an **ActiveGate with EEC** (Extension Execution Controller).
EEC must be enabled on the ActiveGate group handling this monitoring configuration.

## Prerequisites

- **ActiveGate with EEC** (Extension Execution Controller) enabled — required for the SNMP extension to run
- Network access from the ActiveGate host to target IP ranges: UDP 161 (SNMP), ICMP echo, and relevant TCP ports for connectivity monitors
- Load `dt-obs-extensions` before troubleshooting extension errors or DEC status codes
- A **private synthetic location** configured (ActiveGate acting as synthetic location) for ICMP/TCP monitors
- Token scopes: API token with permissions to read and write synthetic monitors for classic `MULTI_PROTOCOL` management (Environment API v2); `settings.read` / `settings.write` for `NETWORK_AVAILABILITY` monitors and extension configurations (Settings API)

---

## Step 1: Configure SNMP Autodiscovery

SNMP autodiscovery uses the Dynatrace SNMP extension to scan IP ranges, identify devices,
and create Custom Device entities that feed metrics into Grail.

### 1a. Install the SNMP Extension

Install `com.dynatrace.extension.snmp` from the Dynatrace Hub:

```bash
# List available SNMP extensions from Hub (note the version numbers)
dtctl get hub-extensions --jq '.[] | select(.name | contains("snmp"))'

# Install the extension with a pinned version
dtctl apply -f snmp-extension-install.yaml
```

`snmp-extension-install.yaml`:
```yaml
apiVersion: v1alpha1
kind: ExtensionInstallation
metadata:
  name: com.dynatrace.extension.snmp
spec:
  version: "2.1.4"   # pin to the version returned by hub-extensions above
```

Verify installation:
```bash
dtctl get extensions | grep snmp
```

---

## Step 2: Configuration for SNMP

### 2a. Configure SNMP Autodiscovery

The monitoring configuration defines which IP ranges to scan and SNMP credentials to use.

`snmp-monitoring-config.yaml`:
```yaml
apiVersion: v1alpha1
kind: MonitoringConfiguration
metadata:
  name: network-devices-snmp
spec:
  extensionName: com.dynatrace.extension.snmp
  description: "SNMP autodiscovery for core network devices"
  activeGate:
    useActiveGateGroup: "default"   # or a specific AG group name
  version: "2.1.4"   # pin to the installed extension version
  value:
    enabled: true
    description: "Core network device autodiscovery"
    # Autodiscovery target ranges — scan these subnets for SNMP-responsive devices
    autodiscovery:
      - targetType: "network"
        targetAddress: "192.168.1.0/24"
      - targetType: "network"
        targetAddress: "10.0.0.0/16"
    # SNMP credentials (define one per community string / v3 auth profile)
    snmpCredentials:
      - name: "subnet-a-v2c"
        version: "V2"
        communityString: "<your-community-string>"
      - name: "subnet-b-v2c"
        version: "V2"
        communityString: "<your-community-string>"
    # Optional: SNMPv3 credentials
    # snmpV3Credentials:
    #   - name: "v3-auth"
    #     username: "<snmp-username>"
    #     authProtocol: "SHA"
    #     authPassword: "<auth-password>"
    #     privProtocol: "AES"
    #     privPassword: "<priv-password>"
    #     securityLevel: "authPriv"
```

Apply:
```bash
dtctl apply -f snmp-monitoring-config.yaml
```

### 2b. Verify Autodiscovery

After ~5 minutes, discovered devices appear as CUSTOM_DEVICE entities.

### 2c. SNMP Autodiscovery Troubleshooting

| Symptom | Cause | Remedy |
|---------|-------|--------|
| No devices discovered | SNMP blocked by firewall | Allow UDP 161 from ActiveGate IPs to target range |
| Extension shows `GENERIC_ERROR` | Wrong community string | Update credential in monitoring config |
| Partial discovery (some devices missing) | Mixed SNMP versions in subnet | Add both V2 and V3 credential entries |
| Extension `HIGH_MEMORY_RESTART` | Too large an IP range scanned | Split into smaller subnet ranges across multiple configs |
| Devices discovered but no metrics | OID not responding | Verify target device exposes standard MIB OIDs |

→ For extension status codes and DEC error codes, load the `dt-obs-extensions` skill.

---

## Step 3: Configure ICMP and TCP monitors with new approach

### Step 3a: ICMP Monitor

ICMP monitors send periodic ping (ICMP echo) requests to test whether a host is reachable.

`icmp-monitor.yaml`:
```yaml
schemaId: builtin:synthetic.monitors.network-availability
scope: environment
value:
  name: "ICMP Monitor — Core Router"
  enabled: true
  type: NETWORK_AVAILABILITY
  frequencyMin: 1        # polling interval in minutes (1, 2, 5, 10, 15, 30, 60)
  locations:
    - SYNTHETIC_LOCATION-<your-private-activegate-location-id>
  steps:
    - name: "Ping 192.168.1.1"
      requestType: ICMP
      host: "192.168.1.1"   # IP or hostname of target device
  tags:
    - key: network-monitoring
    - key: icmp
    - key: core-router
```

Apply:
```bash
dtctl apply -f icmp-monitor.yaml
```

For programmatic creation without YAML apply, use the Settings API directly.

### Create ICMP Monitor (Settings API v2)

```bash
# POST /api/v2/settings/objects with schemaId=builtin:synthetic.monitors.network-availability
curl -X POST "https://<env-id>.live.dynatrace.com/api/v2/settings/objects" \
  -H "Authorization: Api-Token <token>" \
  -H "Content-Type: application/json" \
  -d '[{
    "schemaId": "builtin:synthetic.monitors.network-availability",
    "scope": "environment",
    "value": {
      "name": "ICMP Monitor — Core Router",
      "enabled": true,
      "type": "NETWORK_AVAILABILITY",
      "frequencyMin": 1,
      "locations": ["SYNTHETIC_LOCATION-<id>"],
      "steps": [{
        "name": "Ping 192.168.1.1",
        "requestType": "ICMP",
        "host": "192.168.1.1"
      }],
      "tags": [{"key": "network-monitoring"}, {"key": "icmp"}]
    }
  }]'
```

Required token scope: `settings.write`.

### Step 3b: TCP Monitor

TCP monitors attempt a TCP handshake to a specific host:port to verify service port availability.

`tcp-monitor.yaml`:
```yaml
schemaId: builtin:synthetic.monitors.network-availability
scope: environment
value:
  name: "TCP Monitor — Switch Management"
  enabled: true
  type: NETWORK_AVAILABILITY
  frequencyMin: 5
  locations:
    - SYNTHETIC_LOCATION-<your-private-activegate-location-id>
  steps:
    - name: "TCP 192.168.1.10:443"
      requestType: TCP
      host: "192.168.1.10"   # target host
      port: 443              # TCP port to test
    # Optionally test multiple ports in sequence (all must pass for monitor to be UP)
    - name: "TCP 192.168.1.10:22"
      requestType: TCP
      host: "192.168.1.10"
      port: 22
  tags:
    - key: network-monitoring
    - key: tcp
    - key: switch-management
```

Apply:
```bash
dtctl apply -f tcp-monitor.yaml
```

For programmatic creation without YAML apply, use the Settings API directly.

### Create TCP Monitor (Settings API v2)

```bash
curl -X POST "https://<env-id>.live.dynatrace.com/api/v2/settings/objects" \
  -H "Authorization: Api-Token <token>" \
  -H "Content-Type: application/json" \
  -d '[{
    "schemaId": "builtin:synthetic.monitors.network-availability",
    "scope": "environment",
    "value": {
      "name": "TCP Monitor — Switch HTTPS",
      "enabled": true,
      "type": "NETWORK_AVAILABILITY",
      "frequencyMin": 5,
      "locations": ["SYNTHETIC_LOCATION-<id>"],
      "steps": [{
        "name": "TCP connect 192.168.1.10:443",
        "requestType": "TCP",
        "host": "192.168.1.10",
        "port": 443
      }],
      "tags": [{"key": "network-monitoring"}, {"key": "tcp"}]
    }
  }]'
```

Required token scope: `settings.write`.

## Managing Monitors via the Environment API v2

Use the Environment API v2 (`/api/v2/synthetic/monitors`) to create, read, update, and delete
classic `MULTI_PROTOCOL` monitors programmatically. The `"type"` field in the request body is always
`"MULTI_PROTOCOL"` and the created entity carries the `MULTIPROTOCOL_MONITOR-` prefix.
(`NETWORK_AVAILABILITY_MONITOR-` is the Smartscape entity type, not what this endpoint creates.)

Required token scopes: API token with `Read synthetic monitors` permission (GET); `Create and update synthetic monitors` permission (POST, PUT, DELETE).

Base URL:
- SaaS: `https://<env-id>.live.dynatrace.com/api/v2/synthetic/monitors`

### GET — Retrieve a monitor definition

```bash
curl -X GET "https://<env-id>.live.dynatrace.com/api/v2/synthetic/monitors/<monitorId>" \
  -H "Authorization: Api-Token <token>"
```

Returns the full monitor definition including `steps`, `locations`, `tags`, and `syntheticMonitorOutageHandlingSettings`.

### POST — Create a monitor

**ICMP:**

```bash
curl -X POST "https://<env-id>.live.dynatrace.com/api/v2/synthetic/monitors" \
  -H "Authorization: Api-Token <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "ICMP Monitor — Core Router",
    "type": "MULTI_PROTOCOL",
    "enabled": true,
    "frequencyMin": 1,
    "locations": ["SYNTHETIC_LOCATION-<id>"],
    "steps": [
      {
        "name": "Ping 192.168.1.1",
        "requestType": "ICMP",
        "targetList": ["192.168.1.1"],
        "properties": {
          "ICMP_NUMBER_OF_PACKETS": "5"
        },
        "constraints": [
          {
            "type": "SUCCESS_RATE_PERCENT",
            "properties": { "value": "100", "operator": "=" }
          }
        ],
        "requestConfigurations": [
          {
            "constraints": [
              {
                "type": "ICMP_SUCCESS_RATE_PERCENT",
                "properties": { "value": "100", "operator": "=" }
              }
            ]
          }
        ]
      }
    ],
    "syntheticMonitorOutageHandlingSettings": {
      "globalOutages": true,
      "localOutages": false,
      "globalConsecutiveOutageCountThreshold": 1
    },
    "performanceThresholds": { "enabled": false },
    "tags": []
  }'
```

**TCP:**

```bash
curl -X POST "https://<env-id>.live.dynatrace.com/api/v2/synthetic/monitors" \
  -H "Authorization: Api-Token <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "TCP Monitor — Switch HTTPS",
    "type": "MULTI_PROTOCOL",
    "enabled": true,
    "frequencyMin": 5,
    "locations": ["SYNTHETIC_LOCATION-<id>"],
    "steps": [
      {
        "name": "TCP 192.168.1.10:443",
        "requestType": "TCP",
        "targetList": ["192.168.1.10"],
        "properties": {
          "TCP_PORT_RANGES": "443"
        },
        "constraints": [
          {
            "type": "SUCCESS_RATE_PERCENT",
            "properties": { "value": "100", "operator": "=" }
          }
        ],
        "requestConfigurations": [{ "constraints": [] }]
      }
    ],
    "syntheticMonitorOutageHandlingSettings": {
      "globalOutages": true,
      "localOutages": false,
      "globalConsecutiveOutageCountThreshold": 1
    },
    "performanceThresholds": { "enabled": false },
    "tags": []
  }'
```

To monitor multiple hosts in a single step, list all IPs in `targetList` — all are checked; the step passes only if ALL succeed:

```json
{
  "steps": [{
    "requestType": "ICMP",
    "targetList": ["192.168.1.1", "192.168.1.2", "192.168.1.3"],
    "properties": { "ICMP_NUMBER_OF_PACKETS": "5" },
    "constraints": [{ "type": "SUCCESS_RATE_PERCENT", "properties": { "value": "100", "operator": "=" } }]
  }]
}
```

A successful POST for a `MULTI_PROTOCOL` monitor returns HTTP 200 with the new entity ID:

```json
{ "entityId": "MULTIPROTOCOL_MONITOR-<id>" }
```

**ICMP with explicit `targetList` (Environment API v2):**

```bash
curl -X POST "https://<env-id>.live.dynatrace.com/api/v2/synthetic/monitors" \
  -H "Authorization: Api-Token <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "ICMP Monitor — Custom device for E2E",
    "type": "MULTI_PROTOCOL",
    "enabled": true,
    "frequencyMin": 1,
    "locations": ["SYNTHETIC_LOCATION-<id>"],
    "steps": [
      { "name": "Ping 192.168.1.10", "requestType": "ICMP", "targetList": ["192.168.1.10"] },
      { "name": "Ping 192.168.1.11", "requestType": "ICMP", "targetList": ["192.168.1.11"] }
    ],
    "tags": []
  }'
```

**TCP with explicit `targetList` (Environment API v2):**

```bash
curl -X POST "https://<env-id>.live.dynatrace.com/api/v2/synthetic/monitors" \
  -H "Authorization: Api-Token <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "TCP Monitor — Custom device for E2E",
    "type": "MULTI_PROTOCOL",
    "enabled": true,
    "frequencyMin": 1,
    "locations": ["SYNTHETIC_LOCATION-<id>"],
    "steps": [
      { "name": "TCP 192.168.1.10:22", "requestType": "TCP", "targetList": ["192.168.1.10"], "properties": { "TCP_PORT_RANGES": "22" } },
      { "name": "TCP 192.168.1.11:22", "requestType": "TCP", "targetList": ["192.168.1.11"], "properties": { "TCP_PORT_RANGES": "22" } }
    ],
    "tags": []
  }'
```

### PUT — Update a monitor

Send the full monitor definition — the PUT replaces the entire monitor body:

```bash
curl -X PUT "https://<env-id>.live.dynatrace.com/api/v2/synthetic/monitors/<monitorId>" \
  -H "Authorization: Api-Token <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "ICMP Monitor — Core Router",
    "type": "MULTI_PROTOCOL",
    "enabled": true,
    "frequencyMin": 1,
    "locations": ["SYNTHETIC_LOCATION-<id>"],
    "steps": [ ... ],
    "syntheticMonitorOutageHandlingSettings": { ... },
    "performanceThresholds": { "enabled": false },
    "tags": []
  }'
```

A successful PUT returns HTTP 204 (no body).

> **Note:** Classic `MULTI_PROTOCOL` monitors use the `MULTIPROTOCOL_MONITOR-` entity ID prefix.
> Monitors created with the new `NETWORK_AVAILABILITY` approach use the `NETWORK_AVAILABILITY_MONITOR-`
> prefix instead. Use whichever approach matches how the monitor was originally created; mixing them
> creates separate entities.

---

## Migration

### ICMP - deprecated definition

Examples:
```json
{
  "name": "DEMO - ICMP custom device",
  "description": "Instead of explicit list of IPs we have a monitor defined using filtering. Monitor is based on the extensionName == Custom device for E2E. Success rate constraints are set to =100%.",
  "type": "MULTI_PROTOCOL",
  "frequencyMin": 1,
  "locations": [
    "SYNTHETIC_LOCATION-<your-private-activegate-location-id>"
  ],
  "enabled": true,
  "steps": [
    {
      "requestType": "ICMP",
      "targetFilter": "extensionName == \"Custom device for E2E\"",
      "targetList": [],
      "properties": {
        "ICMP_NUMBER_OF_PACKETS": "5"
      },
      "constraints": [
        {
          "type": "SUCCESS_RATE_PERCENT",
          "properties": {
            "value": "100",
            "operator": "="
          }
        }
      ],
      "requestConfigurations": [
        {
          "constraints": [
            {
              "type": "ICMP_SUCCESS_RATE_PERCENT",
              "properties": {
                "value": "100",
                "operator": "="
              }
            }
          ]
        }
      ],
      "name": "DEMO - ICMP custom device - step"
    }
  ],
  "syntheticMonitorOutageHandlingSettings": {
    "globalOutages": true,
    "localOutages": false,
    "globalConsecutiveOutageCountThreshold": 1,
    "origin": "MONITOR"
  },
  "performanceThresholds": {
    "enabled": false
  },
  "tags": [],
  "primaryGrailTags": [],
  "modificationTimestamp": 1783945095054
}
```

```json
{
  "name": "DEMO - ICMP custom device group",
  "description": "Instead of explicit list of IPs we have a monitor defined using filtering. Monitor is based on the extensionGroup == Custom device group for E2E. Success rate constraints are set to =100%.",
  "type": "MULTI_PROTOCOL",
  "frequencyMin": 1,
  "locations": [
    "SYNTHETIC_LOCATION-<your-private-activegate-location-id>"
  ],
  "enabled": true,
  "steps": [
    {
      "requestType": "ICMP",
      "targetFilter": "extensionGroup == \"Custom device group for E2E\"",
      "targetList": [],
      "properties": {
        "ICMP_NUMBER_OF_PACKETS": "5"
      },
      "constraints": [
        {
          "type": "SUCCESS_RATE_PERCENT",
          "properties": {
            "value": "100",
            "operator": "="
          }
        }
      ],
      "requestConfigurations": [
        {
          "constraints": [
            {
              "type": "ICMP_SUCCESS_RATE_PERCENT",
              "properties": {
                "value": "100",
                "operator": "="
              }
            }
          ]
        }
      ],
      "name": "DEMO - ICMP custom device group - step"
    }
  ],
  "syntheticMonitorOutageHandlingSettings": {
    "globalOutages": true,
    "localOutages": false,
    "globalConsecutiveOutageCountThreshold": 1,
    "origin": "MONITOR"
  },
  "performanceThresholds": {
    "enabled": false
  },
  "tags": [],
  "modificationTimestamp": 1783675181516
}
```

```json
{
  "name": "DEMO - ICMP custom device interface",
  "description": "Instead of explicit list of IPs we have a monitor defined using filtering. Monitor is based on the interfacesOf == CUSTOM_DEVICE-<id>. Success rate constraints are set to =100%.",
  "type": "MULTI_PROTOCOL",
  "frequencyMin": 1,
  "locations": [
    "SYNTHETIC_LOCATION-<your-private-activegate-location-id>"
  ],
  "enabled": true,
  "steps": [
    {
      "requestType": "ICMP",
      "targetFilter": "interfacesOf == \"CUSTOM_DEVICE-<id>\"",
      "targetList": [],
      "properties": {
        "ICMP_NUMBER_OF_PACKETS": "5"
      },
      "constraints": [
        {
          "type": "SUCCESS_RATE_PERCENT",
          "properties": {
            "value": "100",
            "operator": "="
          }
        }
      ],
      "requestConfigurations": [
        {
          "constraints": [
            {
              "type": "ICMP_SUCCESS_RATE_PERCENT",
              "properties": {
                "value": "100",
                "operator": "="
              }
            }
          ]
        }
      ],
      "name": "DEMO - ICMP custom device interface - step"
    }
  ],
  "syntheticMonitorOutageHandlingSettings": {
    "globalOutages": true,
    "localOutages": false,
    "globalConsecutiveOutageCountThreshold": 1,
    "origin": "MONITOR"
  },
  "performanceThresholds": {
    "enabled": false
  },
  "tags": [],
  "modificationTimestamp": 1783675181129
}
```

### TCP - deprecated definition

Examples:
```json
{
  "name": "DEMO - TCP custom device",
  "description": "Monitor is based on the extensionName == Custom device for E2E. Success rate constraints are set to =100%.",
  "type": "MULTI_PROTOCOL",
  "frequencyMin": 1,
  "locations": [
    "SYNTHETIC_LOCATION-<your-private-activegate-location-id>"
  ],
  "enabled": true,
  "steps": [
    {
      "requestType": "TCP",
      "targetFilter": "extensionName == \"Custom device for E2E\"",
      "targetList": [],
      "properties": {
        "TCP_PORT_RANGES": "22"
      },
      "constraints": [
        {
          "type": "SUCCESS_RATE_PERCENT",
          "properties": {
            "value": "100",
            "operator": "="
          }
        }
      ],
      "requestConfigurations": [
        {
          "constraints": []
        }
      ],
      "name": "DEMO - TCP custom device - step"
    }
  ],
  "syntheticMonitorOutageHandlingSettings": {
    "globalOutages": true,
    "localOutages": false,
    "globalConsecutiveOutageCountThreshold": 1,
    "origin": "MONITOR"
  },
  "performanceThresholds": {
    "enabled": false
  },
  "tags": [],
  "primaryGrailTags": [],
  "modificationTimestamp": 1783945103120
}
```

```json
{
  "name": "DEMO - TCP custom device group",
  "description": "Monitor is based on the extensionGroup == Custom device group for E2E. Success rate constraints are set to =100%.",
  "type": "MULTI_PROTOCOL",
  "frequencyMin": 1,
  "locations": [
    "SYNTHETIC_LOCATION-<your-private-activegate-location-id>"
  ],
  "enabled": true,
  "steps": [
    {
      "requestType": "TCP",
      "targetFilter": "extensionGroup == \"Custom device group for E2E\"",
      "targetList": [],
      "properties": {
        "TCP_PORT_RANGES": "22"
      },
      "constraints": [
        {
          "type": "SUCCESS_RATE_PERCENT",
          "properties": {
            "value": "100",
            "operator": "="
          }
        }
      ],
      "requestConfigurations": [
        {
          "constraints": []
        }
      ],
      "name": "DEMO - TCP custom device group - step"
    }
  ],
  "syntheticMonitorOutageHandlingSettings": {
    "globalOutages": true,
    "localOutages": false,
    "globalConsecutiveOutageCountThreshold": 1,
    "origin": "MONITOR"
  },
  "performanceThresholds": {
    "enabled": false
  },
  "tags": [],
  "modificationTimestamp": 1783675182308
}
```

```json
{
  "name": "DEMO - TCP custom device interface",
  "description": "Monitor is based on the interfacesOf == CUSTOM_DEVICE-<id>. Success rate constraints are set to =100%.",
  "type": "MULTI_PROTOCOL",
  "frequencyMin": 1,
  "locations": [
    "SYNTHETIC_LOCATION-<your-private-activegate-location-id>"
  ],
  "enabled": true,
  "steps": [
    {
      "requestType": "TCP",
      "targetFilter": "interfacesOf == \"CUSTOM_DEVICE-<id>\"",
      "targetList": [],
      "properties": {
        "TCP_PORT_RANGES": "22"
      },
      "constraints": [
        {
          "type": "SUCCESS_RATE_PERCENT",
          "properties": {
            "value": "100",
            "operator": "="
          }
        }
      ],
      "requestConfigurations": [
        {
          "constraints": []
        }
      ],
      "name": "DEMO - TCP custom device interface - step"
    }
  ],
  "syntheticMonitorOutageHandlingSettings": {
    "globalOutages": true,
    "localOutages": false,
    "globalConsecutiveOutageCountThreshold": 1,
    "origin": "MONITOR"
  },
  "performanceThresholds": {
    "enabled": false
  },
  "tags": [],
  "modificationTimestamp": 1783675180598
}
```

### Replacing targetFilter with explicit host steps

`targetFilter` (e.g. `extensionName == "..."`, `extensionGroup == "..."`, `interfacesOf == "..."`) is a
deprecated dynamic lookup that resolved Custom Device entities to their IP addresses at runtime.
Replace `targetFilter` with explicit IP targets using one of three approaches:

- **dtctl YAML** (Step 3a above): creates a `NETWORK_AVAILABILITY` monitor (`type: NETWORK_AVAILABILITY` in the manifest) — apply with `dtctl apply`.
- **Settings API** (see **Create ICMP Monitor (Settings API v2)** and **Create TCP Monitor (Settings API v2)** sections above): creates a `NETWORK_AVAILABILITY` monitor — POST to `/api/v2/settings/objects` with `schemaId=builtin:synthetic.monitors.network-availability`.
- **Environment API v2** (see **Managing Monitors via the Environment API v2** section above): keeps `"type": "MULTI_PROTOCOL"` — POST to `/api/v2/synthetic/monitors` replacing `targetFilter` with an explicit `targetList` array of the resolved IPs.

**Migration approach:**
1. Discover the IPs the old filter was resolving to (Step 1 below).
2. Create the replacement monitor using dtctl YAML, Settings API, or Environment API v2 (see options above) with one step per resolved IP (or all IPs in `targetList` in one step for the Environment API v2 path).
3. Carry over equivalent settings: `frequencyMin`, `locations`, `enabled`, `constraints`, `requestConfigurations`, step `properties` (field names and schema differ between approaches — adapt rather than copy verbatim).
4. Delete the old `MULTI_PROTOCOL` monitor once the replacement is verified.

**Step 1 — Discover the IPs the filter was resolving to**

Query Grail to find IP addresses of the custom devices the old filter matched.
The `filter` clause must be adapted to match the variant used in the original `targetFilter`:

| `targetFilter` variant | Suggested DQL filter starting point |
|------------------------|-------------------------------------|
| `extensionName == "..."` | `entity.detected_name == "<value>"` |
| `extensionGroup == "..."` | `entity.detected_name == "<value>"` or inspect `customProperties` — adapt to how groups are exposed on your devices |
| `interfacesOf == "CUSTOM_DEVICE-<id>"` | `id == "CUSTOM_DEVICE-<id>"` to find the parent device, then follow interface relationships |

`entity.detected_name` is a common starting point for name-based filters, but is not a guaranteed mapping for all variants — inspect the entity fields returned and adapt accordingly.

Example using `entity.detected_name` (suitable for `extensionName` / `extensionGroup` name matching):

```dql
fetch dt.entity.custom_device
| fieldsAdd entity.name, entity.detected_name, entity.type,
            ipAddress, dnsNames, customProperties,
            managementZones, tags, lifetime
| filter entity.detected_name == "Custom device for E2E"
| sort entity.name asc
```

Filter using `classicEntitySelector`:

```dql
fetch dt.entity.custom_device
| filter in(id, classicEntitySelector("type(CUSTOM_DEVICE)"))
| fieldsAdd entity.name, entity.detected_name, entity.type,
            ipAddress, dnsNames, tags, managementZones, lifetime
| sort entity.name asc
```

Each row's `ipAddress` field contains the IPs to use as the host list in each replacement step.

---

**Step 2 — Build the replacement monitor**

Create a new `NETWORK_AVAILABILITY` monitor (dtctl YAML, Settings API, or Environment API v2 — see options above). Carry over equivalent settings: `frequencyMin`, `locations`, `enabled`, `tags`, step `properties` (e.g. `ICMP_NUMBER_OF_PACKETS`, `TCP_PORT_RANGES`), `constraints`, and `requestConfigurations`.

**ICMP — before (deprecated):**

```json
{
  "type": "MULTI_PROTOCOL",
  "steps": [
    {
      "requestType": "ICMP",
      "targetFilter": "extensionName == \"Custom device for E2E\"",
      "targetList": [],
      "constraints": [
        {
          "type": "SUCCESS_RATE_PERCENT",
          "properties": {
            "value": "100",
            "operator": "="
          }
        }
      ],
      "requestConfigurations": [
        {
          "constraints": [
            {
              "type": "ICMP_SUCCESS_RATE_PERCENT",
              "properties": {
                "value": "100",
                "operator": "="
              }
            }
          ]
        }
      ]
    }
  ]
}
```

**ICMP — after (dtctl YAML):**

```yaml
schemaId: builtin:synthetic.monitors.network-availability
scope: environment
value:
  name: "ICMP Monitor — Custom device for E2E"
  enabled: true
  type: NETWORK_AVAILABILITY
  frequencyMin: 1
  locations:
    - SYNTHETIC_LOCATION-<your-private-activegate-location-id>
  steps:
    - name: "Ping 192.168.1.10"
      requestType: ICMP
      host: "192.168.1.10"
    - name: "Ping 192.168.1.11"
      requestType: ICMP
      host: "192.168.1.11"
  tags: []
```

**ICMP — after (Settings API JSON, NETWORK_AVAILABILITY):**

```json
[{
  "schemaId": "builtin:synthetic.monitors.network-availability",
  "scope": "environment",
  "value": {
    "name": "ICMP Monitor — Custom device for E2E",
    "enabled": true,
    "type": "NETWORK_AVAILABILITY",
    "frequencyMin": 1,
    "locations": ["SYNTHETIC_LOCATION-<your-private-activegate-location-id>"],
    "steps": [
      { "name": "Ping 192.168.1.10", "requestType": "ICMP", "host": "192.168.1.10" },
      { "name": "Ping 192.168.1.11", "requestType": "ICMP", "host": "192.168.1.11" }
    ]
  }
}]
```

**ICMP — after (Environment API v2 JSON, MULTI_PROTOCOL):**

```json
{
  "name": "ICMP Monitor — Custom device for E2E",
  "type": "MULTI_PROTOCOL",
  "enabled": true,
  "frequencyMin": 1,
  "locations": ["SYNTHETIC_LOCATION-<your-private-activegate-location-id>"],
  "steps": [
    { "name": "Ping 192.168.1.10", "requestType": "ICMP", "targetList": ["192.168.1.10"] },
    { "name": "Ping 192.168.1.11", "requestType": "ICMP", "targetList": ["192.168.1.11"] }
  ],
  "tags": []
}
```

**TCP — before (deprecated):**

```json
{
  "type": "MULTI_PROTOCOL",
  "steps": [
    {
      "requestType": "TCP",
      "targetFilter": "extensionName == \"Custom device for E2E\"",
      "targetList": [],
      "properties": {
        "TCP_PORT_RANGES": "22"
      },
      "constraints": [
        {
          "type": "SUCCESS_RATE_PERCENT",
          "properties": {
            "value": "100",
            "operator": "="
          }
        }
      ],
      "requestConfigurations": [
        {
          "constraints": []
        }
      ]
    }
  ]
}
```

**TCP — after (dtctl YAML):**

```yaml
schemaId: builtin:synthetic.monitors.network-availability
scope: environment
value:
  name: "TCP Monitor — Custom device for E2E"
  enabled: true
  type: NETWORK_AVAILABILITY
  frequencyMin: 1
  locations:
    - SYNTHETIC_LOCATION-<your-private-activegate-location-id>
  steps:
    - name: "TCP 192.168.1.10:22"
      requestType: TCP
      host: "192.168.1.10"
      port: 22
    - name: "TCP 192.168.1.11:22"
      requestType: TCP
      host: "192.168.1.11"
      port: 22
  tags: []
```

**TCP — after (Settings API JSON, NETWORK_AVAILABILITY):**

```json
[{
  "schemaId": "builtin:synthetic.monitors.network-availability",
  "scope": "environment",
  "value": {
    "name": "TCP Monitor — Custom device for E2E",
    "enabled": true,
    "type": "NETWORK_AVAILABILITY",
    "frequencyMin": 1,
    "locations": ["SYNTHETIC_LOCATION-<your-private-activegate-location-id>"],
    "steps": [
      { "name": "TCP 192.168.1.10:22", "requestType": "TCP", "host": "192.168.1.10", "port": 22 },
      { "name": "TCP 192.168.1.11:22", "requestType": "TCP", "host": "192.168.1.11", "port": 22 }
    ]
  }
}]
```

**TCP — after (Environment API v2 JSON, MULTI_PROTOCOL):**

```json
{
  "name": "TCP Monitor — Custom device for E2E",
  "type": "MULTI_PROTOCOL",
  "enabled": true,
  "frequencyMin": 1,
  "locations": ["SYNTHETIC_LOCATION-<your-private-activegate-location-id>"],
  "steps": [
    { "name": "TCP 192.168.1.10:22", "requestType": "TCP", "targetList": ["192.168.1.10"], "properties": { "TCP_PORT_RANGES": "22" } },
    { "name": "TCP 192.168.1.11:22", "requestType": "TCP", "targetList": ["192.168.1.11"], "properties": { "TCP_PORT_RANGES": "22" } }
  ],
  "tags": []
}
```

Key differences from the deprecated format:

| Field | Deprecated | dtctl YAML / Settings API | Environment API v2 |
|-------|------------|---------------------------|--------------------|
| `type` | `MULTI_PROTOCOL` | `NETWORK_AVAILABILITY` | `MULTI_PROTOCOL` |
| Entity created | `MULTIPROTOCOL_MONITOR-` | `NETWORK_AVAILABILITY_MONITOR-` | `MULTIPROTOCOL_MONITOR-` |
| Target selection | `targetFilter` — dynamic | `host` per step — explicit scalar | `targetList` per step — explicit array |
| Multi-host | Filter expands at runtime | One step per IP | One step per IP, or all IPs in one `targetList` |

> **Note:** Each step is checked independently; the monitor is UP only when all steps succeed.
> Use separate steps (one per host) to get per-host availability metrics and independent constraints.

Apply via `dtctl`:

```bash
dtctl apply -f icmp-monitor-migrated.yaml
```

Or via Settings API v2 — see the **Create ICMP Monitor** and **Create TCP Monitor** sections above.

Once the new monitor is verified, delete the old `MULTI_PROTOCOL` monitor:

```bash
curl -X DELETE "https://<env-id>.live.dynatrace.com/api/v2/synthetic/monitors/<monitorId>" \
  -H "Authorization: Api-Token <token>"
```

## Validation

### SNMP autodiscovery

After ~5 minutes, confirm discovered devices appear as `CUSTOM_DEVICE` entities:

```dql
fetch dt.entity.custom_device
| filter isNotNull(entity.detected_name)
| fields entity.name, entity.detected_name, ipAddress, lifetime
| sort entity.name asc
```

Check extension status via CLI:

```bash
dtctl get extensions | grep snmp
```

### ICMP/TCP monitors

Confirm monitors are active and reporting availability metrics.

**Classic (works on all tenants):**

```dql
timeseries avg(dt.synthetic.multi_protocol.availability),
  by: {dt.entity.multiprotocol_monitor}
```

**With Smartscape dimension (use only if `dt.smartscape.network_availability_monitor` is available on the tenant — see Smartscape status note above):**

```dql
timeseries avg(dt.synthetic.multi_protocol.availability),
  by: {dt.entity.multiprotocol_monitor, dt.smartscape.network_availability_monitor}
```

Confirm no active monitors still use the deprecated `targetFilter` by inspecting existing definitions:

```bash
curl -s "https://<env-id>.live.dynatrace.com/api/v2/synthetic/monitors?type=MULTI_PROTOCOL" \
  -H "Authorization: Api-Token <token>"
```

A `MULTI_PROTOCOL` monitor is fully replaced when a corresponding `NETWORK_AVAILABILITY` monitor is active and the old monitor has been deleted.

## References

- [`custom-devices.md`](custom-devices.md) — Custom devices (entity API) migration overview; parent reference for this guide
- `dt-obs-extensions` — Extension status, DEC error codes, monitoring configuration troubleshooting
- `dt-alerting` — Anomaly detector setup and notification routing for availability alerts
- `dt-dql-essentials` — DQL syntax reference for building custom availability queries
- `dt-obs-hosts` — Host-level metrics for machines also monitored by SNMP (correlation)
- [`entity-synthetic`](../entity-queries/entity-synthetic.md) — Migrate classic synthetic monitoring entity queries to Smartscape-based equivalents
