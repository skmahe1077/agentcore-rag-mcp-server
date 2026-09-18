#!/usr/bin/env bash
# Prints a qualitative cost assessment for the demo profile before you run
# `terraform apply`. Deliberately does not invent exact prices - AWS
# pricing changes over time and varies by region/account. For actual
# numbers, use:
#   - AWS Pricing Calculator: https://calculator.aws
#   - Infracost (if installed): infracost breakdown --path terraform
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cat <<'EOF'
Cost assessment - cloud-operations-runbook-assistant (demo profile)
=====================================================================
This is a qualitative assessment. Get exact numbers from AWS Pricing
Calculator (https://calculator.aws) or Infracost before approving spend.

| Billable service          | Pricing dimension                          | Idle cost                    | Expected demo usage                | Major cost driver                  | Cleanup requirement              | Lower-cost alternative                  |
|----------------------------|---------------------------------------------|-------------------------------|-------------------------------------|-------------------------------------|-----------------------------------|-------------------------------------------|
| Bedrock (foundation model) | Per input/output token                      | None                          | A handful of investigations/day     | Output token volume                 | None (no idle resource)           | Smaller/cheaper model via foundation_model_id |
| Bedrock (embeddings)       | Per input token, at ingestion + query time  | None                          | One-time ingestion of ~10 documents | Re-ingesting large corpora often    | None                              | Lower embedding_dimensions (256 vs 1024)  |
| S3 (documents)             | Storage (GB-month) + requests               | Storage of a few small MB     | Negligible                          | N/A at this scale                   | scripts/destroy.sh empties bucket | N/A - already minimal                     |
| S3 Vectors                 | Storage + query requests                    | Storage of small vector index | A few dozen queries/day             | N/A at this scale                   | scripts/destroy.sh                | N/A - already the low-cost default        |
| Bedrock Knowledge Bases    | Ingestion job compute (per run)             | None                          | Occasional re-sync after doc edits  | Frequent re-ingestion               | Deleted with the KB               | N/A                                        |
| AgentCore Runtime          | Consumption-based, per invocation duration  | None (no idle microVM)        | A handful of investigations/day     | Long-running or looping invocations | scripts/destroy.sh                | N/A - already consumption-based           |
| AgentCore Gateway          | Per request                                 | None                          | A few tool calls per investigation  | High-frequency polling clients      | scripts/destroy.sh                | N/A                                        |
| Lambda (7 MCP tools)       | Per invocation + GB-second                  | None                          | A few tool calls per investigation  | N/A at this scale                   | scripts/destroy.sh                | N/A - already minimal (256MB, ARM64)      |
| DynamoDB                   | On-demand read/write request units          | Storage of demo data only     | Light read/write traffic            | N/A at this scale                   | scripts/destroy.sh                | N/A - already on-demand                   |
| Cognito                    | Monthly active users beyond free tier       | None                          | 2 demo users                        | N/A at this scale                   | scripts/destroy.sh                | N/A - well within free tier               |
| CloudWatch Logs/Dashboard  | Ingestion + storage + dashboard count       | A few cents/month             | Low log volume                      | enable_debug_logging left on        | scripts/destroy.sh                | Shorter cloudwatch_log_retention_days     |
| CloudWatch Alarms          | Per alarm-month                             | A few cents/month             | Fixed alarm count                   | N/A                                  | scripts/destroy.sh                | N/A - already minimal alarm set           |
| ECR                        | Storage (GB-month)                          | Storage of 1 container image  | Occasional rebuilds                 | Accumulating old image versions     | Lifecycle policy + destroy.sh     | ECR lifecycle policy already caps at 5    |
| CloudTrail                 | Management events                           | Free for the first trail      | N/A                                  | N/A                                  | N/A                                | N/A                                        |
| AWS Budgets                | First 2 budgets free                        | Free                          | N/A                                  | N/A                                  | scripts/destroy.sh                | N/A                                        |

Explicit alternatives comparison (see ARCHITECTURE.md for when to switch):

| Component             | Demo default                        | Optional alternative                | Why the alternative costs more            |
| ---------------------- | ------------------------------------ | ------------------------------------ | ------------------------------------------ |
| Vector storage         | S3 Vectors                           | OpenSearch Serverless                | Minimum billable OCU capacity even idle    |
| Compute                | AgentCore consumption-based Runtime  | AgentCore Runtime Instances          | Reserved, continuously-billed capacity     |
| Tool execution         | Lambda on demand                     | A long-running container service     | Pays for idle time between invocations     |
| Operational evidence   | Simulated DynamoDB data              | Live AWS diagnostic APIs             | Same AWS cost either way, but adds API load |
| Encryption             | AWS-owned keys                       | Customer-managed KMS                 | Per-key monthly charge + per-request charge |
| Observability          | Sampled traces (10%)                 | Full tracing (100%)                  | Proportionally more trace storage/ingestion |

No NAT Gateway, no EC2, no continuously-running compute, no OpenSearch Serverless,
and no provisioned DynamoDB/Lambda capacity are created by this project's demo
profile - see ARCHITECTURE.md's "Infrastructure that must not be created by
default" section.
EOF

if command -v infracost >/dev/null 2>&1; then
  echo
  echo "Infracost detected - running a breakdown (requires INFRACOST_API_KEY):"
  (cd "${REPO_ROOT}/terraform" && infracost breakdown --path .) || echo "Infracost run failed or is not configured; see https://www.infracost.io/docs/ for setup."
else
  echo
  echo "Infracost is not installed. Install it (https://www.infracost.io/docs/#quick-start) for an automated dollar estimate against this Terraform config."
fi
