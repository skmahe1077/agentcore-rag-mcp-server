#!/usr/bin/env bash
# Post-deployment smoke test: confirms the core resources exist and
# respond, without running a full demo conversation. Safe to run
# repeatedly; read-only against AWS.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TF_DIR="${REPO_ROOT}/terraform"
FAILURES=0

check() {
  local description="$1"
  shift
  printf '%-60s' "${description}"
  if "$@" >/dev/null 2>&1; then
    echo "OK"
  else
    echo "FAILED"
    FAILURES=$((FAILURES + 1))
  fi
}

REGION="$(terraform -chdir="${TF_DIR}" output -raw aws_region)"
TABLE_NAME="$(terraform -chdir="${TF_DIR}" output -raw dynamodb_table_name)"
KB_ID="$(terraform -chdir="${TF_DIR}" output -raw knowledge_base_id)"
POOL_ID="$(terraform -chdir="${TF_DIR}" output -raw cognito_user_pool_id)"
BUCKET="$(terraform -chdir="${TF_DIR}" output -raw runbook_documents_bucket)"
AGENT_RUNTIME_ID="$(terraform -chdir="${TF_DIR}" output -raw agent_runtime_id)"

check "DynamoDB table exists and is ACTIVE" \
  bash -c "aws dynamodb describe-table --table-name '${TABLE_NAME}' --region '${REGION}' --query 'Table.TableStatus' --output text | grep -q ACTIVE"

check "DynamoDB table has entitlement records" \
  bash -c "aws dynamodb query --table-name '${TABLE_NAME}' --region '${REGION}' --key-condition-expression 'pk = :pk' --expression-attribute-values '{\":pk\":{\"S\":\"ENTITLEMENT#incident_commander\"}}' --query 'Count' --output text | grep -qv '^0$'"

check "Knowledge Base exists" \
  aws bedrock-agent get-knowledge-base --knowledge-base-id "${KB_ID}" --region "${REGION}"

check "Runbook documents bucket is reachable" \
  aws s3api head-bucket --bucket "${BUCKET}"

check "Cognito user pool exists" \
  aws cognito-idp describe-user-pool --user-pool-id "${POOL_ID}" --region "${REGION}"

check "Demo users exist" \
  aws cognito-idp admin-get-user --user-pool-id "${POOL_ID}" --username demo-incident-commander --region "${REGION}"

check "AgentCore Runtime exists" \
  aws bedrock-agentcore-control get-agent-runtime --agent-runtime-id "${AGENT_RUNTIME_ID}" --region "${REGION}"

command -v jq >/dev/null 2>&1 || { echo "jq is required but not found on PATH." >&2; exit 1; }

# Read actual deployed function names rather than reconstructing them -
# they're truncated to fit AWS's 64-character limit (see lambda-tools.tf).
while IFS=$'\t' read -r tool fn_name; do
  check "Lambda tool ${tool} exists" \
    aws lambda get-function --function-name "${fn_name}" --region "${REGION}"
done < <(terraform -chdir="${TF_DIR}" output -json mcp_tool_function_names | jq -r 'to_entries[] | "\(.key)\t\(.value)"')

echo
if [ "${FAILURES}" -eq 0 ]; then
  echo "Smoke test passed."
  exit 0
else
  echo "Smoke test failed: ${FAILURES} check(s) did not pass." >&2
  exit 1
fi
