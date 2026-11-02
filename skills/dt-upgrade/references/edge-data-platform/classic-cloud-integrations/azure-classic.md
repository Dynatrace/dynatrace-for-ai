# Azure Classic Connection Reference

Distilled reference for the classic Azure monitoring integration.

---

## Two Classic Flavours

Azure has two primary classic monitoring approaches (plus Azure Native as a deployment variant):

| Flavour | Metric prefix (Grail) | Entity type | `dt.da.source` |
|---|---|---|---|
| **Built-in (classic)** | `dt.cloud.azure.<service>.*` | Dedicated (e.g., `AZURE_VM`) | null |
| **Cloud services (non-built-in)** | `cloud.azure.microsoft_<provider>.<resource>.*` | `CUSTOM_DEVICE` (`cloud:azure:*`) | null |

> **No Settings 2.0**: Classic Azure connections use the legacy Configuration API (`/api/config/v1/azure/credentials`), NOT Settings 2.0. There is no `builtin:cloud.azure` schema.

---

## Built-in Entity Types

`AZURE_VM`, `AZURE_VM_SCALE_SET`, `AZURE_LOAD_BALANCER`, `AZURE_EVENT_HUB_NAMESPACE`, `AZURE_EVENT_HUB`, `AZURE_REDIS_CACHE`, `AZURE_FUNCTION_APP`, `AZURE_STORAGE_ACCOUNT`, `AZURE_COSMOS_DB`, `AZURE_WEB_APP`, `AZURE_SQL_SERVER`, `AZURE_SQL_DATABASE`, `AZURE_SQL_ELASTIC_POOL`, `AZURE_IOT_HUB`, `AZURE_API_MANAGEMENT_SERVICE`, `AZURE_APPLICATION_GATEWAY`, `AZURE_SERVICE_BUS_NAMESPACE`, `AZURE_SERVICE_BUS_QUEUE`, `AZURE_SERVICE_BUS_TOPIC`

Topology entities: `AZURE_CREDENTIALS`, `AZURE_SUBSCRIPTION`, `AZURE_TENANT`, `AZURE_MGMT_GROUP`, `AZURE_REGION`

## Non-Built-in Entity Types (Custom Device Sub-types)

Common sub-types: `cloud:azure:cache:redis`, `cloud:azure:containerservice:managedcluster`, `cloud:azure:postgresql:flexibleservers`, `cloud:azure:cognitiveservices:openai`, `cloud:azure:storage:storageaccounts`, `cloud:azure:network:loadbalancers:standard`, `cloud:azure:app:containerapps`, `cloud:azure:apimanagement:service`, `cloud:azure:network:networkinterfaces`, `cloud:azure:network:publicipaddresses`, `cloud:azure:network:dnszones`

---

## Classic → Cloud Service Migration

Some services exist as BOTH classic built-in and cloud service — but you **cannot run both simultaneously**. Enabling the cloud version disables the classic version. This creates:
- A new entity with a different ID and metric keys
- Gaps in historical data during the switch
- Dashboard/alert breakage if hardcoded to classic entity IDs or metric keys

| Cloud Service | Replaces Classic |
|---|---|
| Azure Cache for Redis | Azure Redis (built-in) |
| Azure SQL Database | Azure SQL (built-in) |
| Azure Storage Account | Azure Storage accounts (built-in) |
| Azure Cosmos DB Account | Azure Cosmos DB (built-in) |
| Azure Basic/Standard Load Balancer | Azure Load Balancer (built-in) |

---

## Key Detection Queries

### Enumerate classic connections
```dql
fetch dt.entity.azure_credentials, from:now()-12h
| fieldsAdd entity.name, id, belongs_to
| fieldsRemove can_access
| fieldsAdd sub_id = belongs_to[`dt.entity.azure_subscription`][0]
| lookup [fetch dt.entity.azure_subscription | fieldsAdd azureSubscriptionUuid],
    sourceField:sub_id, lookupField:id, prefix:"sub."
| fields entity.name, id, sub_id, sub.azureSubscriptionUuid
```

### Classic metric source classification
```dql
fetch metric.series, from:now()-1h
| filter contains(metric.key, "azure")
| filterOut startsWith(metric.key, "dac.azure_")
| filterOut startsWith(metric.key, "remote_dsfm.")
| filterOut startsWith(metric.key, "dt.sfm.")
| summarize cnt=count(), by:{dt.da.source, dt.source_entity.type}
| sort cnt desc
```

### Custom device type counts
```dql
fetch dt.entity.custom_device
| filter contains(toString(entity.type), "cloud:azure")
| summarize cnt=count(), by:{entity.type}
| sort cnt desc
```

---

## Migration Notes

- Azure classic has no Metric Streams equivalent — no push-based ingestion.
- Unlike AWS, Azure classic entity types (`AZURE_VM`) use **different names** from new types (`AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINES`) — no name collision.
- The `cloud.azure.microsoft_*` prefix is shared with the new connection. See [disambiguation.md](disambiguation.md).
- Entity scoping uses `accessible_by[dt.entity.azure_subscription]` for built-in entities and `accessible_by[dt.entity.azure_credentials]` for custom devices.
