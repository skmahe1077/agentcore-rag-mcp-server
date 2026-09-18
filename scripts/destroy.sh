#!/usr/bin/env bash
# Destroys all Terraform-managed resources for this project. Requires
# explicit confirmation (type the project name) unless --yes is passed.
#
# Usage: scripts/destroy.sh [--yes]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TF_DIR="${REPO_ROOT}/terraform"
AUTO_APPROVE=""
[ "${1:-}" = "--yes" ] && AUTO_APPROVE="-auto-approve"

command -v terraform >/dev/null 2>&1 || { echo "terraform is required but not found on PATH." >&2; exit 1; }

PROJECT_NAME="$(terraform -chdir="${TF_DIR}" console <<<'var.project_name' 2>/dev/null | tr -d '"' || echo "cloud-operations-runbook-assistant")"

if [ -z "${AUTO_APPROVE}" ]; then
  echo "This will destroy every AWS resource this project manages (project: ${PROJECT_NAME})."
  read -r -p "Type the project name to confirm: " CONFIRM
  [ "${CONFIRM}" = "${PROJECT_NAME}" ] || { echo "Confirmation did not match. Aborted."; exit 1; }
fi

echo "==> terraform destroy"
terraform -chdir="${TF_DIR}" destroy -input=false ${AUTO_APPROVE}

echo
echo "Destroy complete. Run scripts/verify_cleanup.sh to confirm nothing billable remains."
