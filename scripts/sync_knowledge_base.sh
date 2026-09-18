#!/usr/bin/env bash
# Starts a Bedrock Knowledge Base ingestion job and polls until it
# completes. Run after scripts/upload_runbooks.sh, and again any time
# sample-data/ changes.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TF_DIR="${REPO_ROOT}/terraform"
POLL_INTERVAL_SECONDS=10
MAX_POLLS=60 # 10 minutes

command -v aws >/dev/null 2>&1 || { echo "AWS CLI is required but not found on PATH." >&2; exit 1; }

KB_ID="$(terraform -chdir="${TF_DIR}" output -raw knowledge_base_id)"
DATA_SOURCE_ID="$(terraform -chdir="${TF_DIR}" output -raw knowledge_base_data_source_id)"
[ -n "${KB_ID}" ] && [ -n "${DATA_SOURCE_ID}" ] || { echo "Could not read Knowledge Base outputs. Run 'terraform apply' first." >&2; exit 1; }

echo "Starting ingestion job for knowledge base ${KB_ID}, data source ${DATA_SOURCE_ID} ..."
JOB_ID="$(aws bedrock-agent start-ingestion-job \
  --knowledge-base-id "${KB_ID}" \
  --data-source-id "${DATA_SOURCE_ID}" \
  --query 'ingestionJob.ingestionJobId' --output text)"

echo "Ingestion job started: ${JOB_ID}"

for ((i = 0; i < MAX_POLLS; i++)); do
  STATUS="$(aws bedrock-agent get-ingestion-job \
    --knowledge-base-id "${KB_ID}" \
    --data-source-id "${DATA_SOURCE_ID}" \
    --ingestion-job-id "${JOB_ID}" \
    --query 'ingestionJob.status' --output text)"

  echo "  status: ${STATUS}"

  case "${STATUS}" in
    COMPLETE)
      echo "Ingestion complete."
      exit 0
      ;;
    FAILED)
      echo "Ingestion failed." >&2
      aws bedrock-agent get-ingestion-job \
        --knowledge-base-id "${KB_ID}" \
        --data-source-id "${DATA_SOURCE_ID}" \
        --ingestion-job-id "${JOB_ID}" \
        --query 'ingestionJob.failureReasons' --output text >&2
      exit 1
      ;;
  esac

  sleep "${POLL_INTERVAL_SECONDS}"
done

echo "Timed out waiting for ingestion job ${JOB_ID} to complete." >&2
exit 1
