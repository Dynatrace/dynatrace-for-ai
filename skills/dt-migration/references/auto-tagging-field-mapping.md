# Auto-Tagging Keys → Semantic Dictionary Field Mapping

Maps the `Attribute` enum of `builtin:management-zones` (198 values) to the most appropriate field in this semantic dictionary. Two values have no row — `APPMON_SERVER_NAME` and `APPMON_SYSTEM_PROFILE_NAME`; every other value is covered, so a missing row for anything else means the key is not an `Attribute` value.

**Legend:**
- `—` — no direct equivalent exists in the semantic dictionary. **This is not a verdict that the discriminator cannot be enriched.** It means the table has no field to hand you; the attribute may still be derivable at ingest. A `—` is a route to the enrichment design (the `dt-upgrade` skill's autotagging reference), never a reason to report a zone as unmappable.

**Scope:** this table maps ME-attribute keys only. `DIMENSION` and log rules carry other condition types — `METRIC_KEY`, `LOG_FILE_NAME` — which have no row here; resolve those against the metric's own dimensions or the log record's fields instead.

---
## Notes

Any auto tagging key referring to ``*_TAGS`` uses a rule condition that is itself based on tags. Note that the referenced tags may either be the result of another rule for which a recursive search is then necessary to find the original underlying attribute. Alternatively, the referenced tags may also be imported from the monitored environment like cloud vendor tags/labels, Kubernetes labels/attributes or OneAgent environment variables. Cloud vendor tags have the pattern ``aws/azure/gcp.tags.*`` where

Dynatrace supports "primary tags" which is a way to letting customers select custom tags from the source environment and placing them as enriched fields on mass data and top level attributes on smartscape nodes. For example, a selected Kubernetes label ``team:backend`` on a POD becomes ``primary_tags.team:backend``. Smartscape nodes usually contain all collected environment labels and mass data only a selected subset. Smartscape nodes group labels or tags in the structure of the ``tags`` attribute.

### RUM name keys (`frontend.name`)

`WEB_APPLICATION_NAME`, `MOBILE_APPLICATION_NAME` and `CUSTOM_APPLICATION_NAME` all map onto the **same** field, `frontend.name`. Three consequences:

1. **The value form differs between mass data and Smartscape.** Smartscape FRONTEND nodes carry the display name with spaces (`easyTravel mainframe`); mass data (`user.events`, `user.sessions`) carries the underscored form (`easyTravel_mainframe`). A classic rule stores the display name, so porting its literal verbatim matches the Smartscape node and **zero** records — on the tenant used for validation, 0 of 18,081,945 `user.events` for `easyTravel mainframe` against 1,040,965 for `easyTravel_mainframe`. Run the value check (Stage 3 step 4 of the `dt-upgrade` skill's management-zones reference) against the data kind the Segment will filter, and translate the literal rather than copying it.
2. **Three classic keys collapse into one predicate.** A zone holding both a `WEB_APPLICATION_NAME` and a `MOBILE_APPLICATION_NAME` condition produces two filters on the same field, which over-matches wherever a web and a mobile app share a name. Qualify with the type field (`web` / `mobile` / `custom`) whenever a zone uses more than one of these keys — on the data kinds that carry it, per point 3. `dt.rum.agent.type` is the mapping for the `*_PLATFORM` keys and is **not** a substitute for this.
3. **The type qualifier is not on every RUM data kind — add it only where Stage 3 finds it populated.** On the validation tenant `frontend.type` was on every FRONTEND node and on every `user.events` record that carries a `frontend.name`, but on **no** `user.sessions` record, so a qualified sessions include matches nothing. `dt.rum.application.type`, which the frontends skill documents for the same split, was populated on none of them there. Measure which field the tenant carries on each data kind the Segment covers, with a control column. **Never drop the qualifier where the zone needs it:** it is needed when the zone uses more than one of these keys, or when a name it matches exists under more than one type. If such a zone covers a data kind that lacks the type field, that include is a **field gap** — record it in the plan as needing enrichment, or have the customer explicitly accept the broader scope; an unqualified include silently widens the zone. Where no matched name exists under more than one type, the qualifier changes nothing and can be left off a data kind that lacks it.

### Host name keys

`HOST_NAME`, `HOST_DETECTED_NAME` and `HOST_ONEAGENT_CUSTOM_HOST_NAME` behave like the RUM name keys above: the mass-data field is `host.name`, but **on Smartscape HOST nodes the populated attribute is `name`**. `host.name` is null on nodes OneAgent does not name itself — vmware, GCP, Azure and discovery-mode hosts. On the validation tenant it was non-null on 30 of 47 nodes while `name` was populated on all 47, and one of the 17 nulls was the exact literal a `HOST_NAME EQUALS` rule matched on in the tenant's highest-usage zone. Filter node-side on `name`; use `host.name` only against mass data.

## HOST

Matching Smartscape Node: HOST

| Auto-Tagging Key | Mass Data Field or Smartscape Node Attribute |
|---|---|
| `HOST_NAME` | `host.name` on mass data; **`name` on Smartscape HOST nodes** — see [Host name keys](#host-name-keys) |
| `HOST_DETECTED_NAME` | `host.name` on mass data; **`name` on Smartscape HOST nodes** |
| `HOST_AWS_NAME_TAG` | `aws.tags.name` or  ``tags:aws[name]``|
| `HOST_ONEAGENT_CUSTOM_HOST_NAME` | `host.name` on mass data; **`name` on Smartscape HOST nodes** |
| `HOST_TAGS` | See above general notes |
| `HOST_IP_ADDRESS` | `host.ip` |
| `HOST_OS_TYPE` | `os.type` |
| `HOST_OS_VERSION` | `os.version` |
| `HOST_ARCHITECTURE` | `os.architecture` |
| `HOST_BITNESS` | `process.bitness` |
| `HOST_CLOUD_TYPE` | `cloud.provider` — **enum values differ**: classic `EC2`/`AZURE`/`GOOGLE_CLOUD_PLATFORM` → live `aws`/`azure`/`gcp` (lowercase short names). Translate the literal; do not port it. For account-scoped zones prefer `aws.account.id` / `azure.subscription` / `gcp.project.id` per the `dt-upgrade` skill's management-zone classification reference. |
| `HOST_HYPERVISOR_TYPE` | — |
| `HOST_PAAS_TYPE` | `cloud.platform` |
| `HOST_PAAS_MEMORY_LIMIT` | `host.physical.memory` |
| `HOST_TECHNOLOGY` | — |
| `HOST_CPU_CORES` | `host.logical.cpu.cores` |
| `HOST_LOGICAL_CPU_CORES` | `host.logical.cpu.cores` |
| `HOST_CUSTOM_METADATA` | — |
| `HOST_KUBERNETES_LABELS` | `tags:k8s.labels[<label_key>]` to be found on K8S_NODE *not* on the HOST |
| `HOST_AZURE_WEB_APPLICATION_HOST_NAMES` | `azure.container_app.hostname` |
| `HOST_AZURE_WEB_APPLICATION_SITE_NAMES` | `azure.site_name` |
| `HOST_AZURE_COMPUTE_MODE` | `azure.resource.type` |
| `HOST_AZURE_SKU` | — |
| `HOST_AIX_VIRTUAL_CPU_COUNT` | `host.virtual.cpus` |
| `HOST_AIX_LOGICAL_CPU_COUNT` | `host.logical.cpus` |
| `HOST_AIX_SIMULTANEOUS_THREADS` | `host.simultaneous.multithreading` |
| `HOST_BOSH_NAME` | — |
| `HOST_BOSH_INSTANCE_ID` | — |
| `HOST_BOSH_INSTANCE_NAME` | — |
| `HOST_BOSH_AVAILABILITY_ZONE` | `aws.availability_zone` |
| `HOST_BOSH_DEPLOYMENT_ID` | — |
| `HOST_BOSH_STEMCELL_VERSION` | — |
| `HOST_GROUP_NAME` | `dt.host_group.id` |
| `HOST_GROUP_ID` | Formerly `dt.entity.host_group` but must now be resolved under `dt.host_group.id` representing the plaintext identifier on which the classic entity was based on. |
| `GOOGLE_COMPUTE_INSTANCE_ID` | `gcp.instance.id` |
| `GOOGLE_COMPUTE_INSTANCE_NAME` | `gcp.resource.name` |
| `GOOGLE_COMPUTE_INSTANCE_MACHINE_TYPE` | `gcp.resource.type` |
| `GOOGLE_COMPUTE_INSTANCE_PUBLIC_IP_ADDRESSES` | `host.ip` |
| `GOOGLE_COMPUTE_INSTANCE_PROJECT` | `gcp.organization.name` |
| `GOOGLE_COMPUTE_INSTANCE_PROJECT_ID` | `gcp.project.id` |

---

## PROCESS_GROUP

Matching Smartscape Node: Does not exist, attributes need to be found on PROCESS nodes

| Auto-Tagging Key | Semantic Dictionary Field |
|---|---|
| `PROCESS_GROUP_NAME` | `dt.process_group.detected_name` |
| `PROCESS_GROUP_DETECTED_NAME` | `dt.process_group.detected_name` |
| `PROCESS_GROUP_TAGS` | See above general notes  |
| `PROCESS_GROUP_LISTEN_PORT` | `process.listen_ports` |
| `PROCESS_GROUP_TECHNOLOGY` | `process.software_technologies` (plus per-runtime sub-fields; coverage is sparse — verify before relying on it) |
| `PROCESS_GROUP_TECHNOLOGY_EDITION` | — |
| `PROCESS_GROUP_TECHNOLOGY_VERSION` | — |
| `PROCESS_GROUP_ID` | The value of this property corresponds to `dt.entity.process_group`. No Smartscape node of this kind exists, but that former entity's properties may now be found under `dt.process_group.id` on a `dt.smartscape.process` node.  |
| `PROCESS_GROUP_AZURE_HOST_NAME` | `azure.container_app.hostname` |
| `PROCESS_GROUP_AZURE_SITE_NAME` | `azure.site_name` |
| `PROCESS_GROUP_CUSTOM_METADATA` | `process.metadata` |
| `PROCESS_GROUP_PREDEFINED_METADATA` | `process.metadata` |

---

## SERVICE

Matching Smartscape Node: SERVICE

| Auto-Tagging Key | Semantic Dictionary Field |
|---|---|
| `SERVICE_NAME` | `dt.service.name` |
| `SERVICE_DETECTED_NAME` | `dt.service.name` |
| `SERVICE_TAGS` | See above general notes  |
| `SERVICE_PORT` | `server.port` |
| `SERVICE_TYPE` | — |
| `SERVICE_TOPOLOGY` | — |
| `SERVICE_TECHNOLOGY` | — |
| `SERVICE_TECHNOLOGY_EDITION` | — |
| `SERVICE_TECHNOLOGY_VERSION` | — |
| `SERVICE_DATABASE_NAME` | `db.namespace` |
| `SERVICE_DATABASE_VENDOR` | `db.system` |
| `SERVICE_DATABASE_TOPOLOGY` | — |
| `SERVICE_DATABASE_HOST_NAME` | `server.address` |
| `SERVICE_WEB_SERVER_ENDPOINT` | `url.full` |
| `SERVICE_PUBLIC_DOMAIN_NAME` | `url.domain` |
| `SERVICE_REMOTE_ENDPOINT` | `server.address` |
| `SERVICE_REMOTE_SERVICE_NAME` | `service.name` |
| `SERVICE_IBM_CTG_GATEWAY_URL` | `url.full` |
| `SERVICE_AKKA_ACTOR_SYSTEM` | `messaging.akka.actor.system` |
| `SERVICE_MESSAGING_LISTENER_CLASS_NAME` | `messaging.system` |
| `SERVICE_WEB_APPLICATION_ID` | `dt.rum.application.id` |
| `SERVICE_WEB_CONTEXT_ROOT` | `url.path` |
| `SERVICE_WEB_SERVER_NAME` | `server.address` |
| `SERVICE_WEB_SERVICE_NAME` | `rpc.service` |
| `SERVICE_WEB_SERVICE_NAMESPACE` | `rpc.namespace` |
| `SERVICE_CTG_SERVICE_NAME` | `rpc.service` |
| `SERVICE_ESB_APPLICATION_NAME` | `service.name` |

---

## QUEUE

Matching Smartscape Node: SERVICE

| Auto-Tagging Key | Semantic Dictionary Field |
|---|---|
| `QUEUE_NAME` | `messaging.destination.name` |
| `QUEUE_VENDOR` | `messaging.system` |
| `QUEUE_TECHNOLOGY` | `messaging.system` |

---

## CUSTOM_DEVICE

Matching Smartscape Node: Depends on the custom devices "type" attribute.

| Auto-Tagging Key | Semantic Dictionary Field |
|---|---|
| `CUSTOM_DEVICE_NAME` | `name` |
| `CUSTOM_DEVICE_TAGS` | See above general notes  |
| `CUSTOM_DEVICE_IP_ADDRESS` | `device.address` |
| `CUSTOM_DEVICE_PORT` | `device.port` |
| `CUSTOM_DEVICE_DNS_ADDRESS` | `server.address` |
| `CUSTOM_DEVICE_TECHNOLOGY` | — |
| `CUSTOM_DEVICE_METADATA` | — |

---

## CUSTOM_DEVICE_GROUP

Matching Smartscape Node: No equivalent type.

| Auto-Tagging Key | Semantic Dictionary Field |
|---|---|
| `CUSTOM_DEVICE_GROUP_NAME` | — |
| `CUSTOM_DEVICE_GROUP_TAGS` | See above general notes  |

---

## WEB_APPLICATION

Matching Smartscape Node: FRONTEND

| Auto-Tagging Key | Semantic Dictionary Field |
|---|---|
| `WEB_APPLICATION_NAME` | `frontend.name` — where the zone needs the type distinction, qualify with the type field (`web`) on data kinds that carry it, and record a field gap on those that do not; see [RUM name keys](#rum-name-keys-frontendname) |
| `WEB_APPLICATION_NAME_PATTERN` | `url.path.pattern` |
| `WEB_APPLICATION_TAGS` | See above general notes  |
| `WEB_APPLICATION_TYPE` | `browser.type` |

---

## MOBILE_APPLICATION

Matching Smartscape Node: FRONTEND

| Auto-Tagging Key | Semantic Dictionary Field |
|---|---|
| `MOBILE_APPLICATION_NAME` | `frontend.name` — where the zone needs the type distinction, qualify with the type field (`mobile`) on data kinds that carry it, and record a field gap on those that do not; see [RUM name keys](#rum-name-keys-frontendname) |
| `MOBILE_APPLICATION_TAGS` | See above general notes  |
| `MOBILE_APPLICATION_PLATFORM` | `dt.rum.agent.type` |

---

## CUSTOM_APPLICATION

Matching Smartscape Node: FRONTEND

| Auto-Tagging Key | Semantic Dictionary Field |
|---|---|
| `CUSTOM_APPLICATION_NAME` | `frontend.name` — where the zone needs the type distinction, qualify with the type field (`custom`) on data kinds that carry it, and record a field gap on those that do not; see [RUM name keys](#rum-name-keys-frontendname) |
| `CUSTOM_APPLICATION_TAGS` | See above general notes  |
| `CUSTOM_APPLICATION_PLATFORM` | `dt.rum.agent.type` |
| `CUSTOM_APPLICATION_TYPE` | — |

---

## ENTERPRISE_APPLICATION (DC-RUM App)

Matching Smartscape Node: No equivalent

| Auto-Tagging Key | Semantic Dictionary Field |
|---|---|
| `ENTERPRISE_APPLICATION_NAME` | `service.name` |
| `ENTERPRISE_APPLICATION_TAGS` | See above general notes  |
| `ENTERPRISE_APPLICATION_DECODER_TYPE` | — |
| `ENTERPRISE_APPLICATION_IP_ADDRESS` | `host.ip` |
| `ENTERPRISE_APPLICATION_PORT` | `server.port` |
| `ENTERPRISE_APPLICATION_METADATA` | — |

---

## DATA_CENTER_SERVICE (DC-RUM Service)

Matching Smartscape Node: No equivalent

| Auto-Tagging Key | Semantic Dictionary Field |
|---|---|
| `DATA_CENTER_SERVICE_NAME` | `service.name` |
| `DATA_CENTER_SERVICE_TAGS` | See above general notes  |
| `DATA_CENTER_SERVICE_DECODER_TYPE` | — |
| `DATA_CENTER_SERVICE_IP_ADDRESS` | `host.ip` |
| `DATA_CENTER_SERVICE_PORT` | `server.port` |
| `DATA_CENTER_SERVICE_METADATA` | — |

---

## BROWSER_MONITOR (Synthetic Test)

| Auto-Tagging Key | Semantic Dictionary Field |
|---|---|
| `BROWSER_MONITOR_NAME` | Name of `dt.smartscape.browser_monitor`. |
| `BROWSER_MONITOR_TAGS` | See above general notes  |

---

## EXTERNAL_MONITOR (External Synthetic Test)

Matching Smartscape Node: Coming later.

| Auto-Tagging Key | Semantic Dictionary Field |
|---|---|
| `EXTERNAL_MONITOR_NAME` | - |
| `EXTERNAL_MONITOR_TAGS` | See above general notes  |
| `EXTERNAL_MONITOR_ENGINE_TYPE` | — |
| `EXTERNAL_MONITOR_ENGINE_NAME` | — |
| `EXTERNAL_MONITOR_ENGINE_DESCRIPTION` | — |

---

## HTTP_MONITOR

| Auto-Tagging Key | Semantic Dictionary Field |
|---|---|
| `HTTP_MONITOR_NAME` | Name of `dt.smartscape.http_monitor` |
| `HTTP_MONITOR_TAGS` | See above general notes  |

---

## NETWORK_AVAILABILITY_MONITOR (NAM)

Matching Smartscape Node: `NETWORK_AVAILABILITY_MONITOR` (planned; see [type-mappings.md](type-mappings.md))

| Auto-Tagging Key | Semantic Dictionary Field |
|---|---|
| `NETWORK_AVAILABILITY_MONITOR_NAME` | Name of `dt.smartscape.network_availability_monitor` (planned) |
| `NETWORK_AVAILABILITY_MONITOR_TAGS` | See above general notes |

---

## DOCKER

Matching Smartscape Node: CONTAINER

| Auto-Tagging Key | Semantic Dictionary Field |
|---|---|
| `DOCKER_CONTAINER_NAME` | `container.name` |
| `DOCKER_FULL_IMAGE_NAME` | `container.image.name` |
| `DOCKER_IMAGE_VERSION` | `container.image.version` |

---

## ESXI_HOST (Hypervisor)

Matching Smartscape Node: No equivalent — the rows below resolve onto the underlying host, not onto an ESXi node. In classic the entity type is `dt.entity.hypervisor`; there is no `dt.entity.esxi_host`, so a query written against that name fails with "entity type wasn't found".

| Auto-Tagging Key | Semantic Dictionary Field |
|---|---|
| `ESXI_HOST_NAME` | `host.name` |
| `ESXI_HOST_TAGS` | — |
| `ESXI_HOST_HARDWARE_MODEL` | — |
| `ESXI_HOST_HARDWARE_VENDOR` | — |
| `ESXI_HOST_PRODUCT_NAME` | `os.name` |
| `ESXI_HOST_PRODUCT_VERSION` | `os.version` |
| `ESXI_HOST_CLUSTER_NAME` | — (vSphere/ESXi cluster, **not** `k8s.cluster.name`) |

---

## EC2_INSTANCE

Matching Smartscape Node: AWS_EC2_INSTANCE

| Auto-Tagging Key | Semantic Dictionary Field |
|---|---|
| `EC2_INSTANCE_NAME` | `aws.resource.name` |
| `EC2_INSTANCE_TAGS` | `See above general notes  |
| `EC2_INSTANCE_ID` | `aws.resource.id` |
| `EC2_INSTANCE_PRIVATE_HOST_NAME` | `host.name` |
| `EC2_INSTANCE_PUBLIC_HOST_NAME` | `host.fqdn` |
| `EC2_INSTANCE_AWS_INSTANCE_TYPE` | `aws.resource.type` |
| `EC2_INSTANCE_AWS_SECURITY_GROUP` | `aws.arn` |
| `EC2_INSTANCE_AMI_ID` | `container.image.digest` |
| `EC2_INSTANCE_BEANSTALK_ENV_NAME` | `deployment.release_stage` |

---

## OPENSTACK_VM

Matching Smartscape Node: Unknown

| Auto-Tagging Key | Semantic Dictionary Field |
|---|---|
| `OPENSTACK_VM_NAME` | `host.name` |
| `OPENSTACK_VM_INSTANCE_TYPE` | — |
| `OPENSTACK_VM_SECURITY_GROUP` | — |

---

## VMWARE_VM

Matching Smartscape Node: Unknown.

| Auto-Tagging Key | Semantic Dictionary Field |
|---|---|
| `VMWARE_VM_NAME` | `host.name` |

---

## KUBERNETES

Matching Smartscape Nodes, K8S_CLUSTER, K8S_NODE, K8S_SERVICE

| Auto-Tagging Key | Semantic Dictionary Field |
|---|---|
| `KUBERNETES_CLUSTER_NAME` | `k8s.cluster.name` |
| `KUBERNETES_NODE_NAME` | `k8s.node.name` |
| `KUBERNETES_SERVICE_NAME` | `k8s.service.name` |

---

## CLOUD_APPLICATION

Matching Smartscape Node: K8S_DEPLOYMENT, K8S_REPLICASET, K8S_STATEFULSET, K8S_DAEMONSET, K8S_JOB, K8S_CRONJOB 

| Auto-Tagging Key | Semantic Dictionary Field |
|---|---|
| `CLOUD_APPLICATION_NAME` | `k8s.workload.name` |
| `CLOUD_APPLICATION_LABELS` | `k8s.workload.label.__attribute_name__` |
| `CLOUD_APPLICATION_NAMESPACE_NAME` | `k8s.namespace.name` |
| `CLOUD_APPLICATION_NAMESPACE_LABELS` | `k8s.namespace.label.__attribute_name__` |

---

## AWS_AUTO_SCALING_GROUP

Matching Smartscape Node: AWS_AUTOSCALING_AUTOSCALINGROUP

| Auto-Tagging Key | Semantic Dictionary Field |
|---|---|
| `AWS_AUTO_SCALING_GROUP_NAME` | `aws.resource.name` |
| `AWS_AUTO_SCALING_GROUP_TAGS` | `aws.tags.__tag_key__` |

---

## AWS_CLASSIC_LOAD_BALANCER

Matching Smartscape Node: AWS_ELASTICLOADBALANCING_LOADBALANCER

| Auto-Tagging Key | Semantic Dictionary Field |
|---|---|
| `AWS_CLASSIC_LOAD_BALANCER_NAME` | `aws.resource.name` |
| `AWS_CLASSIC_LOAD_BALANCER_TAGS` | `aws.tags.__tag_key__` |
| `AWS_CLASSIC_LOAD_BALANCER_FRONTEND_PORTS` | `server.port` |

---

## AWS_APPLICATION_LOAD_BALANCER

Matching Smartscape Node: TBD

| Auto-Tagging Key | Semantic Dictionary Field |
|---|---|
| `AWS_APPLICATION_LOAD_BALANCER_NAME` | `aws.alb.name` |
| `AWS_APPLICATION_LOAD_BALANCER_TAGS` | `aws.tags.__tag_key__` |

---

## AWS_NETWORK_LOAD_BALANCER

Matching Smartscape Node: TBD

| Auto-Tagging Key | Semantic Dictionary Field |
|---|---|
| `AWS_NETWORK_LOAD_BALANCER_NAME` | `aws.resource.name` |
| `AWS_NETWORK_LOAD_BALANCER_TAGS` | `aws.tags.__tag_key__` |

---

## AWS_RELATIONAL_DATABASE_SERVICE

Matching Smartscape Node: AWS_RDS_DBCLUSTER

| Auto-Tagging Key | Semantic Dictionary Field |
|---|---|
| `AWS_RELATIONAL_DATABASE_SERVICE_NAME` | `aws.resource.name` |
| `AWS_RELATIONAL_DATABASE_SERVICE_TAGS` | `aws.tags.__tag_key__` |
| `AWS_RELATIONAL_DATABASE_SERVICE_INSTANCE_CLASS` | `aws.resource.type` |
| `AWS_RELATIONAL_DATABASE_SERVICE_ENDPOINT` | `server.address` |
| `AWS_RELATIONAL_DATABASE_SERVICE_ENGINE` | `db.system` |
| `AWS_RELATIONAL_DATABASE_SERVICE_PORT` | `server.port` |
| `AWS_RELATIONAL_DATABASE_SERVICE_DB_NAME` | `db.namespace` |

---

## AWS_ACCOUNT

Matching Smartscape Node: AWS_ACCOUNT

| Auto-Tagging Key | Semantic Dictionary Field |
|---|---|
| `AWS_ACCOUNT_NAME` | `aws.account.name` |
| `AWS_ACCOUNT_ID` | `aws.account.id` |

---

## AZURE

Matching Smartscape Node: TBD

| Auto-Tagging Key | Semantic Dictionary Field |
|---|---|
| `AZURE_VM_NAME` | `azure.vm.name` |
| `AZURE_SCALE_SET_NAME` | `azure.vm_scale_set.name` |
| `AZURE_ENTITY_NAME` | `azure.resource.name` |
| `AZURE_ENTITY_TAGS` | `azure.tags.__tag_key__` |
| `AZURE_TENANT_NAME` | `azure.tenant.name` |
| `AZURE_TENANT_UUID` | `azure.tenant.id` |
| `AZURE_MGMT_GROUP_NAME` | `azure.management_group` |
| `AZURE_MGMT_GROUP_UUID` | `azure.management_group` |
| `AZURE_SUBSCRIPTION_NAME` | — |
| `AZURE_SUBSCRIPTION_UUID` | `azure.subscription` |

---

## DATACENTER

Matching Smartscape Node: TBD

| Auto-Tagging Key | Semantic Dictionary Field |
|---|---|
| `AWS_AVAILABILITY_ZONE_NAME` | `aws.availability_zone` |
| `AZURE_REGION_NAME` | `azure.location` |
| `GEOLOCATION_SITE_NAME` | `geo.name` |
| `GOOGLE_CLOUD_PLATFORM_ZONE_NAME` | `gcp.zone` |
| `OPENSTACK_AVAILABILITY_ZONE_NAME` | — |
| `OPENSTACK_REGION_NAME` | — |
| `VMWARE_DATACENTER_NAME` | — |

---

## OPENSTACK_ACCOUNT

Matching Smartscape Node: No equivalent

| Auto-Tagging Key | Semantic Dictionary Field |
|---|---|
| `OPENSTACK_ACCOUNT_NAME` | — |
| `OPENSTACK_ACCOUNT_PROJECT_NAME` | — |

---

## OPENSTACK

Matching Smartscape Node: No equivalent

| Auto-Tagging Key | Semantic Dictionary Field |
|---|---|
| `OPENSTACK_PROJECT_NAME` | — |
| `NAME_OF_COMPUTE_NODE` | `host.name` |

---

## CLOUD_FOUNDRY

Matching Smartscape Node: No equivalent

| Auto-Tagging Key | Semantic Dictionary Field |
|---|---|
| `CLOUD_FOUNDRY_ORG_NAME` | — |
| `CLOUD_FOUNDRY_FOUNDATION_NAME` | — |
