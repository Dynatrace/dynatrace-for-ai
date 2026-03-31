# Inventory and Discovery Reference

Comprehensive reference for host/process discovery, technology inventory, port mapping, cost attribution, data quality, and multi-cloud management.

---

## Host Inventory

### All Hosts Overview

Fetch all hosts with basic information:

```dql
smartscapeNodes "HOST"
| fieldsAdd name, os.type, os.version, host.logical.cpu.cores, host.physical.memory
| sort name asc
```

### Host by Operating System

Group and count hosts by OS type:

```dql
smartscapeNodes "HOST"
| fieldsAdd os.type, os.version
| summarize host_count = count(), by: {os.type}
| sort host_count desc
```

**OS Types:** `LINUX`, `WINDOWS`, `AIX`, `SOLARIS`, `ZOS`

### Virtualization Analysis

Identify physical vs virtual hosts:

```dql
smartscapeNodes "HOST"
| fieldsAdd name, hypervisor.type, host.logical.cpu.cores
| summarize
    total_hosts = count(),
    virtual_hosts = countIf(isNotNull(hypervisor.type)),
    physical_hosts = countIf(isNull(hypervisor.type)),
    by: {hypervisor.type}
```

**Hypervisor Types:** `VMWARE`, `KVM`, `HYPERV`, `XEN`

### Cloud vs On-Premise Classification

Classify hosts by deployment type:

```dql
smartscapeNodes "HOST"
| fieldsAdd
    name,
    cloud.provider,
    aws.region,
    azure.location,
    hypervisor.type
| fieldsAdd deployment_type = if(
    isNotNull(cloud.provider), cloud.provider,
    else: if(isNotNull(hypervisor.type), "On-Premise Virtual", else: "On-Premise Physical")
  )
| summarize host_count = count(), by: {deployment_type}
| sort host_count desc
```

---

## Technology Inventory

### Technology Stack Overview

List all detected technologies:

```dql
smartscapeNodes "PROCESS"
| fieldsAdd process.software_technologies
| filter isNotNull(process.software_technologies) and arraySize(process.software_technologies) > 0
| expand tech = process.software_technologies
| fieldsAdd tech_type = tech[type]
| summarize process_count = count(), by: {tech_type}
| sort process_count desc
```

**Use Case:** Comprehensive technology stack visibility.

### Technology Versions

Track technology versions for each type:

```dql
smartscapeNodes "PROCESS"
| fieldsAdd process.software_technologies
| filter isNotNull(process.software_technologies)
| expand tech = process.software_technologies
| fieldsAdd tech_type = tech[type], tech_version = tech[version], tech_edition = tech[edition]
| filter isNotNull(tech_version) and tech_version != ""
| summarize process_count = count(), by: {tech_type, tech_version}
| sort tech_type, process_count desc
```

### Java Processes Distribution

Analyze Java deployment landscape:

```dql
smartscapeNodes "PROCESS"
| fieldsAdd process.software_technologies, dt.process_group.detected_name
| expand tech = process.software_technologies
| filter tech[type] == "JAVA"
| fieldsAdd java_version = tech[version]
| summarize process_count = count(), by: {java_version}
| sort process_count desc
```

### Database Technologies

Identify all database processes:

```dql
smartscapeNodes "PROCESS"
| fieldsAdd process.software_technologies, dt.process_group.detected_name
| expand tech = process.software_technologies
| filter in(tech[type], {"APACHE_CASSANDRA", "ELASTIC_SEARCH", "MONGO_DB", "MYSQL", "POSTGRESQL", "ORACLE_DB", "MSSQL", "REDIS", "COUCHDB"})
| fieldsAdd db_type = tech[type], db_version = tech[version]
| summarize
    process_count = count(),
    process_groups = countDistinct(dt.process_group.detected_name),
    by: {db_type, db_version}
| sort process_count desc
```

**Pattern:** Database deployment across infrastructure.

### Messaging and Streaming Technologies

List message queues and streaming platforms:

