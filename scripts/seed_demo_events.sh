#!/usr/bin/env bash
# Thin wrapper around scripts/seed_demo_data.py using Terraform outputs.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TF_DIR="${REPO_ROOT}/terraform"

TABLE_NAME="$(terraform -chdir="${TF_DIR}" output -raw dynamodb_table_name)"
REGION="$(terraform -chdir="${TF_DIR}" output -raw aws_region)"
[ -n "${TABLE_NAME}" ] || { echo "Could not read dynamodb_table_name from terraform output. Run 'terraform apply' first." >&2; exit 1; }

python3 "${REPO_ROOT}/scripts/seed_demo_data.py" --table-name "${TABLE_NAME}" --region "${REGION}"
