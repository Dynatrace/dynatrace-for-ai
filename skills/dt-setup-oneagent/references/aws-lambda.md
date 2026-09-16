# AWS Lambda — OneAgent layer and environment variables

Layer ARN discovery, the environment variables the layer requires, attaching to an existing function, creating one, Secrets Manager for the runtime token, uninstall and verification.

Part of the `dt-setup-oneagent` skill — see [../SKILL.md](../SKILL.md) for the hard rules, URL normalization and token guidance that apply to every target.

---

The Dynatrace OneAgent for Lambda is published as a Lambda **layer**. The layer plus a small set of environment variables instruments any function created with a supported runtime.

### Supported runtimes and Dynatrace API techtypes

| AWS Lambda runtime              | Dynatrace API `techtype`  |
|---------------------------------|---------------------------|
| `python*`                       | `python`                  |
| `nodejs*`                       | `nodejs`                  |
| `java*`                         | `java`                    |
| `provided*` (custom) / `go*`    | `go` ← assumed for `provided*`; only correct for Go custom runtimes |
| `dotnet*`                       | `DotNet`                  |

For `provided.al2023` Rust/C++/custom runtimes, do **not** assume Go — set `DT_LAYER_ARN` to the correct layer for the language manually.

### Layer ARN auto-discovery

Layer ARNs are published from different Dynatrace-owned AWS accounts depending on the tenant, and are not available in every AWS region. Never hard-code an account number or copy an ARN from another environment — resolve it per tenant, region and architecture. The definitive lookup is:

```
GET ${DT_ENV_URL_NORMALIZED}/api/v1/deployment/lambda/layer
    ?techtype=<python|nodejs|java|go|DotNet>
    &region=<aws-region>
    &arch=<x86|arm>
    &withCollector=<included|excluded>
Header: Authorization: Api-Token ${DT_API_TOKEN}   # dt0c01.… access token (InstallerDownload)
        Authorization: Bearer ${DT_API_TOKEN}      # dt0s16.… platform token
```

Response is JSON containing an `arns` array. Pick the first ARN.

**Do not** use `aws lambda list-layer-versions --layer-name 'Dynatrace_OneAgent_<Lang>'`: it queries the *caller's* AWS account and silently returns empty when the layer lives in a Dynatrace-owned account (the common case).

### Environment variables the layer requires

| Variable                                                  | Always required | When                              |
|-----------------------------------------------------------|-----------------|-----------------------------------|
| `AWS_LAMBDA_EXEC_WRAPPER=/opt/dynatrace`                  | yes             | Layer entrypoint hook             |
| `DT_TENANT=<tenant id>`                                   | yes             |                                   |
| `DT_CONNECTION_BASE_URL=https://<id>.<host>`              | yes             | **No trailing `/api`** — verified against multiple SaaS tenants. |
| `DT_CLUSTER_ID=<id-or-empty>`                             | yes             | Empty string is fine for SaaS     |
| `DT_CONNECTION_AUTH_TOKEN=<token>`                        | yes (one of these) | Inlined token form — stored in plaintext on the function and readable by any principal holding `lambda:GetFunctionConfiguration`. Prefer the Secrets Manager form below. |
| `DT_CONNECTION_AUTH_TOKEN_SECRETS_MANAGER_ARN=<arn>`      | yes (one of these) | Secrets Manager form           |
| `DT_LOG_COLLECTION_AUTH_TOKEN` / `…_SECRETS_MANAGER_ARN`  | yes for `with_collector` layers | Otherwise the bundled OpenTelemetry collector dies at startup with `exporters::dynatracelogs: api_token is required` |

### CLI attach (existing function)

> ⚠️ **`--environment` and `--layers` both REPLACE, they don't merge.** Anything you omit is deleted from the function. Sending only the `DT_*` variables wipes the application's own configuration (database URLs, feature flags, API keys); passing only the Dynatrace layer drops every other layer. Always read the current values and merge first.

**Step 1 — snapshot the current config** (this is also your rollback, and it may contain a token if the function was already instrumented, so keep it `0600` and out of git):

```bash
umask 077
aws lambda get-function-configuration \
  --region "$LAMBDA_REGION" --function-name "$LAMBDA_FN" \
  > "./${LAMBDA_FN}.config.backup.json"
```

**Step 2 — build the merged environment** (existing variables first, Dynatrace values win on conflict, so a rotated token is refreshed):

```bash
MERGED_ENV="$(aws lambda get-function-configuration \
  --region "$LAMBDA_REGION" --function-name "$LAMBDA_FN" \
  --query 'Environment.Variables' --output json \
  | jq -c --arg tenant "<id>" \
         --arg baseurl "https://<id>.<host>" '
      (. // {}) + {
        "AWS_LAMBDA_EXEC_WRAPPER": "/opt/dynatrace",
        "DT_TENANT": $tenant,
        "DT_CONNECTION_BASE_URL": $baseurl,
        "DT_CONNECTION_AUTH_TOKEN": env.DT_API_TOKEN
      } | {Variables: .}')"
```