```dql
smartscapeNodes "PROCESS"
| fieldsAdd process.software_technologies, dt.process_group.detected_name
| expand tech = process.software_technologies
| filter in(tech[type], {"APACHE_KAFKA", "RABBIT_MQ", "AMQP", "ACTIVE_MQ"})
| fieldsAdd tech_type = tech[type], tech_version = tech[version]
| summarize process_count = count(), by: {tech_type, tech_version}
| sort process_count desc
```

### Web Servers and Proxies

Track web server and proxy technologies:

```dql
smartscapeNodes "PROCESS"
| fieldsAdd process.software_technologies, dt.process_group.detected_name
| expand tech = process.software_technologies
| filter in(tech[type], {"NGINX", "ENVOY", "APACHE_HTTP_SERVER", "IIS"})
| fieldsAdd tech_type = tech[type]
| summarize
    process_count = count(),
    process_groups = collectDistinct(dt.process_group.detected_name),
    by: {tech_type}
| sort process_count desc
```

### Application Runtime Technologies

Analyze runtime environments:

```dql
smartscapeNodes "PROCESS"
| fieldsAdd process.software_technologies
| expand tech = process.software_technologies
| filter in(tech[type], {"NODE_JS", "PYTHON", "DOTNET", "CLR", "GO", "RUBY"})
| fieldsAdd tech_type = tech[type], tech_version = tech[version]
| summarize process_count = count(), by: {tech_type}
| sort process_count desc
```

---

## Port Discovery

### Port Usage Overview

List all listening ports and process counts:

```dql
smartscapeNodes "PROCESS"
| fieldsAdd process.listen_ports, dt.process_group.detected_name
| filter isNotNull(process.listen_ports) and arraySize(process.listen_ports) > 0
| expand port = process.listen_ports
| summarize process_count = countDistinct(id), by: {port}
| sort toLong(port) asc
```

**Use Case:** Network security auditing and port inventory.

### Well-Known Port Analysis

Identify services on standard ports:

```dql
smartscapeNodes "PROCESS"
| fieldsAdd process.listen_ports, dt.process_group.detected_name
| filter isNotNull(process.listen_ports)
| expand port = process.listen_ports
| filter toLong(port) <= 1024
| summarize
    process_count = countDistinct(id),
    services = collectDistinct(dt.process_group.detected_name),
    by: {port}
| sort toLong(port) asc
```

**Standard Ports:**
- `22`: SSH
- `25`: SMTP
- `53`: DNS
- `80`: HTTP
- `443`: HTTPS
- `111`: RPC
- `3306`: MySQL
- `5432`: PostgreSQL
- `1521`: Oracle
- `1433`: MS SQL Server
- `9092`: Kafka
- `5672`: RabbitMQ

### Processes by Port

Find all processes listening on a specific port:

```dql
smartscapeNodes "PROCESS"
| fieldsAdd process.listen_ports, dt.process_group.detected_name, name
| expand port = process.listen_ports
| filter port == "443"
| limit 50
```

**Example:** Replace "443" with your target port.

### Port Conflict Detection

Identify ports with multiple different process types:

```dql
smartscapeNodes "PROCESS"
| fieldsAdd process.listen_ports, dt.process_group.detected_name
| expand port = process.listen_ports
| summarize
    process_count = countDistinct(id),
    process_types = countDistinct(dt.process_group.detected_name),
    services = collectDistinct(dt.process_group.detected_name),
    by: {port}
| filter process_types > 1
| sort process_types desc, process_count desc
```

**Alert:** Same port used by different process types may indicate misconfiguration.

### Web Services Port Mapping

Identify HTTP/HTTPS services:

```dql
smartscapeNodes "PROCESS"
| fieldsAdd process.listen_ports, dt.process_group.detected_name
| expand port = process.listen_ports
| filter in(port, {80, 443, 8080, 8443, 3000, 4000, 5000, 9090})
| summarize
    process_count = countDistinct(id),
    by: {port, dt.process_group.detected_name}
| sort toLong(port) asc
```

### Database Ports

Find all database services:

