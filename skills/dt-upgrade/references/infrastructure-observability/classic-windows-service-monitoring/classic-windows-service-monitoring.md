# Classic Windows Service Monitoring

<!-- Jira: none -->

**Gen3 replacement**: OS Services monitoring

**Phase 2 required**: no

## What changes

Classic Windows Service Monitoring (CWSM) has been deprecated for a long time. OS Services Monitoring (OSM) provides more flexibility and features.

## Customer actions

- Recreate service monitoring rules using OS Services monitoring

## Tracking queries

Check if the setting `builtin:os.services.monitoring` contains no enabled rules -- if so, no action needed.

## Documentation

- [Windows Services](https://docs.dynatrace.com/docs/shortlink/windows-services)
