# Cloud Operations Runbook Assistant

A secure, grounded, observable incident-support assistant for cloud and platform engineers, built on Amazon Bedrock AgentCore. It investigates AWS incidents by combining **RAG** over approved operational runbooks with **MCP** tools for operational evidence - all behind authenticated, authorized access, with citations, full observability, and human approval before any write action.

> Ask it: *"The production checkout service is returning HTTP 5xx errors. Help me investigate using the approved runbook."* See DEMO.md for the full walkthrough.

## What is RAG?

Retrieval-Augmented Generation: instead of relying on a foundation model's training data (which can be outdated, generic, or simply wrong for your environment), the system retrieves relevant passages from your **own, approved** documents at query time and grounds the model's answer in them, with citations. Here, that means Amazon Bedrock Knowledge Bases retrieving from your runbook catalog (`sample-data/`) stored in S3 and indexed in S3 Vectors - see "Why RAG implementation" below.

## What is MCP?

The Model Context Protocol: a standard way for an AI agent to discover and call external tools, independent of which model or framework the agent uses. Here, seven MCP tools (`app/mcp_server/tools/`) - permission checks, runbook search, alarm/resource/event lookups, incident creation, feedback - are each deployed as a Lambda function and exposed to the agent as one MCP endpoint via Amazon Bedrock AgentCore Gateway.

## What is AgentCore for?

Amazon Bedrock AgentCore is the managed layer that runs the agent (**Runtime**, a consumption-based microVM - no server to manage, no idle cost), federates its tools (**Gateway**, the MCP endpoint in front of the 7 Lambda tools), authenticates callers (**Identity**, via a JWT authorizer backed by Cognito), and captures what happened (**Observability**, structured logs and sampled traces). It replaces infrastructure you'd otherwise have to build and operate yourself for a production agent.

## Architecture

See ARCHITECTURE.md for the full diagram and component-by-component breakdown. In short:

```
Demo client → AgentCore Runtime → Agent (Strands) → Bedrock model
                                        |
                                  AgentCore Gateway → 7 Lambda MCP tools → DynamoDB
                                        |                                  + Bedrock Knowledge Base
                                        |                                    (S3 + S3 Vectors)
```

## Why S3 Vectors (and why OpenSearch Serverless is optional)

S3 Vectors is the default vector store because it has no minimum billable compute capacity - you pay for stored vectors and queries, nothing while idle, and it's confirmed available in `eu-west-1`. OpenSearch Serverless is fully implemented (`terraform/optional-opensearch-serverless.tf`) but **not created unless you explicitly opt in** (`vector_store_backend = "opensearch_serverless"` and `enable_opensearch_serverless = true`), because it bills a minimum OCU footprint even when idle - not cost-effective for a low-traffic demonstration. See ARCHITECTURE.md for when OpenSearch Serverless is the right call.

## Prerequisites

- Terraform ≥ 1.8, an AWS account with credentials configured (`aws sts get-caller-identity` should succeed), Docker (or Finch/Podman) for building the agent image, Python 3.12, `jq`.
- **Bedrock model access** requested in the console for your chosen foundation and embedding models (a manual, per-account step - Terraform cannot do this).
- Run `scripts/bootstrap.sh` to check all of the above and set up a Python virtual environment.

## Deployment

```bash
cp terraform/terraform.tfvars.example terraform/terraform.tfvars
# edit terraform.tfvars: confirm foundation_model_id / embedding_model_id
# against your account's Bedrock console, and set budget_alert_email

scripts/estimate_cost.sh   # read this before proceeding
make apply                 # scripts/deploy.sh: build+push image, terraform apply, ingest runbooks, seed data
make smoke-test
make demo
```

`make apply` runs `scripts/deploy.sh`, which handles the ECR chicken-and-egg problem (the agent container image must exist before the `agent_runtime` resource can reference it) by applying the ECR repository first, then building/pushing the image, then applying everything else. See TROUBLESHOOTING.md if any step fails, and its "integration points to verify" section for the handful of things not confirmed against a live AWS account while building this.

## Authentication

Two demo identities (`read_only_operator`, `incident_commander`) are created directly by Terraform in a Cognito user pool, with generated passwords exposed as a sensitive Terraform output. Get a bearer token with `scripts/get_demo_token.sh <read-only|incident-commander>` (writes to a local gitignored file, never prints your password). See SECURITY.md for the full authentication and authorization model - notably, **the model never decides who's authorized to do what**; every tool re-derives that from DynamoDB.

## Runbook ingestion

```bash
make upload-runbooks   # syncs sample-data/{runbooks,procedures,architecture,restricted}/ to S3
make sync-kb           # triggers and waits for a Knowledge Base ingestion job
```

Both run automatically as part of `make apply`; re-run them after editing anything in `sample-data/`.

## Demo

```bash
make demo
```

Runs all four scenarios from DEMO.md: a grounded investigation with citations, a restricted-content denial (including a prompt-injection attempt), human-approved incident creation, and an observability walkthrough. See DEMO.md for the exact prompts and expected behavior.

## Observability

Every invocation gets a correlation ID; every log line is structured JSON; a CloudWatch dashboard and alarm set cover tool errors, latency, authorization denials, and DynamoDB throttling. See OBSERVABILITY.md.

## Security

JWT authentication at two layers, DynamoDB-derived authorization at every tool (never trusting the model), untrusted-document handling with a working prompt-injection test, redacted structured logging, least-privilege IAM split across four execution contexts, and encryption at rest/in transit. See SECURITY.md for the complete picture.

## Scalability and reliability

AgentCore Runtime scales per-invocation (no capacity to plan for); Lambda tools have no reserved concurrency and share the account pool; DynamoDB is on-demand; all AWS SDK clients use bounded timeouts and bounded adaptive retries (`app/mcp_server/clients.py`); authorization and validation failures are never retried; `create_incident_record` is idempotent via a DynamoDB-backed idempotency key. `tests/test_reliability.py` verifies the timeout/retry bounds and the no-retry-on-auth-failure contract.

## Cost controls

AWS Budgets with actual/forecasted alerts, cost-allocation tags on every resource, configurable log retention and trace sampling, an ECR lifecycle policy, and on-demand billing everywhere applicable. Run `scripts/estimate_cost.sh` before you deploy and `scripts/list_billable_resources.sh` any time after. Full detail in COST.md.

## Cleanup

```bash
make destroy          # requires typing the project name to confirm
make verify-cleanup   # checks every resource type this project can create
```

## Troubleshooting, known limitations, and production hardening

See TROUBLESHOOTING.md - including the specific integration points (Gateway→Lambda event shape, AgentCore Runtime bearer-token passthrough, Bedrock retrieval filter operator semantics) that were built against documented API shapes but not confirmed against a live call, since no valid AWS credentials were available while building this project.

## Repository layout

```text
terraform/          All infrastructure (see ARCHITECTURE.md for the file-by-file breakdown)
app/agent/           The agent (Strands Agents, AgentCore Runtime entrypoint)
app/mcp_server/       7 MCP tools + shared security/config/logging
app/client/           Authenticated demo client
sample-data/         Runbooks, procedures, architecture docs, restricted docs, simulated evidence
scripts/             Deployment, demo, and operational scripts
tests/               62 tests covering authorization, retrieval filtering, prompt injection,
                     idempotency, JWT validation, reliability, logging redaction, and
                     Terraform-plan safety - no live AWS credentials required
```

## License

MIT - see LICENSE. Contributions welcome - see CONTRIBUTING.md.