```dql
smartscapeNodes "PROCESS"
| fieldsAdd process.listen_ports, dt.process_group.detected_name
| expand port = process.listen_ports
| filter in(port, {3306, 5432, 1521, 1433, 27017, 6379, 9042, 7000})
| summarize
    process_count = countDistinct(id),
    by: {port, dt.process_group.detected_name}
| sort toLong(port) asc
```

**Port Mapping:**
- `3306`: MySQL
- `5432`: PostgreSQL
- `1521`: Oracle
- `1433`: MS SQL Server
- `27017`: MongoDB
- `6379`: Redis
- `9042`: Cassandra

---

## Multi-Cloud Hosts

### Cloud Provider Distribution

Categorize hosts by cloud provider:

```dql
smartscapeNodes "HOST"
| fieldsAdd name, cloud.provider, aws.region, azure.location
| fieldsAdd provider = if(
    isNotNull(cloud.provider), cloud.provider,
    else: "on-premise"
  )
| summarize host_count = count(), by: {provider}
| sort host_count desc
```

**Cloud Providers:** `aws`, `azure`, `gcp`, `alibaba_cloud`

### AWS Hosts by Region

Group AWS EC2 instances by region:

```dql
smartscapeNodes "HOST"
| filter isNotNull(aws.region)
| fieldsAdd name, aws.region, aws.availability_zone, aws.state
| summarize host_count = count(), by: {aws.region}
| sort host_count desc
```

**Common Regions:** `us-east-1`, `us-west-2`, `eu-west-1`, `ap-southeast-1`

### AWS Account Inventory

List hosts grouped by AWS account:

```dql
smartscapeNodes "HOST"
| filter isNotNull(aws.account.id)
| fieldsAdd name, aws.account.id, aws.region, aws.resource.type
| summarize
    host_count = count(),
    regions = collectDistinct(aws.region),
    by: {aws.account.id}
| sort host_count desc
```

**Use Case:** Multi-account AWS organization management.

### AWS Instance States

Monitor EC2 instance states:

```dql
smartscapeNodes "HOST"
| filter isNotNull(aws.state)
| fieldsAdd name, aws.state, aws.region, aws.resource.id
| summarize host_count = count(), by: {aws.state}
| sort host_count desc
```

**AWS States:** `running`, `stopped`, `stopping`, `terminated`, `pending`

### Azure Hosts by Location

Group Azure VMs by location:

```dql
smartscapeNodes "HOST"
| filter isNotNull(azure.location)
| fieldsAdd name, azure.location, azure.subscription, azure.status
| summarize host_count = count(), by: {azure.location}
| sort host_count desc
```

**Common Locations:** `eastus`, `westeurope`, `southeastasia`, `northeurope`

### Azure Resource Groups

Organize Azure VMs by resource group:

```dql
smartscapeNodes "HOST"
| filter isNotNull(azure.resource.group)
| fieldsAdd name, azure.resource.group, azure.location, azure.subscription
| summarize host_count = count(), by: {azure.resource.group}
| sort host_count desc
```

### Azure Subscriptions

Track Azure VMs by subscription:

```dql
smartscapeNodes "HOST"
| filter isNotNull(azure.subscription)
| fieldsAdd azure.subscription, azure.location
| summarize
    host_count = count(),
    locations = collectDistinct(azure.location),
    by: {azure.subscription}
| sort host_count desc
```

---

## Cost Attribution

### Cost Center Distribution

List all cost centers and their infrastructure footprint:

```dql
smartscapeNodes "HOST"
| fieldsAdd dt.cost.costcenter, dt.cost.product
| filter isNotNull(dt.cost.costcenter) or isNotNull(dt.cost.product)
| summarize host_count = count(), by: {dt.cost.costcenter, dt.cost.product}
| sort host_count desc
```

**Use Case:** Chargeback and cost allocation reporting.

### Cost Center by Cloud Provider

Analyze cost centers across cloud providers:

