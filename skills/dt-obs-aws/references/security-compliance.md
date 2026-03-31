# AWS Security & Compliance

Monitor security configurations and compliance across AWS resources.

## Table of Contents

- [Security Group Rule Analysis](#security-group-rule-analysis)
- [Security Group Blast Radius](#security-group-blast-radius)
- [S3 Public Access & Encryption](#s3-public-access--encryption)
- [EBS Volume Encryption](#ebs-volume-encryption)
- [IAM & Key Management](#iam--key-management)
- [Public Access Detection](#public-access-detection)
- [Network Security](#network-security)

## Security Group Rule Analysis

Security group rules are stored in `aws.object` as `ipPermissions` (ingress) and `ipPermissionsEgress` (egress) arrays. Convert these to strings with `toString()` and use `contains()` to search for risky patterns.

Find security groups with **any ingress rule open to the internet** (0.0.0.0/0 or ::/0):

```dql
smartscapeNodes "AWS_EC2_SECURITYGROUP"
| parse aws.object, "JSON:awsjson"
| fieldsAdd
    ipPermissions = toString(awsjson[configuration][ipPermissions]),
    groupName = awsjson[configuration][groupName]
| filter contains(ipPermissions, "0.0.0.0/0") or contains(ipPermissions, "::/0")
| fields groupName, aws.resource.id, aws.vpc.id, ipPermissions
```

Count open security groups per VPC:

```dql
smartscapeNodes "AWS_EC2_SECURITYGROUP"
| parse aws.object, "JSON:awsjson"
| fieldsAdd ipPermissions = toString(awsjson[configuration][ipPermissions])
| filter contains(ipPermissions, "0.0.0.0/0") or contains(ipPermissions, "::/0")
| summarize open_sg_count = count(), by: {aws.vpc.id}
```

Find security groups that are **wide open** — all traffic allowed from the internet (protocol `-1` or port range 0-65535 combined with 0.0.0.0/0):

```dql
smartscapeNodes "AWS_EC2_SECURITYGROUP"
| parse aws.object, "JSON:awsjson"
| fieldsAdd
    ipPermissions = toString(awsjson[configuration][ipPermissions]),
    groupName = awsjson[configuration][groupName]
| filter contains(ipPermissions, "0.0.0.0/0")
| filter contains(ipPermissions, "\"ipProtocol\":\"-1\"")
    or contains(ipPermissions, "\"fromPort\":0")
| fields groupName, aws.resource.id, aws.vpc.id, ipPermissions
```

Audit **egress rules** — count security groups with unrestricted outbound traffic per VPC:

```dql
smartscapeNodes "AWS_EC2_SECURITYGROUP"
| parse aws.object, "JSON:awsjson"
| fieldsAdd
    ipPermissionsEgress = toString(awsjson[configuration][ipPermissionsEgress]),
    groupName = awsjson[configuration][groupName]
| filter contains(ipPermissionsEgress, "0.0.0.0/0")
| summarize egress_open_count = count(), by: {aws.vpc.id}
```

> **Tip:** The `ipPermissions` field is a JSON array. To detect specific open ports (e.g., SSH 22, RDP 3389, PostgreSQL 5432), combine the 0.0.0.0/0 filter with a port-specific string match: `contains(ipPermissions, "\"fromPort\":22")`. For a full list of risky ports, repeat with `3389` (RDP), `3306` (MySQL), `5432` (PostgreSQL), `6379` (Redis), `27017` (MongoDB).

## Security Group Blast Radius

Find security groups with the most instances (blast radius):

```dql
smartscapeNodes "AWS_EC2_INSTANCE"
| traverse "uses", "AWS_EC2_SECURITYGROUP"
| summarize instance_count = count(), by: {aws.resource.name, aws.vpc.id}
| sort instance_count desc
| limit 20
```

Find instances with multiple security groups:

```dql
smartscapeNodes "AWS_EC2_INSTANCE"
| parse aws.object, "JSON:awsjson"
| fieldsAdd sg_count = arraySize(awsjson[configuration][securityGroups])
| filter sg_count > 1
| fields name, aws.resource.id, aws.security_group.id, sg_count
| sort sg_count desc
```

List security groups (for finding unused ones, cross-reference with instance usage):

```dql
smartscapeNodes "AWS_EC2_SECURITYGROUP"
| fields name, aws.resource.id, aws.vpc.id
| limit 100
```

## S3 Public Access & Encryption

S3 bucket security configuration is in `supplementary_configuration` within `aws.object`. The four `publicAccessBlockConfiguration` booleans should all be `true` for a properly secured bucket.

Audit **Public Access Block** settings across all S3 buckets:

```dql
smartscapeNodes "AWS_S3_BUCKET"
| parse aws.object, "JSON:awsjson"
| fieldsAdd
    blockPublicAcls = awsjson[supplementary_configuration][publicAccessBlockConfiguration][blockPublicAcls],
    ignorePublicAcls = awsjson[supplementary_configuration][publicAccessBlockConfiguration][ignorePublicAcls],
    blockPublicPolicy = awsjson[supplementary_configuration][publicAccessBlockConfiguration][blockPublicPolicy],
    restrictPublicBuckets = awsjson[supplementary_configuration][publicAccessBlockConfiguration][restrictPublicBuckets]
| fields name, aws.account.id, aws.region,
         blockPublicAcls, ignorePublicAcls, blockPublicPolicy, restrictPublicBuckets
```

Find S3 buckets **missing any Public Access Block** setting (potential public exposure):

```dql
smartscapeNodes "AWS_S3_BUCKET"
| parse aws.object, "JSON:awsjson"
| fieldsAdd
    blockPublicAcls = awsjson[supplementary_configuration][publicAccessBlockConfiguration][blockPublicAcls],
    ignorePublicAcls = awsjson[supplementary_configuration][publicAccessBlockConfiguration][ignorePublicAcls],
    blockPublicPolicy = awsjson[supplementary_configuration][publicAccessBlockConfiguration][blockPublicPolicy],
    restrictPublicBuckets = awsjson[supplementary_configuration][publicAccessBlockConfiguration][restrictPublicBuckets]
| filter blockPublicAcls != true
    or ignorePublicAcls != true
    or blockPublicPolicy != true
    or restrictPublicBuckets != true
| fields name, aws.account.id, aws.region,
         blockPublicAcls, ignorePublicAcls, blockPublicPolicy, restrictPublicBuckets
```

Find S3 buckets with **no Public Access Block configuration** at all:

```dql
smartscapeNodes "AWS_S3_BUCKET"
| parse aws.object, "JSON:awsjson"
| fieldsAdd pubBlock = awsjson[supplementary_configuration][publicAccessBlockConfiguration]
| filter isNull(pubBlock)
| fields name, aws.account.id, aws.region
```

Detect S3 buckets with **public ACL grants** (AllUsers or AuthenticatedUsers):

```dql
smartscapeNodes "AWS_S3_BUCKET"
| parse aws.object, "JSON:awsjson"
| fieldsAdd acl = toString(awsjson[supplementary_configuration][accessControlList][grants])
| filter contains(acl, "AllUsers") or contains(acl, "AuthenticatedUsers")
| fields name, aws.account.id, aws.region, acl
```

Summarize S3 **security posture** — encryption algorithm and public access block status:

```dql
smartscapeNodes "AWS_S3_BUCKET"
| parse aws.object, "JSON:awsjson"
| fieldsAdd
    blockPublicAcls = awsjson[supplementary_configuration][publicAccessBlockConfiguration][blockPublicAcls],
    sseAlgorithm = awsjson[supplementary_configuration][serverSideEncryptionConfiguration][rules][0][applyServerSideEncryptionByDefault][sseAlgorithm]
| summarize bucket_count = count(), by: {blockPublicAcls, sseAlgorithm}
```

## EBS Volume Encryption

Summarize EBS volume encryption status by volume type:

```dql
smartscapeNodes "AWS_EC2_VOLUME"
| parse aws.object, "JSON:awsjson"
| fieldsAdd
    encrypted = awsjson[configuration][encrypted],
    volumeType = awsjson[configuration][volumeType],
    state = awsjson[configuration][state]
| summarize volume_count = count(), by: {encrypted, volumeType}
| sort volume_count desc
```

List **unencrypted EBS volumes** with size and location:

```dql
smartscapeNodes "AWS_EC2_VOLUME"
| parse aws.object, "JSON:awsjson"
| fieldsAdd
    encrypted = awsjson[configuration][encrypted],
    volumeType = awsjson[configuration][volumeType],
    size = awsjson[configuration][size]
| filter encrypted != true
| fields name, aws.resource.id, aws.availability_zone, volumeType, size
```

## IAM & Key Management

> **Note:** IAM analysis in Dynatrace is limited to role-level metadata. For policy-level analysis (overly permissive policies, unused access keys, MFA status), use AWS IAM Access Analyzer or Security Hub.

Identify IAM roles used by Lambda functions:

```dql
smartscapeNodes "AWS_IAM_ROLE"
| parse aws.object, "JSON:awsjson"
| fieldsAdd assumeRolePolicyDocument = awsjson[configuration][assumeRolePolicyDocument]
| filter contains(toString(assumeRolePolicyDocument), "lambda")
| fields name, aws.account.id
```

Monitor KMS encryption key states:

```dql
smartscapeNodes "AWS_KMS_KEY"
| parse aws.object, "JSON:awsjson"
| fieldsAdd keyState = awsjson[configuration][keyState],
            keyUsage = awsjson[configuration][keyUsage]
| summarize key_count = count(), by: {keyState, keyUsage}
| sort key_count desc
```

Check RDS database encryption:

```dql
smartscapeNodes "AWS_RDS_DBINSTANCE"
| parse aws.object, "JSON:awsjson"
| fieldsAdd storageEncrypted = awsjson[configuration][storageEncrypted]
| summarize db_count = count(), by: {storageEncrypted, aws.region}
```

Count IAM roles by account:

```dql
smartscapeNodes "AWS_IAM_ROLE"
| summarize role_count = count(), by: {aws.account.id}
| sort role_count desc
```

## Public Access Detection

Find publicly accessible RDS databases:

```dql
smartscapeNodes "AWS_RDS_DBINSTANCE"
| parse aws.object, "JSON:awsjson"
| fieldsAdd publiclyAccessible = awsjson[configuration][publiclyAccessible]
| filter publiclyAccessible == true
| fields name, aws.resource.id, aws.vpc.id, aws.account.id
```

Identify internet-facing load balancers:

```dql
smartscapeNodes "AWS_ELASTICLOADBALANCINGV2_LOADBALANCER"
| parse aws.object, "JSON:awsjson"
| fieldsAdd scheme = awsjson[configuration][scheme]
| filter scheme == "internet-facing"
| fields name, aws.resource.id, aws.vpc.id, aws.region
```

Audit VPC attachment coverage across Lambda functions — use to verify functions requiring private connectivity have VPC configured. For per-function networking detail, see `references/serverless-containers.md`.

```dql
smartscapeNodes "AWS_LAMBDA_FUNCTION"
| filter isNotNull(aws.vpc.id)
| fields name, aws.resource.id, aws.vpc.id, aws.security_group.id
| summarize function_count = count(), by: {aws.vpc.id}
```

## Network Security

List SSL/TLS certificates:

```dql
smartscapeNodes "AWS_ACM_CERTIFICATE"
| fields name, aws.account.id, aws.region
| summarize cert_count = count(), by: {aws.region}
```

Analyze VPC endpoint private connectivity:

```dql
smartscapeNodes "AWS_EC2_VPCENDPOINT"
| parse aws.object, "JSON:awsjson"
| fieldsAdd serviceName = awsjson[configuration][serviceName]
| summarize endpoint_count = count(), by: {serviceName, aws.vpc.id}
| sort endpoint_count desc
```

List Route53 hosted zones:

```dql
smartscapeNodes "AWS_ROUTE53_HOSTEDZONE"
| summarize zone_count = count(), by: {aws.account.id}
```
