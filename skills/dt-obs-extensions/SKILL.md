---
name: dt-obs-extensions
description: Work with Dynatrace extensions - check extension status and help troubleshoot configuration issues
license: Apache-2.0
---

# Dynatrace Extensions Skill

## Overview

Dynatrace extensions allow you to extend the functionality of Dynatrace by integrating with external systems and custom data sources. 

**When to use this skill:**

- Checking the status of installed extensions and their monitoring configurations
- Troubleshooting extension configuration issues using DQL queries and event logs

## Extensions lifecycle
Extensions are first installed, which brings assets (dashboards, alert templates, OpenPipeline rules etc). Once installed, each extension can have multiple activation - Monitoring Configurations. Configurations can run on ActiveGate or OneAgent, and can be enabled/disabled independently. Each configuration has its own status, which can be queried using this skill.

## Extensions Monitoring Configurations and Statuses

### Extensions Statuses

To check the status of an extension, you can run following DQL query:

```dql
timeseries count(dt.sfm.extension.config.status), by: {dt.extension.name, dt.extension.config.id, dt.extension.status}
```

This query will return a timeseries with the status for each extension configuration. `dt.extension.name` is extension name `dt.extension.config.id` is extension Monitoring Configuration ID. The `dt.extension.status` field can have following values:
`OK` - Configuration is running without issues
`CUSTOM_CODE_EXTENSION_NOT_ALLOWED` - Extension is not allowed to run custom code, which is required for this configuration. To fix this, ActiveGate or OneAgent needs to be updated
`EEC_HARD_LIMIT_REJECTION` - Extension is rejected due to resource usage hard limit. Check Extensions Settings in ActiveGate and switch Performance Profile
`EEC_HARD_LIMIT_RESTART` - Extension is restarted due to resource usage hard limit. Check Extensions Settings in ActiveGate and switch Performance Profile
`EEC_RESTSERVER_ERROR` - EEC is unable to start REST API. Check if there are other processes that are using the same port
`EXTENSIONS_CACHE_ERROR` - ActiveGate or OneAgent is unable to download the extension. Check disk size
`EXTENSION_VERIFICATION_ERROR` - Extension verification failed. It means that extension.yaml is malformed
`GROUP_NAME_CHANGE` - Configurations are temporarily rebalanced because ActiveGate changed group.
`HIGH_CPU` - Extension is using too much CPU. Check Extensions Settings in ActiveGate and switch Performance Profile
`HIGH_CPU_RESTART` - Extension is restarted due to high CPU usage. Check Extensions Settings in ActiveGate and switch Performance Profile
`HIGH_MEMORY` - Extension is using too much memory. Check Extensions Settings in ActiveGate and switch Performance Profile
`HIGH_MEMORY_RESTART` - Extension is restarted due to high memory usage. Check Extensions Settings in ActiveGate and switch Performance Profile
`INCOMPATIBLE_API_ERROR` - Extension is using API that is not compatible with the current version of ActiveGate or OneAgent. Check extension documentation for supported versions or update ActiveGate or OneAgent
`MAX_TASKS_LIMIT_REJECTION` - Extension is rejected due to max tasks limit. Increase number of ActiveGates in the group or split group into smaller ones
`MISSING_BINARY` - Missing binary on ActiveGate or OneAgent - this indicates malformed installation. Reinstall the ActiveGate or OneAgent
`MISSING_DATASOURCE`- Missing binary on ActiveGate or OneAgent - this indicates malformed installation. Reinstall the ActiveGate or OneAgent
`RESTART` - Extension is being restarted
`STARTUP` - Extension is starting up
`STARTUP_ERROR` - Extension encountered an error during startup
`STARTUP_PENDING` - Extension startup is pending
`STARTUP_SCHEDULED` - Extension startup is scheduled
`TIMED_OUT_RESTART` - Extension restarted due to timeout
`IDLE` - Extensions is working, but did not produce any status
`GENERIC_ERROR` - Extension is in error state. Check extension logs for more details
`WARNING` - Extension is in warning state. Check extension logs for more details


## Extensions Monitoring Configurations Troubleshooting

If you see any status other than `OK`, it means that there is an issue with the extension configuration. You can get detailed logs executing following DQL query:

```dql
fetch dt.system.events | filter dt.extension.name == "<extension_name>" AND dt.extension.config.id == "<config_id>"
```

You may see error codes in content. Error Codes have format DEC:[A-Z0-9_]+. You can find the list of error codes and their meaning in [references/extensions-error-codes.md](references/extensions-error-codes.md) If you find error code in content, check the error code documentation for troubleshooting steps. If there is no error code, check the event content for more details about the issue.