```dql
smartscapeNodes "HOST"
| fieldsAdd dt.cost.costcenter, cloud.provider
| filter isNotNull(dt.cost.costcenter)
| summarize host_count = count(), by: {dt.cost.costcenter, cloud.provider}
| sort dt.cost.costcenter, host_count desc
```

### Product Cost Breakdown

Group infrastructure costs by product:

```dql
smartscapeNodes "HOST"
| fieldsAdd dt.cost.product, dt.cost.costcenter
| filter isNotNull(dt.cost.product)
| summarize host_count = count(), by: {dt.cost.product, dt.cost.costcenter}
| sort dt.cost.product, host_count desc
```

### Resource Costs by Cost Center

Calculate resource consumption per cost center:

```dql
smartscapeNodes "HOST"
| fieldsAdd dt.cost.costcenter, host.logical.cpu.cores, host.physical.memory
| filter isNotNull(dt.cost.costcenter)
| fieldsAdd memory_gb = toDouble(host.physical.memory) / 1024 / 1024 / 1024
| summarize
    host_count = count(),
    total_cores = sum(toLong(host.logical.cpu.cores)),
    total_memory_gb = sum(memory_gb),
    by: {dt.cost.costcenter}
| fieldsAdd total_memory_gb = round(total_memory_gb, decimals: 0)
| sort total_cores desc
```

**Metric:** Physical resource allocation per cost center.

### Hosts Without Cost Attribution

Identify hosts missing cost metadata:

```dql
smartscapeNodes "HOST"
| fieldsAdd dt.cost.costcenter, dt.cost.product, name, cloud.provider
| filter isNull(dt.cost.costcenter) and isNull(dt.cost.product)
| summarize host_count = count(), by: {cloud.provider}
| sort host_count desc
```

**Action:** Tag unattributed infrastructure for cost tracking.

### Cost Attribution Coverage Rate

Calculate percentage of hosts with cost tags:

```dql
smartscapeNodes "HOST"
| fieldsAdd dt.cost.costcenter
| summarize
    total_hosts = count(),
    attributed_hosts = countIf(isNotNull(dt.cost.costcenter)),
    unattributed_hosts = countIf(isNull(dt.cost.costcenter))
| fieldsAdd coverage_rate = round((toDouble(attributed_hosts) / toDouble(total_hosts)) * 100, decimals: 1)
```

**Target:** >90% cost attribution coverage

---

## Tags and Metadata

### Important Notes
- Generic `tags` field is NOT populated in smartscape queries
- Use specific tag fields: `tags:azure[*]`, `tags:environment`
- Use custom metadata: `host.custom.metadata[*]`

### Azure Resource Tags

List all Azure-specific tags:

```dql
smartscapeNodes "HOST"
| filter isNotNull(azure.location)
| fieldsAdd `tags:azure`[dt_owner_team], `tags:azure`[dt_owner_capability]
| filter isNotNull(`tags:azure`[dt_owner_team])
| summarize host_count = count(), by: {`tags:azure`[dt_owner_team], `tags:azure`[dt_owner_capability]}
| sort host_count desc
```

**Azure Pattern:** Tags prefixed with `tags:azure` for resource organization.

### Azure Cost Tags

Analyze Azure cost allocation tags:

```dql
smartscapeNodes "HOST"
| filter isNotNull(azure.location)
| fieldsAdd
    capability = `tags:azure`[dt_cloudcost_capability],
    service = `tags:azure`[dt_cloudcost_service],
    cluster = `tags:azure`[dt_cloudcost_clustername]
| filter isNotNull(capability)
| summarize host_count = count(), by: {capability, service}
| sort host_count desc
```

**Use Case:** Cost allocation and chargeback reporting.

### Azure Owner Tags

Track resource ownership via Azure tags:

```dql
smartscapeNodes "HOST"
| filter isNotNull(azure.location)
| fieldsAdd
    owner_team = `tags:azure`[dt_owner_team],
    owner_email = `tags:azure`[dt_owner_email],
    owner_capability = `tags:azure`[dt_owner_capability]
| filter isNotNull(owner_team)
| summarize host_count = count(), by: {owner_team, owner_capability}
| sort host_count desc
```

