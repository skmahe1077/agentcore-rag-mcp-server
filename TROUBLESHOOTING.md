# Troubleshooting

## Integration points to verify before your first real deployment

This project was built and unit-tested extensively without live AWS credentials (all 62 tests in `tests/` run against `moto`-mocked AWS and mocked Bedrock calls - no real AWS account was reachable while writing it). Everything Terraform-side was confirmed against the actual installed provider schema (`terraform validate` passes) and current AWS documentation. A few integration points, specifically the *exact runtime request/response shapes* between managed AWS services, could not be confirmed against a live API call and are called out in code comments (`grep -rn "verify against the live" .`). Check these first if something doesn't work end-to-end:

1. **Gateway → Lambda invocation envelope** (`app/mcp_server/tools/*.py::lambda_handler`, `app/mcp_server/security.py::extract_gateway_authenticated_user_id`). The handlers accept either `event` directly or `event["arguments"]` as the tool payload, and look for Gateway-injected caller identity at `event["requestContext"]["authorizer"]["claims"]`. Confirm the actual shape by invoking a tool Lambda through the Gateway once deployed and logging the raw `event` (temporarily set `ENABLE_DEBUG_LOGGING=true` on one function), then adjust the envelope-parsing logic if needed.
2. **AgentCore Runtime bearer-token passthrough** (`app/client/demo_client.py::_inject_bearer_header`). The generated boto3 `invoke_agent_runtime` operation doesn't expose an `Authorization` parameter directly, so the demo client attaches it via a `before-sign` event hook. Confirm this actually reaches the runtime's `custom_jwt_authorizer` - if not, check whether the SDK expects the token via a different mechanism (e.g. `bedrock_agentcore_starter_toolkit`, if you adopt it, may handle this natively).
3. **Bedrock Knowledge Base retrieval filter operators** (`app/mcp_server/tools/search_runbooks.py::_build_filter`). Built using `equals` (for containment on list-type metadata) and `in` (for classification membership) based on documented Bedrock Retrieve filter semantics - confirm against a real `retrieve` call that `equals` on a `STRING_LIST` metadata attribute matches by containment as expected.
4. **`aws_bedrockagentcore_agent_runtime`'s `code_configuration.runtime` enum** and the container image entrypoint convention - this project uses `container_configuration` (not `code_configuration`) specifically because the documented, proven deployment path for a Strands-based agent is a container image; this sidesteps needing to verify `code_configuration`'s exact packaging convention at all.

None of these affect `terraform validate`, `terraform fmt`, linting, or the Python test suite - they only matter once you're invoking the deployed services end-to-end.

## "AWS credentials are invalid" / `InvalidClientTokenId`

Your AWS credentials aren't currently valid (expired, revoked, or misconfigured). Fix with `aws configure` or by updating `~/.aws/credentials`, then confirm with `aws sts get-caller-identity`. Nothing in this project can proceed past `terraform plan`/`apply` or any AWS CLI script without working credentials.

## Bedrock model access denied

Bedrock model access is granted per-account, per-model, in the Bedrock console ("Model access" page) - this is a manual, one-time step Terraform cannot perform. Do this before setting `foundation_model_id`/`embedding_model_id` in `terraform.tfvars`.

## `foundation_model_id` / `embedding_model_id` validation error

Both variables default to an empty string and have a Terraform `validation` block requiring a non-empty value - this is deliberate (see the comment in `terraform/variables.tf`), forcing you to confirm the exact model/inference-profile ID for your account in the Bedrock console rather than trusting a hardcoded default. Set both in `terraform.tfvars`; `terraform.tfvars.example` has recommended starting values for `eu-west-1`.

## `terraform apply` fails because the agent container image doesn't exist

The `agent_runtime` resource references an ECR image that must exist before it can be created - this is why `scripts/deploy.sh` applies just the ECR repository first (`-target=aws_ecr_repository.agent`), then builds and pushes the image, then applies everything else. If you're not using `scripts/deploy.sh`, follow the same order manually.

## `terraform apply` fails on the Lambda layer

`aws_lambda_layer_version` reads from `build/lambda-layer/` (via `data.archive_file.mcp_tools_layer`), which is built by `scripts/build_lambda_packages.sh`, not by Terraform. Run that script before `terraform apply` (or `terraform plan`) whenever `app/mcp_server/requirements.txt` changes, or the first time you run `apply`.

## Linters/scanners not installed

`make lint` and `make security-scan` gracefully skip `tflint`, `shellcheck`, `checkov`, and `trivy` if they're not on `PATH`, printing a note rather than failing. Install what you need:

```bash
brew install tflint shellcheck trivy   # macOS
pip install checkov
```

Ruff (Python lint/format) and `terraform validate`/`fmt` always run - those are pinned in `requirements-dev.txt` and bundled with Terraform respectively.

## `scripts/verify_cleanup.sh` reports remaining resources after `destroy`

- **KMS keys**: if `use_customer_managed_kms` was ever `true`, the key enters a pending-deletion window (7-30 days, `kms_deletion_window_in_days`) and cannot be force-deleted immediately - this is expected AWS behavior, not a bug.
- **CloudWatch log groups**: occasionally lag a few minutes behind the resources that wrote to them; re-run the check after a short wait.
- **Anything else**: `terraform destroy` may have partially failed - check `terraform show` for resources still in state, and re-run `terraform destroy`.

## Tests fail locally

Run `make test` (or `PYTHONPATH=. pytest tests/ -v` inside the venv from `scripts/bootstrap.sh`) - the suite needs no AWS credentials (it uses `moto` and mocks). If a test fails, check first whether `app/mcp_server/schemas.py` and `terraform/agentcore.tf`'s `local.tool_schema_definitions` have drifted out of sync (see CONTRIBUTING.md).

## Known limitations

- The `create_incident_record` tool never performs remediation - by design, not as a gap to fill in later without also revisiting the confirmation and authorization model.
- `get_resource_status` and `get_alarm_details`'s simulated-data lookups use a bounded DynamoDB `Scan` rather than a `Query` (documented in-code) - fine for the small demo dataset; add a GSI keyed by `alarm_name`/`resource_identifier` before scaling the simulated dataset significantly.
- `get_recent_events`'s live-diagnostics path uses CloudTrail `LookupEvents`, which only covers the last 90 days and is not a full application-event history - it's deliberately bounded and read-only rather than exposing an unrestricted log search, per the project's security requirements.
- No automated `terraform plan`/`apply` has been run against a real AWS account as part of building this project (no valid credentials were available) - `terraform validate` and the static safety tests in `tests/test_terraform_plan_safety.py` are the strongest checks performed. Run a full `terraform plan` yourself before the first `apply` and review it.

## Production-hardening recommendations

- Set `cost_profile = "production"` and review the resulting forced-on settings (`terraform/locals.tf`).
- Set `use_customer_managed_kms = true` if your compliance posture requires customer-managed keys.
- Consider `enable_private_networking = true` and a VPC-attached configuration if your organization requires private connectivity to AgentCore Runtime/Gateway.
- Increase `trace_sampling_percentage` and `cloudwatch_log_retention_days` for stronger security-event visibility.
- Replace the demo Cognito users/passwords with your real identity provider integration - the demo users exist purely to exercise the authorization model in this repository.
- Review and tighten the `LiveReadOnlyDiagnostics` IAM statement (`terraform/lambda-tools.tf`) to specific resource ARNs if you enable `enable_live_aws_diagnostics` at scale.
