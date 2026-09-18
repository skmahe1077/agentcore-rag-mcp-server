#!/usr/bin/env bash
# Full deployment: builds and pushes the agent container image, builds the
# Lambda dependency layer, applies Terraform, uploads runbooks, syncs the
# Knowledge Base, and seeds simulated demo data.
#
# The agent image must exist in ECR before the agent_runtime resource can
# be created, so this does a targeted apply for the ECR repository first -
# see the comment below for why -target is used here specifically.
#
# Usage: scripts/deploy.sh [--yes]
#   --yes   skip the confirmation prompt before `terraform apply`
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TF_DIR="${REPO_ROOT}/terraform"
AUTO_APPROVE=""
[ "${1:-}" = "--yes" ] && AUTO_APPROVE="-auto-approve"

for tool in terraform aws docker python3; do
  command -v "${tool}" >/dev/null 2>&1 || { echo "${tool} is required but not found on PATH." >&2; exit 1; }
done

if [ ! -f "${TF_DIR}/terraform.tfvars" ]; then
  echo "terraform/terraform.tfvars not found. Copy terraform/terraform.tfvars.example and edit it first." >&2
  exit 1
fi

echo "==> terraform init"
terraform -chdir="${TF_DIR}" init -input=false

# Read directly from the variable via `terraform console` rather than
# `terraform output` - outputs aren't reliably populated yet at this point
# (a -target-scoped apply only writes outputs reachable from that target's
# dependency graph, which excludes plain variable passthroughs like this).
REGION="$(terraform -chdir="${TF_DIR}" console <<<'var.aws_region' | tr -d '"')"

echo "==> Creating the ECR repository first (chicken-and-egg: the agent"
echo "    container image must exist before the agent_runtime resource can"
echo "    reference it, but the repository must exist before we can push)."
terraform -chdir="${TF_DIR}" apply -input=false ${AUTO_APPROVE} -target=aws_ecr_repository.agent

REPO_URL="$(terraform -chdir="${TF_DIR}" output -raw ecr_repository_url)"
# Matches the default of var.agent_image_tag in terraform/variables.tf;
# override with AGENT_IMAGE_TAG=v1.2.3 if you set agent_image_tag in
# terraform.tfvars to something other than "latest".
IMAGE_TAG="${AGENT_IMAGE_TAG:-latest}"
IMAGE_URI="${REPO_URL}:${IMAGE_TAG}"

echo "==> Building and pushing agent image: ${IMAGE_URI}"
aws ecr get-login-password --region "${REGION}" \
  | docker login --username AWS --password-stdin "${REPO_URL%%/*}"
docker build --platform linux/arm64 -f "${REPO_ROOT}/app/Dockerfile" -t "${IMAGE_URI}" "${REPO_ROOT}"
docker push "${IMAGE_URI}"

echo "==> Building Lambda dependency layer"
"${REPO_ROOT}/scripts/build_lambda_packages.sh"

echo "==> terraform apply (full)"
if [ -z "${AUTO_APPROVE}" ]; then
  echo "About to create/update all remaining AWS resources for this project."
  read -r -p "Continue? [y/N] " CONFIRM
  [ "${CONFIRM}" = "y" ] || [ "${CONFIRM}" = "Y" ] || { echo "Aborted."; exit 1; }
fi
terraform -chdir="${TF_DIR}" apply -input=false ${AUTO_APPROVE}

echo "==> Uploading runbooks"
"${REPO_ROOT}/scripts/upload_runbooks.sh"

echo "==> Syncing Knowledge Base"
"${REPO_ROOT}/scripts/sync_knowledge_base.sh"

echo "==> Seeding simulated demo data"
"${REPO_ROOT}/scripts/seed_demo_events.sh"

echo
echo "Deployment complete. Next: scripts/smoke_test.sh, then scripts/run_demo.sh."
