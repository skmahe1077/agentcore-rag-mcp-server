#!/usr/bin/env bash
# Builds the Lambda dependency layer for the 7 MCP tool functions
# (lambda-tools.tf). Terraform cannot cross-compile/cross-platform-install
# Python wheels, so this is the documented last-resort scripted step for
# that one piece - the tool code itself is still zipped declaratively by
# Terraform's archive_file data source, not by this script.
#
# Usage: scripts/build_lambda_packages.sh
# Output: build/lambda-layer/python/... (terraform/lambda-tools.tf reads this path)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAYER_DIR="${REPO_ROOT}/build/lambda-layer"
PYTHON_DIR="${LAYER_DIR}/python"

command -v pip >/dev/null 2>&1 || { echo "pip is required but not found on PATH." >&2; exit 1; }

echo "Building Lambda dependency layer at ${PYTHON_DIR} ..."
rm -rf "${LAYER_DIR}"
mkdir -p "${PYTHON_DIR}"

pip install \
  --platform manylinux2014_aarch64 \
  --target "${PYTHON_DIR}" \
  --implementation cp \
  --python-version 3.12 \
  --only-binary=:all: \
  --upgrade \
  --requirement "${REPO_ROOT}/app/mcp_server/requirements.txt"

# Strip caches/tests to keep the layer small - purely a size optimization,
# safe to remove without affecting behavior.
find "${PYTHON_DIR}" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "${PYTHON_DIR}" -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true

echo "Lambda dependency layer ready: ${PYTHON_DIR}"
echo "Run 'terraform apply' next - lambda-tools.tf packages this directory as the tools' Lambda layer."
