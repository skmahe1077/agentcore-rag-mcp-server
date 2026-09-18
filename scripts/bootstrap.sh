#!/usr/bin/env bash
# Checks local dependencies and sets up a Python virtual environment.
# Idempotent - safe to run repeatedly.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MISSING=()

check() {
  command -v "$1" >/dev/null 2>&1 || MISSING+=("$1")
}

check terraform
check aws
check python3
check docker
check jq

if [ "${#MISSING[@]}" -gt 0 ]; then
  echo "Missing required tools: ${MISSING[*]}" >&2
  echo "Install them, then re-run this script." >&2
  exit 1
fi

TF_VERSION="$(terraform version -json | python3 -c 'import json,sys; print(json.load(sys.stdin)["terraform_version"])')"
echo "Terraform ${TF_VERSION} found."

PY_VERSION="$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')"
echo "Python ${PY_VERSION} found (3.12+ recommended to match the Lambda/AgentCore runtime)."

VENV_DIR="${REPO_ROOT}/.venv"
if [ ! -d "${VENV_DIR}" ]; then
  echo "Creating virtual environment at ${VENV_DIR} ..."
  python3 -m venv "${VENV_DIR}"
fi

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet -r "${REPO_ROOT}/requirements-dev.txt"

echo
echo "Bootstrap complete. Activate the virtual environment with:"
echo "  source ${VENV_DIR}/bin/activate"
echo
echo "Next steps:"
echo "  1. Copy terraform/terraform.tfvars.example to terraform/terraform.tfvars and edit it."
echo "  2. Confirm Bedrock model access in the console for your account/region."
echo "  3. Run: make plan"
