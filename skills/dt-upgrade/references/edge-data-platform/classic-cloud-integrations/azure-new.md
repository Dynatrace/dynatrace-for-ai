# Azure New Connection Reference

Distilled reference for the new Azure connection (Smartscape on Grail).
## Contents
- [Architecture](#architecture)
- [Entity Model](#entity-model)
- [Metric Key Format](#metric-key-format)
- [Key Detection Queries](#key-detection-queries)
- [Migration Notes](#migration-notes)
---

## Architecture

| Property | Value |
|---|---|
| Pipeline | Cloud-native Data Acquisition (DA) |
| Settings schema | `builtin:hyperscaler-authentication.connections.azure` |
| Auth | Federated Identity Credential |
| `dt.da.source` | `azure-metric-poller` |
| Entity model | Smartscape on Grail (`AZURE_MICROSOFT_*` types) |
| ActiveGate | Not required |
| Polling interval | 5 minutes (5-minute delay) |
| Status | **Preview** (March 2026) |

---

## Entity Type Naming

Pattern: `AZURE_MICROSOFT_<PROVIDER>_<RESOURCETYPE>` — derived from Azure resource types (uppercase, `.`/`/` → `_`).

Example: `microsoft.compute/virtualmachines` → `AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINES`

### Key Smartscape Entity Types

| Smartscape Type | Azure Service |
|---|---|
| `AZURE_MICROSOFT_RESOURCES_SUBSCRIPTIONS` | Subscription (topology container) |
| `AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINES` | Virtual Machines |
| `AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINESCALESETS` | VM Scale Sets |
| `AZURE_MICROSOFT_NETWORK_LOADBALANCERS` | Load Balancer |
| `AZURE_MICROSOFT_NETWORK_APPLICATIONGATEWAYS` | Application Gateway |
| `AZURE_MICROSOFT_CACHE_REDIS` | Cache for Redis |
| `AZURE_MICROSOFT_DOCUMENTDB_DATABASEACCOUNTS` | Cosmos DB |
| `AZURE_MICROSOFT_SQL_SERVERS_DATABASES` | SQL Database |
| `AZURE_MICROSOFT_EVENTHUB_NAMESPACES` | Event Hubs |
| `AZURE_MICROSOFT_SERVICEBUS_NAMESPACES` | Service Bus |
| `AZURE_MICROSOFT_WEB_SITES` | Web App / Function App |
| `AZURE_MICROSOFT_STORAGE_STORAGEACCOUNTS` | Storage Account |
| `AZURE_MICROSOFT_APP_CONTAINERAPPS` | Container Apps |
| `AZURE_MICROSOFT_APIMANAGEMENT_SERVICE` | API Management |
| `AZURE_MICROSOFT_CONTAINERSERVICE_MANAGEDCLUSTERS` | AKS |
| `AZURE_MICROSOFT_DBFORPOSTGRESQL_FLEXIBLESERVERS` | PostgreSQL Flexible |
| `AZURE_MICROSOFT_COGNITIVESERVICES_ACCOUNTS` | Cognitive Services / OpenAI |

---

## Metric Key Format

```
cloud.azure.microsoft_<provider>.<resource>.<MetricName>
```

- Provider: lowercase namespace (e.g., `microsoft_compute`, `microsoft_cache`)
- Resource: resource type (e.g., `virtualmachines`, `redis`)
- MetricName: Azure Monitor original casing

### Shared prefix with classic

The `cloud.azure.microsoft_*` prefix is identical to classic cloud services. Distinguish by `dt.da.source`:
- New: `dt.da.source == "azure-metric-poller"`
- Classic: `dt.da.source` is null

### Enrichment Dimensions

| Dimension | Description |
|---|---|
| `dt.da.source` | `azure-metric-poller` |
| `dt.smartscape_source.type` | Entity type |
| `dt.smartscape_source.id` | Entity ID |
| `azure.subscription` | Subscription ID |
| `azure.resource.type` | Azure resource type |
| `azure.resource.group` | Resource group |
| `azure.tag.<Key>` | Azure tags (up to 20) |

---

## Detection Queries

### Find all new connection metrics
```dql
fetch metric.series, from:now()-1h
| filter dt.da.source == "azure-metric-poller"
| summarize cnt=count(), by:{metric.key, dt.smartscape_source.type}
```

### List all Azure Smartscape entity types
```dql
smartscapeNodes "*"
| filter startsWith(type, "AZURE_")
| summarize cnt=count(), by:{type}
| sort cnt desc
```

### Enumerate monitored subscriptions
```dql
smartscapeNodes AZURE_MICROSOFT_RESOURCES_SUBSCRIPTIONS, from:now()-12h
| fields id, name, `azure.subscription`
```

### Detect new connections via Settings API
```
dtctl get settings --schema builtin:hyperscaler-authentication.connections.azure -o json
```

---

## Entity Attributes

All Azure Smartscape entities carry: `azure.subscription`, `azure.location`, `azure.resource.id`, `azure.resource.group`, `azure.resource.name`, `azure.resource.type`, `azure.object` (full ARM JSON), `tags`.

---

## Migration Notes

- Azure classic and new entity types use **different naming** — no name collisions (unlike AWS).
- Classic: `AZURE_VM` → New: `AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINES`. See [entity-type-mapping.md](entity-type-mapping.md).
- Classic cloud service metrics share the same key prefix as new connection metrics — requires disambiguation.
- Metric Streaming is NOT available or planned for Azure (neither classic nor new).
