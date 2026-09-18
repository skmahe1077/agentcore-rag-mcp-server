#!/usr/bin/env bash
# Confirms no billable resources remain after `scripts/destroy.sh`. Checks
# each resource type this project can create; never touches resources it
# doesn't recognize as belonging to this project (name-prefix or tag
# matched only).
set -euo pipefail

PROJECT_NAME="${PROJECT_NAME:-cloud-operations-runbook-assistant}"
ENVIRONMENT="${ENVIRONMENT:-demo}"
REGION="${AWS_REGION:-eu-west-1}"
NAME_PREFIX="${PROJECT_NAME}-${ENVIRONMENT}"
# Lambda function names are truncated to the first 36 chars of NAME_PREFIX
# to fit AWS's 64-character limit (see terraform/lambda-tools.tf) - mirror
# that here since terraform output isn't available after `destroy`.
LAMBDA_NAME_PREFIX="${NAME_PREFIX:0:36}"
REMAINING=0

command -v aws >/dev/null 2>&1 || { echo "AWS CLI is required but not found on PATH." >&2; exit 1; }

report() {
  local description="$1" count="$2"
  if [ "${count}" -gt 0 ]; then
    echo "REMAINING: ${description} (${count})"
    REMAINING=$((REMAINING + count))
  else
    echo "clean:     ${description}"
  fi
}

echo "Checking for remaining resources with prefix '${NAME_PREFIX}' in ${REGION} ..."
echo "==============================================================================="

COUNT="$(aws bedrock-agentcore-control list-agent-runtimes --region "${REGION}" \
  --query "length(agentRuntimes[?starts_with(agentRuntimeName, '${NAME_PREFIX//-/_}')])" --output text 2>/dev/null || echo 0)"
report "AgentCore Runtimes" "${COUNT:-0}"

COUNT="$(aws bedrock-agentcore-control list-gateways --region "${REGION}" \
  --query "length(items[?starts_with(name, '${NAME_PREFIX}')])" --output text 2>/dev/null || echo 0)"
report "AgentCore Gateways" "${COUNT:-0}"

COUNT="$(aws bedrock-agentcore-control list-workload-identities --region "${REGION}" \
  --query "length(workloadIdentities[?starts_with(name, '${NAME_PREFIX}')])" --output text 2>/dev/null || echo 0)"
report "AgentCore Identity workload identities" "${COUNT:-0}"

COUNT="$(aws bedrock-agent list-knowledge-bases --region "${REGION}" \
  --query "length(knowledgeBaseSummaries[?starts_with(name, '${NAME_PREFIX}')])" --output text 2>/dev/null || echo 0)"
report "Bedrock Knowledge Bases" "${COUNT:-0}"

COUNT="$(aws s3vectors list-vector-buckets --region "${REGION}" \
  --query "length(vectorBuckets[?starts_with(vectorBucketName, '${NAME_PREFIX}')])" --output text 2>/dev/null || echo 0)"
report "S3 Vectors buckets" "${COUNT:-0}"

COUNT="$(aws s3api list-buckets --query "length(Buckets[?starts_with(Name, '${NAME_PREFIX}')])" --output text 2>/dev/null || echo 0)"
report "S3 buckets (documents + artifacts)" "${COUNT:-0}"

COUNT="$(aws lambda list-functions --region "${REGION}" \
  --query "length(Functions[?starts_with(FunctionName, '${LAMBDA_NAME_PREFIX}')])" --output text 2>/dev/null || echo 0)"
report "Lambda functions" "${COUNT:-0}"

if aws dynamodb describe-table --table-name "${NAME_PREFIX}-table" --region "${REGION}" >/dev/null 2>&1; then
  report "DynamoDB table" 1
else
  report "DynamoDB table" 0
fi

COUNT="$(aws cognito-idp list-user-pools --region "${REGION}" --max-results 60 \
  --query "length(UserPools[?starts_with(Name, '${NAME_PREFIX}')])" --output text 2>/dev/null || echo 0)"
report "Cognito user pools" "${COUNT:-0}"

COUNT="$(aws logs describe-log-groups --region "${REGION}" --log-group-name-prefix "/aws/lambda/${NAME_PREFIX}" \
  --query "length(logGroups)" --output text 2>/dev/null || echo 0)"
report "CloudWatch log groups (Lambda)" "${COUNT:-0}"

if aws cloudwatch get-dashboard --dashboard-name "${NAME_PREFIX}-dashboard" --region "${REGION}" >/dev/null 2>&1; then
  report "CloudWatch dashboard" 1
else
  report "CloudWatch dashboard" 0
fi

COUNT="$(aws cloudwatch describe-alarms --region "${REGION}" --alarm-name-prefix "${NAME_PREFIX}" \
  --query "length(MetricAlarms)" --output text 2>/dev/null || echo 0)"
report "CloudWatch alarms" "${COUNT:-0}"

COUNT="$(aws iam list-roles --query "length(Roles[?starts_with(RoleName, '${NAME_PREFIX}')])" --output text 2>/dev/null || echo 0)"
report "IAM roles" "${COUNT:-0}"

if aws kms describe-key --key-id "alias/${NAME_PREFIX}" --region "${REGION}" >/dev/null 2>&1; then
  echo "REMAINING: customer-managed KMS key alias/${NAME_PREFIX} still exists (if use_customer_managed_kms was enabled, delete it manually after its retention window; KMS keys cannot be force-deleted immediately)"
  REMAINING=$((REMAINING + 1))
else
  report "Customer-managed KMS key" 0
fi

COUNT="$(aws budgets describe-budgets --account-id "$(aws sts get-caller-identity --query Account --output text)" \
  --query "length(Budgets[?starts_with(BudgetName, '${NAME_PREFIX}')])" --output text 2>/dev/null || echo 0)"
report "AWS Budgets" "${COUNT:-0}"

COUNT="$(aws opensearchserverless list-collections --region "${REGION}" \
  --query "length(collectionSummaries[?starts_with(name, '${NAME_PREFIX}')])" --output text 2>/dev/null || echo 0)"
report "OpenSearch Serverless collections (optional backend)" "${COUNT:-0}"

COUNT="$(aws ecr describe-repositories --region "${REGION}" \
  --query "length(repositories[?starts_with(repositoryName, '${NAME_PREFIX}')])" --output text 2>/dev/null || echo 0)"
report "ECR repositories" "${COUNT:-0}"

echo "==============================================================================="
if [ "${REMAINING}" -eq 0 ]; then
  echo "Cleanup verified: no remaining resources found."
  exit 0
else
  echo "Cleanup incomplete: ${REMAINING} resource group(s) still present. See TROUBLESHOOTING.md." >&2
  exit 1
fi
