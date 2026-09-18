# Cost controls

This project is built to be cost-effective by default. This document explains what drives cost, what controls exist, and how to check spend before and after deploying.

## Before you deploy

Run:

```bash
make cost-estimate
# or directly:
scripts/estimate_cost.sh
```

This prints a qualitative cost breakdown (billable service, pricing dimension, idle cost, expected demo usage, major cost driver, cleanup requirement, lower-cost alternative) without inventing exact prices. For actual dollar figures, use the [AWS Pricing Calculator](https://calculator.aws) or [Infracost](https://www.infracost.io) (the script runs Infracost automatically if it's installed and configured).

## What the demo profile does NOT create

Per `ARCHITECTURE.md`, the demo profile never creates: a NAT Gateway, an EKS cluster, EC2 instances, an Application Load Balancer, an Auto Scaling group, an RDS/Aurora cluster, provisioned DynamoDB capacity, an OpenSearch Serverless collection, a provisioned OpenSearch domain, long-running container services, AgentCore instance-based compute, multiple vector stores, unnecessary VPC endpoints, or continuously running monitoring components. These are the components that typically dominate a demo's AWS bill, and none of them are present unless you explicitly opt into the production profile or `enable_opensearch_serverless`.

## What actually costs money

Everything billable in the demo profile is **consumption-based**: Bedrock model/embedding invocations, S3/S3 Vectors storage and requests, AgentCore Runtime/Gateway per-invocation charges, Lambda per-invocation charges, DynamoDB on-demand request units, and small fixed costs for CloudWatch log storage, alarms, and the dashboard. None of these accrue meaningfully while the system is idle - see `scripts/estimate_cost.sh` for the full table.

## Cost controls implemented

- **AWS Budgets** (`terraform/budgets.tf`): a monthly budget (`monthly_budget_limit`, default $20) with actual-spend notifications at 80% and 100%, and a forecasted-spend notification at 100%. Notifications only get created when `budget_alert_email` is set - **AWS Budgets sends alerts but does not automatically stop or delete resources.** If you need a hard spending cap, that requires separate automation (e.g. a Lambda triggered by a budget alarm) that this project does not implement.
- **Cost-allocation tags**: every resource carries `Project`, `Environment`, `CostProfile`, and `Application` tags (`terraform/locals.tf`), so Cost Explorer and `scripts/list_billable_resources.sh` can filter to exactly this project's spend.
- **Configurable log retention** (`cloudwatch_log_retention_days`, default 7 days) and **sampled tracing** (`trace_sampling_percentage`, default 10%) keep observability costs proportional to actual usage.
- **ECR lifecycle policy**: expires untagged images after 7 days and keeps only the 5 most recent tagged images, so repeated `scripts/deploy.sh` runs don't accumulate storage indefinitely.
- **DynamoDB on-demand billing**: no provisioned capacity to size or pay for while idle.
- **Lambda**: ARM64, 256MB memory, short timeouts, no provisioned concurrency, no VPC attachment - minimizes both per-invocation cost and idle cost (there is none).
- **AgentCore Runtime**: consumption-based microVMs with a bounded idle-session timeout (`agent_idle_session_timeout_seconds`) and maximum lifetime (`agent_max_lifetime_seconds`), so a stuck or abandoned session doesn't run indefinitely.

## Checking what's actually deployed

```bash
make list-billable-resources
# or directly:
scripts/list_billable_resources.sh
```

Lists every AWS resource tagged for this project, plus a few resource types (Cognito, ECR, S3 Vectors, AgentCore) that aren't always covered by the standard resource-tagging API.

## Cleanup

```bash
make destroy
make verify-cleanup
```

See `TROUBLESHOOTING.md` if `verify-cleanup` reports remaining resources after `destroy` completes.

## Demo vs. production cost tradeoffs

| Component | Demo default | Optional alternative | Why the alternative costs more |
|---|---|---|---|
| Vector storage | S3 Vectors | OpenSearch Serverless | Minimum billable OCU capacity even while idle |
| Compute | AgentCore consumption-based Runtime | AgentCore Runtime Instances | Reserved, continuously-billed capacity |
| Tool execution | Lambda on demand | A long-running container service | Pays for idle time between invocations |
| Operational evidence | Simulated DynamoDB data | Live AWS diagnostic APIs | Same AWS cost either way, but adds API load and diagnostic-permission scope |
| Encryption | AWS-owned keys | Customer-managed KMS | Per-key monthly charge plus per-request charge |
| Observability | Sampled traces (10%) | Full tracing (100%) | Proportionally more trace storage/ingestion |

Switch to the production profile (`cost_profile = "production"`) only when you have a measured, sustained need for the hardening it adds (point-in-time recovery, deletion protection, longer log retention) - see `ARCHITECTURE.md`.
