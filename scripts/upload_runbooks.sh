#!/usr/bin/env bash
# Uploads sample-data/{runbooks,procedures,architecture,restricted} (each
# document plus its .metadata.json sidecar) to the Knowledge Base's S3
# source bucket. Idempotent - `aws s3 sync` only transfers changed files.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TF_DIR="${REPO_ROOT}/terraform"

command -v aws >/dev/null 2>&1 || { echo "AWS CLI is required but not found on PATH." >&2; exit 1; }

BUCKET="$(terraform -chdir="${TF_DIR}" output -raw runbook_documents_bucket)"
[ -n "${BUCKET}" ] || { echo "Could not read runbook_documents_bucket from terraform output. Run 'terraform apply' first." >&2; exit 1; }

for dir in runbooks procedures architecture restricted; do
  echo "Uploading sample-data/${dir}/ -> s3://${BUCKET}/${dir}/"
  aws s3 sync "${REPO_ROOT}/sample-data/${dir}/" "s3://${BUCKET}/${dir}/" --delete
done

echo
echo "Upload complete. Next: scripts/sync_knowledge_base.sh to trigger ingestion."
