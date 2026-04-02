# AWS VPC Networking & Security

Monitor and troubleshoot AWS VPC network infrastructure, security groups, and connectivity.

## Table of Contents

- [VPC Discovery](#vpc-discovery)
- [Security Group Analysis](#security-group-analysis)
- [Subnet & Instance Distribution](#subnet--instance-distribution)
- [Internet-Facing Resources](#internet-facing-resources)
- [Network Infrastructure](#network-infrastructure)
- [Availability Zone Distribution](#availability-zone-distribution)

## VPC Discovery

List all VPCs:

```dql
smartscapeNodes "AWS_EC2_VPC"
| fields name, aws.account.id, aws.region, aws.resource.id, aws.vpc.id
```

Get all resources in a VPC grouped by type:

```dql
smartscapeNodes "AWS_*"
| filter aws.vpc.id == "<VPC_ID>"
| summarize resource_count = count(), by: {type, aws.subnet.id}
| sort resource_count desc
```

## Security Group Analysis

Find all instances and their security groups:

```dql
smartscapeNodes "AWS_EC2_INSTANCE"
| fields name, aws.resource.id, aws.vpc.id, aws.security_group.id
| expand aws.security_group.id
```

Locate all resources using a specific security group:

```dql
smartscapeNodes "AWS_EC2_INSTANCE"
| filter contains(aws.security_group.id, "<EC2_SECURITY_GROUP>")
| fields name, aws.resource.id, aws.vpc.id, aws.subnet.id
```

Find instances with multiple security groups:

```dql
smartscapeNodes "AWS_EC2_INSTANCE"
| parse aws.object, "JSON:awsjson"
| fieldsAdd sg_count = arraySize(awsjson[configuration][securityGroups])
| filter sg_count > 0
| fields name, aws.resource.id, aws.security_group.id, sg_count
| sort sg_count desc
```

## Subnet & Instance Distribution

Count instances per subnet:

```dql
smartscapeNodes "AWS_EC2_INSTANCE"
| summarize instance_count = count(), by: {aws.vpc.id, aws.subnet.id}
| sort instance_count desc
```

Find EC2 instances in a specific VPC:

```dql
smartscapeNodes "AWS_EC2_INSTANCE"
| filter aws.vpc.id == "<VPC_ID>"
| fields name, aws.resource.id, aws.subnet.id, aws.availability_zone
```

## Internet-Facing Resources

Locate instances with public IPs:

```dql
smartscapeNodes "AWS_EC2_INSTANCE"
| parse aws.object, "JSON:awsjson"
| fieldsAdd publicIp = awsjson[configuration][networkInterfaces][0][association][publicIp]
| filter isNotNull(publicIp)
| fields name, aws.resource.id, publicIp, aws.vpc.id
```

## Network Infrastructure

List network interfaces:

```dql
smartscapeNodes "AWS_EC2_NETWORKINTERFACE"
| fields name, aws.resource.id, aws.vpc.id, aws.subnet.id, aws.security_group.id
```

NAT gateways by VPC:

```dql
smartscapeNodes "AWS_EC2_NATGATEWAY"
| fields name, aws.resource.id, aws.vpc.id, aws.subnet.id
| summarize nat_count = count(), by: {aws.vpc.id}
```

VPN gateways:

```dql
smartscapeNodes "AWS_EC2_VPNGATEWAY"
| fields name, aws.resource.id, aws.vpc.id, aws.region
```

VPC endpoints:

```dql
smartscapeNodes "AWS_EC2_VPCENDPOINT"
| fields name, aws.resource.id, aws.vpc.id, aws.subnet.id
```

VPC peering connections:

```dql
smartscapeNodes "AWS_EC2_VPCPEERINGCONNECTION"
| fields name, aws.resource.id, aws.vpc.id, aws.region
```

## Availability Zone Distribution

View instance distribution across AZs:

```dql
smartscapeNodes "AWS_EC2_INSTANCE"
| summarize
    instance_count = count(),
    by: {aws.region, aws.availability_zone, aws.vpc.id}
| sort aws.region, instance_count desc
```
