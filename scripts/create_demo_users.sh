#!/usr/bin/env bash
# The two demo Cognito users are created declaratively by Terraform
# (terraform/cognito.tf: aws_cognito_user.demo, with generated permanent
# passwords). This script verifies they exist and are enabled, and can
# rotate a user's password if you ever need to (e.g. after a suspected
# leak) without a full `terraform apply`.
#
# Usage:
#   scripts/create_demo_users.sh                 # verify only
#   scripts/create_demo_users.sh --rotate <user_id>
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TF_DIR="${REPO_ROOT}/terraform"

command -v aws >/dev/null 2>&1 || { echo "AWS CLI is required but not found on PATH." >&2; exit 1; }

POOL_ID="$(terraform -chdir="${TF_DIR}" output -raw cognito_user_pool_id)"
[ -n "${POOL_ID}" ] || { echo "Could not read cognito_user_pool_id from terraform output. Run 'terraform apply' first." >&2; exit 1; }

mapfile -t USER_IDS < <(terraform -chdir="${TF_DIR}" output -json demo_user_ids | python3 -c 'import json,sys; print("\n".join(json.load(sys.stdin)))')

if [ "${1:-}" = "--rotate" ]; then
  TARGET_USER="${2:?Usage: scripts/create_demo_users.sh --rotate <user_id>}"
  NEW_PASSWORD="$(python3 -c 'import secrets,string; alphabet=string.ascii_letters+string.digits+"!@#$%^&*()-_"; print("".join(secrets.choice(alphabet) for _ in range(24)))')"
  aws cognito-idp admin-set-user-password \
    --user-pool-id "${POOL_ID}" \
    --username "${TARGET_USER}" \
    --password "${NEW_PASSWORD}" \
    --permanent >/dev/null
  echo "Password rotated for ${TARGET_USER}. It no longer matches Terraform state -"
  echo "run 'terraform apply' afterwards if you want Terraform's generated password to be the source of truth again."
  exit 0
fi

echo "Verifying demo users in pool ${POOL_ID}:"
for user_id in "${USER_IDS[@]}"; do
  STATUS="$(aws cognito-idp admin-get-user --user-pool-id "${POOL_ID}" --username "${user_id}" \
    --query 'UserStatus' --output text 2>/dev/null || echo "NOT_FOUND")"
  ENABLED="$(aws cognito-idp admin-get-user --user-pool-id "${POOL_ID}" --username "${user_id}" \
    --query 'Enabled' --output text 2>/dev/null || echo "unknown")"
  echo "  ${user_id}: status=${STATUS} enabled=${ENABLED}"
done
