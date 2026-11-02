# OpenPipeline API Reference — Python SDK

Use the Dynatrace Python SDK when dtctl is not available or does not cover a needed feature.
All examples below use `PlatformClient` with a platform token.

```python
import os
from dt import PlatformClient

client = PlatformClient(
    os.environ["DT_ENV_URL"],          # e.g. https://<your-tenant>.apps.dynatrace.com
    platform_token=os.environ["DT_PLATFORM_TOKEN"],
)
```

Prerequisites: `python -c "import dt"` succeeds and `$DT_PLATFORM_TOKEN` / `$DT_ENV_URL` are set. If either is missing, do not install the SDK, mint a token, or ask for the token in conversation — tell the user what is missing instead.

## Translate a classic pipeline

Equivalent to `dtctl translate classic-pipelines`. Returns the translated OpenPipeline artifact
directly (no `-A` envelope wrapper):

```python
from dt.platform.openpipeline.v1.models import ClassicPipelineTranslationResult

result: ClassicPipelineTranslationResult = (
    client.openpipeline.v1.classic_pipelines.translate.get(
        configuration="logs",
        include_sample_data=True,
        skip_disabled_rules=False,
        skip_builtin_processing_rules=True,
    )
)
```

Use `configuration="bizevents"` for Business events. Adjust `include_sample_data`,
`skip_disabled_rules`, and `skip_builtin_processing_rules` to match the flags confirmed with the
user.

## List available technology bundles

Returns all technology bundles available for a given configuration, including their `technologyId`
values:

```python
bundles = list(
    client.openpipeline.v1.technologies.list(configurations_filter="logs")
)
```

## Translate a classic LQL matcher to DQL

Useful when a processor placeholder has an untranslated `matcher`:

```python
from dt.platform.openpipeline.v1.models import MatcherRequest

response: MatcherRequest = client.openpipeline.v1.matcher.lql_to_dql.create(
    body=MatcherRequest(query="<classic LQL matcher>"),
)
translated_dql = response.query
```

## Verify a DQL matcher

Checks whether a DQL matcher expression is valid before using it in a processor:

```python
from dt.platform.openpipeline.v1.models import MatcherVerifyRequest, VerifyResponse

response: VerifyResponse = client.openpipeline.v1.matcher.verify.create(
    body=MatcherVerifyRequest(
        query="<DQL matcher expression>",
        configuration_id="logs",
        context="processing",
    ),
)
print(response.valid)
```

Body fields:

- **`query`** — the DQL matcher expression to validate.
- **`configuration_id`** — the scope being upgraded: `"logs"` or `"bizevents"`.
- **`context`** — the pipeline stage the matcher belongs to, using the processor context name:
  `"processing"`, `"securityContext"`, `"metricExtraction"`, `"davis"`, or `"bucketAssignment"`.
  Note the bucket-assignment stage is keyed `storage` in the artifact but its `context` value here
  is `"bucketAssignment"` (not `"storage"`).

## Verify a DQL processor script

Checks whether a rewritten DQL processor `script` is valid before inserting it into a processor:

```python
from dt.platform.openpipeline.v1.models import DqlProcessorVerifyRequest, VerifyResponse

response: VerifyResponse = client.openpipeline.v1.dql_processor.verify.create(
    body=DqlProcessorVerifyRequest(
        script="<DQL processor script>",
        configuration_id="logs",
    ),
)
print(response.valid)
```

Body fields:

- **`script`** — the DQL processor script to validate.
- **`configuration_id`** — the scope being upgraded: `"logs"` or `"bizevents"`.

## Preview processor output

Runs a processor definition against provided sample data and returns the transformed record.
Useful for validating a rewritten DQL processor before deploying.

```python
from dt.platform.openpipeline.v1.models import (
    DqlProcessor,
    PreviewProcessorEnvelope,
    PreviewProcessorResult,
)

result: PreviewProcessorResult = client.openpipeline.v1.preview.processor.create(
    body=PreviewProcessorEnvelope(
        config_id="logs",
        processor=DqlProcessor(
            id="<processor id>",
            enabled=True,
            description="<description>",
            matcher="<DQL matcher>",
            sample_data="<sample records>",
            dql_script="<DQL script>",
        ),
    )
)
print(result.results[0].matched, result.results[0].record)
```

Body fields:

- **`processor.sample_data`** — a JSON string holding the record(s) to run through the processor.
- **`processor.dql_script`** — the processor's DQL as a flat string (note this differs from the artifact's nested `dql.script`).
- **`config_id`** — the scope being previewed: `logs` or `bizevents`.