`env.DT_API_TOKEN` reads the token from the environment rather than `--arg`, which would place it in jq's own command line where `ps` can read it.

Add `DT_CLUSTER_ID` only if your tenant needs it, and `DT_LOG_COLLECTION_AUTH_TOKEN` when the resolved layer name contains `with_collector`.

The snippet above writes the token straight onto the function, where it is stored in plaintext and can be read by anyone holding `lambda:GetFunctionConfiguration` — a much broader audience than the people you would normally trust with the token. Unless you are prototyping, use `DT_CONNECTION_AUTH_TOKEN_SECRETS_MANAGER_ARN` instead; see *Storing the runtime token in AWS Secrets Manager* below.

**Step 3 — merge the layers and apply** (keep the customer's layers, drop only a previous Dynatrace one):

```bash
KEEP_LAYERS="$(aws lambda get-function-configuration \
  --region "$LAMBDA_REGION" --function-name "$LAMBDA_FN" \
  --query 'Layers[].Arn' --output text \
  | tr '\t' '\n' | grep -v 'Dynatrace_OneAgent_' | grep -v '^None$' || true)"

aws lambda update-function-configuration \
  --region "$LAMBDA_REGION" \
  --function-name "$LAMBDA_FN" \
  --layers "$DYNATRACE_LAYER_ARN" $KEEP_LAYERS \
  --environment "$MERGED_ENV"
```

Then wait until `LastUpdateStatus=Successful` before invoking the function.

### Create a new function and install OneAgent

Creating the function and instrumenting it in one go. Provisions **exactly two** resources for the named function, then attaches OneAgent the same way as the existing-function path. No extra logging, monitoring, or helper resources — anything beyond this is out of scope.

| Resource | Name | Notes |
|---|---|---|
| Lambda function | exactly the value the user passed | runtime + arch default to `python3.12` / `x86_64`; placeholder handler returning `{statusCode: 200}` |
| IAM execution role | `${LAMBDA_FN}-dt-execution-role` | trust policy: `lambda.amazonaws.com`; managed policy: `AWSLambdaBasicExecutionRole` |

Supported runtimes for the placeholder handler: `python*` and `nodejs*`. For Java, .NET, Go, or custom runtimes, create the function out-of-band with the real artifact, then use the CLI attach path on the existing function.

**Step 1 — Create the execution role:**

```bash
aws iam create-role \
  --role-name "${LAMBDA_FN}-dt-execution-role" \
  --description "Execution role for Lambda ${LAMBDA_FN}" \
  --assume-role-policy-document '{
    "Version":"2012-10-17",
    "Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]
  }'

aws iam attach-role-policy \
  --role-name "${LAMBDA_FN}-dt-execution-role" \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

# IAM is eventually consistent — a freshly created role is often not yet
# assumable by lambda:CreateFunction. ~10s is the documented workaround.
sleep 10

ROLE_ARN=$(aws iam get-role --role-name "${LAMBDA_FN}-dt-execution-role" \
  --query 'Role.Arn' --output text)
```

**Step 2 — Build a minimal deployment package.** Python (default) shown; the matching Node.js handler is below.

```bash
TMP=$(mktemp -d)
cat > "$TMP/lambda_function.py" <<'PY'
def lambda_handler(event, context):
    return {"statusCode": 200, "body": "Placeholder handler — OneAgent instrumentation attached."}
PY
( cd "$TMP" && zip -q -r "/tmp/${LAMBDA_FN}.zip" . )
# Handler string for create-function: "lambda_function.lambda_handler"
```

Node.js variant (`--runtime nodejs20.x` etc.):

```bash
cat > "$TMP/index.mjs" <<'JS'
export const handler = async (event) => ({
  statusCode: 200,
  body: "Placeholder handler — OneAgent instrumentation attached.",
});
JS
# Handler string for create-function: "index.handler"
```

**Step 3 — Create the function:**

```bash
aws lambda create-function \
  --region "$LAMBDA_REGION" \
  --function-name "$LAMBDA_FN" \
  --runtime python3.12 \
  --architectures x86_64 \
  --role "$ROLE_ARN" \
  --handler lambda_function.lambda_handler \
  --zip-file "fileb:///tmp/${LAMBDA_FN}.zip"

aws lambda wait function-active \
  --region "$LAMBDA_REGION" \
  --function-name "$LAMBDA_FN"
```

**Step 4 — Attach OneAgent.** Use the "CLI attach" command above against the newly created function. The layer ARN comes from the Dynatrace layer-ARN API (see *Layer ARN auto-discovery* — pass the same runtime/region/architecture you just created).

**Idempotency:** if the function or role already exists, `create-*` calls fail with `EntityAlreadyExists` / `ResourceConflictException`; treat those as no-ops and proceed to attach.

**Teardown** is the caller's responsibility — uninstall (below) removes only the OneAgent layer + env vars. To delete the function and role entirely:

```bash
aws lambda delete-function --function-name "$LAMBDA_FN" --region "$LAMBDA_REGION"
aws iam detach-role-policy --role-name "${LAMBDA_FN}-dt-execution-role" \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
aws iam delete-role --role-name "${LAMBDA_FN}-dt-execution-role"
```

**Gotchas:**

- `aws lambda update-function-configuration --environment` accepts **JSON** for the whole parameter (`{"Variables":{…}}`) or **shorthand** (`Variables={K=v,K=v}`). It does *not* accept `Variables=<json>`. Mixing the two fails with `Expected: '=', received: '"'`.
- Before mutating, capture a backup with `aws lambda get-function-configuration --function-name <fn> > <fn>.config.backup.json`. To revert: `--layers $(jq -r '.Layers[]?.Arn' backup.json)` and `--environment "$(jq -c '{Variables: (.Environment.Variables // {})}' backup.json)"`.
- If you take a backup *after* OneAgent was already attached, the backup is poisoned — restoring it re-instruments the function. Always check `current_has_dynatrace` before overwriting an existing backup file.

### Storing the runtime token in AWS Secrets Manager (preferred)

Write the token to a `0600` file first — `--secret-string "$DT_API_TOKEN"` would put it in the AWS CLI's command line, visible to `ps`:

```bash
umask 077
TOKEN_FILE="$(mktemp)"
trap 'rm -f "$TOKEN_FILE"' EXIT
printf '%s' "$DT_API_TOKEN" > "$TOKEN_FILE"
```

```bash
SECRET_ARN=$(aws secretsmanager create-secret \
  --region "$LAMBDA_REGION" \
  --name "dynatrace/oneagent/${LAMBDA_FN}/auth-token" \
  --secret-string "file://$TOKEN_FILE" \
  --query ARN --output text)

# Grant the function's execution role read on this one secret
aws iam put-role-policy --role-name "$FN_ROLE" \
  --policy-name Dynatrace-OneAgent-SecretAccess \
  --policy-document "$(jq -nc --arg arn "$SECRET_ARN" '
    {Version:"2012-10-17", Statement:[{Effect:"Allow",
     Action:"secretsmanager:GetSecretValue", Resource:$arn}]}')"
```

Then set `DT_CONNECTION_AUTH_TOKEN_SECRETS_MANAGER_ARN=$SECRET_ARN` on the function (instead of the inlined `DT_CONNECTION_AUTH_TOKEN`).

### Surgical uninstall (no backup available)

```bash
CFG=$(aws lambda get-function-configuration --region "$R" --function-name "$F")

KEEP_LAYERS=( $(echo "$CFG" | jq -r '.Layers[]?.Arn | select(test("dynatrace"; "i") | not)') )
KEEP_ENV_JSON=$(echo "$CFG" | jq -c '{
  Variables: (.Environment.Variables // {}
              | with_entries(select(.key | test("^DT_|^AWS_LAMBDA_EXEC_WRAPPER$") | not)))
}')

LAYER_ARGS=(--layers)
[ "${#KEEP_LAYERS[@]}" -gt 0 ] && LAYER_ARGS=(--layers "${KEEP_LAYERS[@]}")

aws lambda update-function-configuration --region "$R" --function-name "$F" \
  "${LAYER_ARGS[@]}" --environment "$KEEP_ENV_JSON"
```

When the Dynatrace layer was the function's only layer, `KEEP_LAYERS` is empty and the call is made with a bare `--layers`. That is intentional and correct: it sends an empty layer list, which is the documented way to detach every layer. Do **not** "fix" this by passing `--layers ''` — an empty string is validated as a layer ARN and the CLI rejects it before the request is sent (`Invalid length for parameter Layers[0], value: 0, valid min length: 1`), which breaks the most common uninstall case.

### Verifying instrumentation

The definitive signals that OneAgent is actually loaded by the runtime are:

1. A layer ARN containing `Dynatrace_OneAgent_…` in `Layers[].Arn`, **and**
2. `AWS_LAMBDA_EXEC_WRAPPER=/opt/dynatrace` in the function's environment.

`DT_TENANT`, `DT_CONNECTION_BASE_URL`, etc. are *not* sufficient on their own — application code commonly sets them for its own Dynatrace API calls. Use both signals together.

---
