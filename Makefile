.PHONY: init fmt validate lint security-scan test plan apply upload-runbooks sync-kb deploy-agent seed-demo demo smoke-test cost-estimate list-billable-resources destroy verify-cleanup

TF_DIR := terraform
PYTHON := python3

init: ## Initialize Terraform and Python dependencies
	terraform -chdir=$(TF_DIR) init
	$(PYTHON) -m venv .venv || true
	. .venv/bin/activate && pip install --quiet --upgrade pip && pip install --quiet -r requirements-dev.txt

fmt: ## Format Terraform and check Python formatting
	terraform -chdir=$(TF_DIR) fmt -recursive
	. .venv/bin/activate && ruff format app tests scripts

validate: ## Validate Terraform configuration
	terraform -chdir=$(TF_DIR) validate

lint: ## Lint Terraform (tflint, if installed) and Python (ruff)
	@command -v tflint >/dev/null 2>&1 && (cd $(TF_DIR) && tflint) || echo "tflint not installed - skipping (see TROUBLESHOOTING.md)"
	@command -v shellcheck >/dev/null 2>&1 && shellcheck scripts/*.sh || echo "shellcheck not installed - skipping (see TROUBLESHOOTING.md)"
	. .venv/bin/activate && ruff check app tests scripts

security-scan: ## Run Checkov/Trivy against the Terraform config
	@command -v checkov >/dev/null 2>&1 && checkov -d $(TF_DIR) --quiet || echo "checkov not installed - skipping (see TROUBLESHOOTING.md)"
	@command -v trivy >/dev/null 2>&1 && trivy config $(TF_DIR) || echo "trivy not installed - skipping (see TROUBLESHOOTING.md)"

test: ## Run the Python test suite
	. .venv/bin/activate && PYTHONPATH=. pytest tests/ -v

plan: ## terraform plan
	terraform -chdir=$(TF_DIR) plan

apply: ## Full deployment (build image, apply Terraform, ingest runbooks, seed data)
	scripts/deploy.sh

upload-runbooks: ## Upload sample-data/ documents to the Knowledge Base's S3 bucket
	scripts/upload_runbooks.sh

sync-kb: ## Trigger and wait for a Knowledge Base ingestion job
	scripts/sync_knowledge_base.sh

deploy-agent: ## Build and push the agent container image only
	scripts/build_lambda_packages.sh
	@echo "Run scripts/deploy.sh for the full build-and-push + terraform apply flow."

seed-demo: ## Seed simulated operational data and entitlements into DynamoDB
	scripts/seed_demo_events.sh

demo: ## Run the four demo scenarios from DEMO.md
	scripts/run_demo.sh

smoke-test: ## Post-deployment smoke test (read-only checks against AWS)
	scripts/smoke_test.sh

cost-estimate: ## Print a qualitative cost assessment before deploying
	scripts/estimate_cost.sh

list-billable-resources: ## List AWS resources tagged for this project
	scripts/list_billable_resources.sh

destroy: ## Destroy all Terraform-managed resources (requires confirmation)
	scripts/destroy.sh

verify-cleanup: ## Confirm no billable resources remain after destroy
	scripts/verify_cleanup.sh
