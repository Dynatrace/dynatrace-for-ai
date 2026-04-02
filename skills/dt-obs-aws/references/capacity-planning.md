# AWS Capacity Planning

Analyze resource capacity and plan for growth.

## Table of Contents

- [Compute Capacity](#compute-capacity)
- [Network Capacity](#network-capacity)
- [Container & Serverless Capacity](#container--serverless-capacity)
- [Database & Storage Capacity](#database--storage-capacity)
- [Infrastructure Capacity](#infrastructure-capacity)

## Compute Capacity

Instance type distribution across regions:

```dql
smartscapeNodes "AWS_EC2_INSTANCE"
| parse aws.object, "JSON:awsjson"
| fieldsAdd instanceType = awsjson[configuration][instanceType],
            state = awsjson[configuration][state][name]
| summarize instance_count = count(), by: {instanceType, state, aws.region}
| sort instance_count desc
```

Auto Scaling group capacity and headroom:

```dql
smartscapeNodes "AWS_AUTOSCALING_AUTOSCALINGGROUP"
| parse aws.object, "JSON:awsjson"
| fieldsAdd minSize = awsjson[configuration][minSize],
            maxSize = awsjson[configuration][maxSize],
            desiredCapacity = awsjson[configuration][desiredCapacity]
| fields name, minSize, maxSize, desiredCapacity, aws.region
| sort desiredCapacity desc
```

## Network Capacity

Subnet IP address utilization (critical for capacity planning):

```dql
smartscapeNodes "AWS_EC2_SUBNET"
| parse aws.object, "JSON:awsjson"
| fieldsAdd availableIpCount = awsjson[configuration][availableIpAddressCount],
            cidrBlock = awsjson[configuration][cidrBlock]
| fields name, cidrBlock, availableIpCount, aws.vpc.id, aws.availability_zone
| sort availableIpCount asc
```

Network interface usage by type:

```dql
smartscapeNodes "AWS_EC2_NETWORKINTERFACE"
| parse aws.object, "JSON:awsjson"
| fieldsAdd interfaceType = awsjson[configuration][interfaceType],
            status = awsjson[configuration][status]
| summarize eni_count = count(), by: {interfaceType, status}
| sort eni_count desc
```

Route tables per VPC:

```dql
smartscapeNodes "AWS_EC2_ROUTETABLE"
| summarize route_table_count = count(), by: {aws.vpc.id, aws.region}
| sort route_table_count desc
```

## Container & Serverless Capacity

ECS service desired vs running counts:

```dql
smartscapeNodes "AWS_ECS_SERVICE"
| parse aws.object, "JSON:awsjson"
| fieldsAdd desiredCount = awsjson[configuration][desiredCount],
            runningCount = awsjson[configuration][runningCount]
| fields name, desiredCount, runningCount, aws.region
```

Lambda function memory allocations:

```dql
smartscapeNodes "AWS_LAMBDA_FUNCTION"
| parse aws.object, "JSON:awsjson"
| fieldsAdd memory = awsjson[configuration][memorySize]
| summarize function_count = count(), by: {memory, aws.region}
| sort memory desc
```

EKS node groups, ECR repositories, and launch templates can be counted with the standard discovery pattern using their respective entity types: `AWS_EKS_NODEGROUP`, `AWS_ECR_REPOSITORY`, `AWS_EC2_LAUNCHTEMPLATE`.

## Database & Storage Capacity

RDS storage type distribution:

```dql
smartscapeNodes "AWS_RDS_DBINSTANCE"
| parse aws.object, "JSON:awsjson"
| fieldsAdd storageType = awsjson[configuration][storageType]
| summarize db_count = count(), by: {storageType, aws.region}
| sort db_count desc
```

## Infrastructure Capacity

Transit gateways for multi-VPC connectivity:

```dql
smartscapeNodes "AWS_EC2_TRANSITGATEWAY"
| fields name, aws.account.id, aws.region, aws.resource.id
```
