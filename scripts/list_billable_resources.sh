#!/usr/bin/env bash
# Lists AWS resources tagged for this project, so you can see everything
# that's billable before and after deployment. Used by `make
# list-billable-resources` and by scripts/verify_cleanup.sh.
set -euo pipefail

PROJECT_NAME="${PROJECT_NAME:-cloud-operations-runbook-assistant}"
AWS_REGION="${AWS_REGION:-eu-west-1}"

command -v aws >/dev/null 2>&1 || { echo "AWS CLI is required but not found on PATH." >&2; exit 1; }

echo "Resources tagged Project=${PROJECT_NAME} in ${AWS_REGION}:"
echo "============================================================"

aws resourcegroupstaggingapi get-resources \
  --region "${AWS_REGION}" \
  --tag-filters "Key=Project,Values=${PROJECT_NAME}" \
  --query 'ResourceTagMappingList[].ResourceARN' \
  --output text | tr '\t' '\n' | sort

echo
echo "Resources not covered by the tagging API (checked individually):"
echo "-------------------------------------------------------------------"

NAME_PREFIX="${PROJECT_NAME}-${ENVIRONMENT:-demo}"

echo "- Cognito user pools matching '${NAME_PREFIX}':"
aws cognito-idp list-user-pools --region "${AWS_REGION}" --max-results 60 \
  --query "UserPools[?starts_with(Name, '${NAME_PREFIX}')].{Name:Name,Id:Id}" --output table || true

echo "- ECR repositories matching '${NAME_PREFIX}':"
aws ecr describe-repositories --region "${AWS_REGION}" \
  --query "repositories[?starts_with(repositoryName, '${NAME_PREFIX}')].{Name:repositoryName,URI:repositoryUri}" \
  --output table 2>/dev/null || echo "  (none found, or ecr:DescribeRepositories not permitted)"

echo "- S3 Vectors buckets matching '${NAME_PREFIX}':"
aws s3vectors list-vector-buckets --region "${AWS_REGION}" \
  --query "vectorBuckets[?starts_with(vectorBucketName, '${NAME_PREFIX}')].vectorBucketName" \
  --output table 2>/dev/null || echo "  (none found, or s3vectors CLI not available in this AWS CLI version)"

echo "- AgentCore Runtimes matching '${NAME_PREFIX}':"
aws bedrock-agentcore-control list-agent-runtimes --region "${AWS_REGION}" \
  --query "agentRuntimes[?starts_with(agentRuntimeName, '${NAME_PREFIX}')].{Name:agentRuntimeName,Id:agentRuntimeId}" \
  --output table 2>/dev/null || echo "  (none found, or bedrock-agentcore-control CLI not available in this AWS CLI version)"

echo "- AgentCore Gateways matching '${NAME_PREFIX}':"
aws bedrock-agentcore-control list-gateways --region "${AWS_REGION}" \
  --query "items[?starts_with(name, '${NAME_PREFIX}')].{Name:name,Id:gatewayId}" \
  --output table 2>/dev/null || echo "  (none found, or bedrock-agentcore-control CLI not available in this AWS CLI version)"

echo
echo "AWS Budgets (account-level, not tag-filterable):"
aws budgets describe-budgets --account-id "$(aws sts get-caller-identity --query Account --output text)" \
  --query "Budgets[?starts_with(BudgetName, '${NAME_PREFIX}')].BudgetName" --output table 2>/dev/null || true