### Custom Metadata - Operator Version

Track OneAgent operator versions:

```dql
smartscapeNodes "HOST"
| fieldsAdd operator_version = host.custom.metadata[OperatorVersion]
| filter isNotNull(operator_version)
| summarize host_count = count(), by: {operator_version}
| sort host_count desc
```

### Custom Metadata - Cluster Information

Query custom cluster metadata:

```dql
smartscapeNodes "HOST"
| fieldsAdd cluster = host.custom.metadata[Cluster]
| filter isNotNull(cluster)
| summarize host_count = count(), by: {cluster}
| sort host_count desc
```

---

## Data Quality

### AWS Hosts Missing Account IDs

Identify AWS hosts without account attribution:

```dql
smartscapeNodes "HOST"
| filter cloud.provider == "aws"
| fieldsAdd aws.account.id, aws.region, name
| summarize
    total_hosts = count(),
    missing_account = countIf(isNull(aws.account.id)),
    has_account = countIf(isNotNull(aws.account.id)),
    by: {aws.region}
| fieldsAdd missing_pct = round((toDouble(missing_account) / toDouble(total_hosts)) * 100, decimals: 1)
| sort missing_pct desc
```

**Data Quality Issue:** AWS hosts should always have account IDs.

### Hosts Without OS Information

Find hosts missing operating system details:

```dql
smartscapeNodes "HOST"
| fieldsAdd os.type, os.version, name
| filter isNull(os.type) or isNull(os.version)
| summarize host_count = count(), by: {os.type}
```

**Expected:** All hosts should report OS type and version.

### Kubernetes Nodes Without Cluster Info

Identify K8s nodes missing cluster metadata:

```dql
smartscapeNodes "HOST"
| fieldsAdd k8s.node.name, k8s.cluster.name, k8s.cluster.uid, name
| filter isNotNull(k8s.node.name)
| filter isNull(k8s.cluster.name) or isNull(k8s.cluster.uid)
| sort name
```

**Alert:** Kubernetes nodes must have cluster information.

### Processes Without Technology Detection

Find processes missing software technology metadata:

```dql
smartscapeNodes "PROCESS"
| fieldsAdd process.software_technologies, dt.process_group.detected_name
| filter isNull(process.software_technologies) or arraySize(process.software_technologies) == 0
| filter dt.process_group.detected_name != "Short-lived processes"
| summarize process_count = count(), by: {dt.process_group.detected_name}
| sort process_count desc
| limit 50
```

**Expected:** Most processes should have detected technologies.

### Hosts Missing Memory Information

Identify hosts without memory data:

```dql
smartscapeNodes "HOST"
| fieldsAdd host.physical.memory, name, cloud.provider
| filter isNull(host.physical.memory) or toLong(host.physical.memory) == 0
| summarize host_count = count(), by: {cloud.provider}
```

### Metadata Completeness Score

Calculate overall metadata completeness:

```dql
smartscapeNodes "HOST"
| fieldsAdd os.type, cloud.provider, host.logical.cpu.cores, host.physical.memory
| summarize
    total_hosts = count(),
    has_os = countIf(isNotNull(os.type)),
    has_cpu = countIf(isNotNull(host.logical.cpu.cores)),
    has_memory = countIf(isNotNull(host.physical.memory))
| fieldsAdd
    os_completeness = round((toDouble(has_os) / toDouble(total_hosts)) * 100, decimals: 1),
    cpu_completeness = round((toDouble(has_cpu) / toDouble(total_hosts)) * 100, decimals: 1),
    memory_completeness = round((toDouble(has_memory) / toDouble(total_hosts)) * 100, decimals: 1)
```

**Target:** >90% completeness for all fields

---

## Related Documentation

For host resource metrics, see [host-metrics.md](host-metrics.md).  
For process monitoring, see [process-monitoring.md](process-monitoring.md).  
For container and Kubernetes monitoring, see [container-monitoring.md](container-monitoring.md).
