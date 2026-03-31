# AWS Events Reference

Event queries for problem timeline analysis. Use these during incident investigation to determine what changed before or during a problem on an AWS resource.

## Placeholder Reference

| Placeholder | Description |
|---|---|
| `<PROBLEM_START>` | Problem start timestamp (e.g., `now()-2h`) |
| `<PROBLEM_END>` | Problem end timestamp (e.g., `now()`) |
| `<ROOT_CAUSE_ENTITY_ID>` | Dynatrace entity ID of the affected resource (e.g., `AWS_EC2_INSTANCE-ABC123`) |
| `<AWS_INSTANCE_ID>` | AWS resource ID of the affected resource (e.g., `i-0abc1234def56789`) |

---

## Auto Scaling Events

List recent Auto Scaling activity. Run this first during any EC2 instance problem to detect scale-in/scale-out events, lifecycle hooks, or capacity changes that may have caused or contributed to the issue.

```dql
fetch events
| filter source == "aws.autoscaling"
| fields timestamp, event.type, event.name, data
| sort timestamp desc
| limit 50
```

**Note:** This query returns the most recent 50 events globally. For incident-scoped analysis, add a time range:

```dql-template
fetch events, from: <PROBLEM_START>, to: <PROBLEM_END>
| filter source == "aws.autoscaling"
| fields timestamp, event.type, event.name, data
| sort timestamp desc
```

---

## AWS Health Events

Query for AWS Health service events affecting the specific resource. AWS Health events indicate service disruptions, scheduled maintenance, or account-level notifications from AWS.

```dql-template
fetch events, from: <PROBLEM_START - 1h>, to: <PROBLEM_END + 1h>
| filter source == "aws.health"
| filter dt.smartscape_source.id == toSmartscapeId("<ROOT_CAUSE_ENTITY_ID>")
| fieldsAdd event.description = jsonData[`eventDescription`][0][`latestDescription`]
| fieldsAdd event.name = jsonData[`eventTypeCode`]
| fieldsAdd event.category = jsonData[actionability]
| fieldsAdd affected_entity_ids = dt.smartscape_source.id
| fields timestamp, event.name, event.description, event.category, affected_entity_ids
| sort timestamp desc
```

**What to look for:**

- `event.category != "INFORMATIONAL"` — active service disruption from AWS or planned maintenance that may be impacting your resource

---

## CloudFormation Events

Check for recent CloudFormation stack deployments or changes. Infrastructure changes via CloudFormation are a common cause of problems — correlate stack events with the problem timeline.

```dql-template
fetch events, from: <PROBLEM_START - 1h>, to: <PROBLEM_END + 1h>
| filter source == "aws.cloudformation"
| parse data, "JSON:jsonData"
| fieldsAdd event.name = jsonData[eventName]
| fieldsAdd event.errorCode = jsonData[errorCode]
| fieldsAdd event.errorMessage = jsonData[errorMessage]
| fieldsAdd event.status = jsonData[`status-details`][status]
| fields jsonData, event.name, event.errorCode, event.status
| limit 20
```

Check for CloudFormation events related to the specific resource:

```dql
fetch events
| filter source == "aws.cloudformation"
| parse data, "JSON:jsonData"
| fieldsAdd event.name = jsonData[eventName]
| fieldsAdd event.errorCode = jsonData[errorCode]
| fieldsAdd event.errorMessage = jsonData[errorMessage]
| fieldsAdd event.status = jsonData[`status-details`][status]
| filter jsonData[`logical-resource-id`] == "<AWS_RESOURCE_NAME>"
| fields jsonData, event.name, event.errorCode, event.status, id, data
| limit 20
```

**What to look for:**

- Stack updates that completed shortly before the problem started
- Failed stack operations that may have left resources in a degraded state
- Resource replacements (e.g., instance replaced due to a launch template change)
