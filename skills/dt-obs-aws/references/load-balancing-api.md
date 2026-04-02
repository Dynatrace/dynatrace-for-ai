# AWS Load Balancing & API Management

Monitor Application/Network Load Balancers, API Gateway, and CloudFront distributions.

## Table of Contents

- [Load Balancing Entity Types](#load-balancing-entity-types)
- [Load Balancer Topology Traversal](#load-balancer-topology-traversal)
- [Load Balancer Configuration](#load-balancer-configuration)
- [Security & Networking](#security--networking)
- [API Gateway](#api-gateway)
- [Cross-Service Analysis](#cross-service-analysis)

## Load Balancing Entity Types

All these types support the standard discovery pattern: `smartscapeNodes "<TYPE>" | fields name, aws.account.id, aws.region, ...`

| Entity type | Description |
|---|---|
| `AWS_ELASTICLOADBALANCINGV2_LOADBALANCER` | ALB, NLB, GLB (modern) |
| `AWS_ELASTICLOADBALANCING_LOADBALANCER` | Classic ELB |
| `AWS_ELASTICLOADBALANCINGV2_TARGETGROUP` | Target groups |
| `AWS_ELASTICLOADBALANCINGV2_LISTENER` | LB listeners |
| `AWS_APIGATEWAY_RESTAPI` | REST APIs |
| `AWS_APIGATEWAY_STAGE` | REST API stages |
| `AWS_APIGATEWAYV2_API` | HTTP/WebSocket APIs |
| `AWS_APIGATEWAYV2_STAGE` | V2 API stages |
| `AWS_CLOUDFRONT_DISTRIBUTION` | CloudFront CDN distributions |

## Load Balancer Topology Traversal

### Complete LB → Target Group → Instance Mapping

This is the most important query — maps internet-facing load balancers through target groups to backend instances:

```dql
smartscapeNodes "AWS_ELASTICLOADBALANCINGV2_LOADBALANCER"
| parse aws.object, "JSON:awsjson"
| fieldsAdd dnsName = awsjson[configuration][dnsName], scheme = awsjson[configuration][scheme]
| traverse "balanced_by", "AWS_ELASTICLOADBALANCINGV2_TARGETGROUP", direction:backward, fieldsKeep:{dnsName, id}
| fieldsAdd targetGroupName = aws.resource.name
| traverse "balances", "AWS_EC2_INSTANCE", fieldsKeep: {targetGroupName, id}
| fieldsAdd loadBalancerDnsName = dt.traverse.history[-2][dnsName],
            loadBalancerId = dt.traverse.history[-2][id],
            targetGroupId = dt.traverse.history[-1][id]
```

### Simpler Traversals

LB to target groups:

```dql
smartscapeNodes "AWS_ELASTICLOADBALANCINGV2_LOADBALANCER"
| traverse "balanced_by", "AWS_ELASTICLOADBALANCINGV2_TARGETGROUP", direction:backward
| fields name, aws.resource.id
```

Target groups to instances:

```dql
smartscapeNodes "AWS_ELASTICLOADBALANCINGV2_TARGETGROUP"
| traverse "balances", "AWS_EC2_INSTANCE"
| fields name, aws.resource.id, aws.availability_zone
```

## Load Balancer Configuration

Find internet-facing load balancers:

```dql
smartscapeNodes "AWS_ELASTICLOADBALANCINGV2_LOADBALANCER"
| parse aws.object, "JSON:awsjson"
| fieldsAdd scheme = awsjson[configuration][scheme], dnsName = awsjson[configuration][dnsName]
| filter scheme == "internet-facing"
| fields name, dnsName, aws.resource.id, aws.vpc.id
```

Check multi-AZ distribution:

```dql
smartscapeNodes "AWS_ELASTICLOADBALANCINGV2_LOADBALANCER"
| fields name, aws.resource.id, aws.availability_zone
| expand aws.availability_zone
```

## Security & Networking

List security groups attached to load balancers:

```dql
smartscapeNodes "AWS_ELASTICLOADBALANCINGV2_LOADBALANCER"
| fields name, aws.resource.id, aws.security_group.id
| expand aws.security_group.id
```

Filter LBs by VPC:

```dql
smartscapeNodes "AWS_ELASTICLOADBALANCINGV2_LOADBALANCER"
| filter aws.vpc.id == "<VPC_ID>"
| fields name, aws.resource.id, aws.subnet.id
```

## API Gateway

Count APIs across regions by type:

```dql
smartscapeNodes "AWS_APIGATEWAY_RESTAPI", "AWS_APIGATEWAYV2_API"
| summarize api_count = count(), by: {type, aws.region}
| sort api_count desc
```

## Cross-Service Analysis

Count all load balancers by type and region:

```dql
smartscapeNodes "AWS_ELASTICLOADBALANCINGV2_LOADBALANCER", "AWS_ELASTICLOADBALANCING_LOADBALANCER"
| summarize lb_count = count(), by: {type, aws.region}
| sort lb_count desc
```
