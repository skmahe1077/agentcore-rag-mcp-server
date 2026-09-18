#!/usr/bin/env bash
# Fetches a bearer ID token for a demo user and writes it to a local,
# gitignored file - never prints the password, and prints the token only
# if you pass --print.
#
# Usage: scripts/get_demo_token.sh <read-only|incident-commander> [--print]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TF_DIR="${REPO_ROOT}/terraform"

ROLE_ARG="${1:-}"
case "${ROLE_ARG}" in
  read-only) USER_ID="demo-read-only-operator" ;;
  incident-commander) USER_ID="demo-incident-commander" ;;
  *)
    echo "Usage: $0 <read-only|incident-commander> [--print]" >&2
    exit 1
    ;;
esac

command -v jq >/dev/null 2>&1 || { echo "jq is required but not found on PATH." >&2; exit 1; }

CLIENT_ID="$(terraform -chdir="${TF_DIR}" output -raw cognito_user_pool_client_id)"
REGION="$(terraform -chdir="${TF_DIR}" output -raw aws_region)"
PASSWORD="$(terraform -chdir="${TF_DIR}" output -json demo_user_passwords | jq -r --arg u "${USER_ID}" '.[$u]')"

[ -n "${CLIENT_ID}" ] && [ -n "${PASSWORD}" ] || { echo "Could not read Cognito outputs. Run 'terraform apply' first." >&2; exit 1; }

TOKEN="$(PYTHONPATH="${REPO_ROOT}" python3 -c "
from app.client.auth import get_access_token
print(get_access_token(user_id='${USER_ID}', password='''${PASSWORD}''', client_id='${CLIENT_ID}', region='${REGION}'))
")"

OUT_FILE="${REPO_ROOT}/.demo-token-${ROLE_ARG}"
printf '%s' "${TOKEN}" > "${OUT_FILE}"
chmod 600 "${OUT_FILE}"

echo "Token for ${USER_ID} written to ${OUT_FILE} (not printed)."

if [ "${2:-}" = "--print" ]; then
  echo "${TOKEN}"
fi
