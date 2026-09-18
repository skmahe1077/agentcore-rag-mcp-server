# Architecture

## Logical architecture

```text
Cloud Engineer
    |
Authenticated Demo Client (app/client/demo_client.py)
    |  Cognito ID token (bearer)
Amazon Bedrock AgentCore Runtime (consumption-based microVM)
    |
Cloud Operations Runbook Agent (app/agent, Strands Agents)
    |
Amazon Bedrock Foundation Model (configurable - see COST.md)
    |
Amazon Bedrock AgentCore Gateway (MCP endpoint, JWT-authorized)
    |
MCP Tools (7 Lambda functions, terraform/lambda-tools.tf)
    |
    +-- check_operator_permissions
    +-- search_runbooks
    +-- get_alarm_details
    +-- get_resource_status
    +-- get_recent_events
    +-- create_incident_record
    +-- submit_feedback
    |
Amazon Bedrock Knowledge Base
    |
Amazon S3 (documents) + Amazon S3 Vectors (vector index)

                     DynamoDB (single table): entitlements, simulated
                     evidence, incidents, idempotency records, feedback
```

Every tool call re-derives authorization from DynamoDB by `user_id` (`app/mcp_server/security.py::resolve_entitlement`) - the model's own claims about a user's role are never trusted. See SECURITY.md for the full authorization model.

## Why S3 Vectors is the default vector store

Confirmed via the live AWS docs (`s3-vectors-regions-quotas.html`) that S3 Vectors is available in `eu-west-1`, and confirmed via the installed `hashicorp/aws` Terraform provider (≥6.x) that `aws_bedrockagent_knowledge_base` supports an `s3_vectors_configuration` storage block. S3 Vectors has no minimum billable compute capacity - you pay for stored vectors and queries, nothing while idle. For a demonstration with a handful of documents and light query volume, this is materially cheaper than the alternative.

## Why OpenSearch Serverless is optional, not default

Amazon OpenSearch Serverless bills for a minimum OCU (OpenSearch Compute Unit) footprint even when idle. For a demo with ~10 documents and occasional queries, that minimum footprint costs far more than the workload justifies. `terraform/optional-opensearch-serverless.tf` implements it fully, gated behind two variables that must both be set explicitly:

```hcl
vector_store_backend         = "opensearch_serverless"
enable_opensearch_serverless = true
```

When either is left at its default, **no** OpenSearch Serverless resource (collection, security policy, network policy, access policy, or related IAM) is created - verified by `tests/test_terraform_plan_safety.py`.

Consider switching to OpenSearch Serverless when you have:
- a genuine need for hybrid (keyword + vector) search - S3 Vectors supports semantic search only;
- high, sustained query throughput where OpenSearch's performance characteristics matter;
- complex metadata filtering beyond S3 Vectors' per-vector limits (35 metadata keys, 1KB filterable metadata);
- large-scale retrieval beyond what a per-vector metadata budget comfortably supports;
- existing OpenSearch operational expertise and infrastructure you want to consolidate onto.

OpenSearch Serverless is not required for "production readiness" - it is a scaling and feature choice you make when you have a measured need for it.

## Infrastructure intentionally not created by default

The demo profile never creates: a NAT Gateway, an EKS cluster, EC2 instances, an Application Load Balancer, an Auto Scaling group, an RDS/Aurora cluster, provisioned DynamoDB capacity, an OpenSearch Serverless collection, a provisioned OpenSearch domain, long-running container services, AgentCore instance-based compute, multiple vector stores, unnecessary VPC endpoints, or continuously running monitoring components. Verified by `tests/test_terraform_plan_safety.py` (static checks) and intended to be additionally verified by `terraform plan` in CI once AWS credentials are available.

## Deployment profiles

Both profiles use the **same** agent code and MCP tool schemas - only Terraform variables differ.

| | Demo (`cost_profile = "demo"`) | Production (`cost_profile = "production"`) |
|---|---|---|
| Vector store | S3 Vectors | S3 Vectors or OpenSearch Serverless, based on measured need |
| Operational evidence | Simulated (DynamoDB) | Live read-only AWS diagnostic APIs (same MCP schemas) |
| Encryption | AWS-owned keys | Customer-managed KMS (`use_customer_managed_kms = true`) |
| Log retention | 7 days | Configurable, typically longer |
| Deletion protection | Disabled | Enabled automatically (`local.effective_deletion_protection`) |
| Point-in-time recovery | Disabled | Enabled automatically (`local.effective_point_in_time_recovery`) |
| Networking | AWS-managed public endpoints | Optional private networking (`enable_private_networking`) |
| Tracing | Sampled (10%) | Configurable, typically higher |

Switch profiles with `cost_profile = "production"` in `terraform.tfvars`; several other variables (`enable_point_in_time_recovery`, `enable_deletion_protection`) are then forced on regardless of their own setting - see `terraform/locals.tf`.

## Data flow: an investigation request

```text
User request (bearer token)
    |
AgentCore Runtime validates JWT (custom_jwt_authorizer, Cognito discovery URL)
    |
Agent (app/agent/main.py) re-validates JWT independently (defense in depth)
    |
Agent calls check_operator_permissions via Gateway
    |  MCP tool re-derives role/permissions from DynamoDB by user_id
    |  Gateway independently confirms the caller's identity matches the
    |  tool-call arguments (enforce_identity_binding)
    |
Agent calls get_alarm_details, get_resource_status, get_recent_events
    |  (simulated by default; identical schema for live diagnostics)
    |
Agent calls search_runbooks
    |  Classification filter built from the caller's DynamoDB entitlement,
    |  applied to the Bedrock Retrieve call, then re-checked on every
    |  returned result (defense in depth)
    |
Foundation model produces a structured result
    |  (IncidentInvestigationResult: observations, possible_causes,
    |  recommendations, assumptions, citations, simulated_evidence_used)
    |
Response returned to the client, correlation ID and metrics logged
```

## Terraform structure

```text
terraform/
├── versions.tf                          Provider version constraints
├── providers.tf                         Provider configuration + default tags
├── variables.tf                         All configurable inputs
├── locals.tf                            Derived values (name prefix, effective flags)
├── data.tf                              Account ID, region, partition
├── budgets.tf                           AWS Budgets
├── s3.tf                                Document + artifact buckets
├── s3-vectors.tf                        S3 Vectors bucket + index (default backend)
├── bedrock-knowledge-base.tf            Knowledge Base + data source
├── cognito.tf                           User pool, app client, demo users
├── dynamodb.tf                          Single-table state store
├── lambda-tools.tf                      7 MCP tool Lambda functions + layer
├── agentcore.tf                         AgentCore Runtime + Gateway + targets
├── iam.tf                               All IAM roles/policies (least-privilege, separated by execution context)
├── observability.tf                     Log metric filters, alarms, dashboard
├── optional-kms.tf                      Customer-managed KMS key (opt-in)
├── optional-opensearch-serverless.tf    OpenSearch Serverless backend (opt-in)
└── outputs.tf                           Values scripts/ consume via `terraform output`
```

## Application structure

```text
app/
├── agent/            Strands-based agent, AgentCore Runtime entrypoint
├── mcp_server/        7 MCP tools + shared security/config/logging, local dev MCP server
└── client/            Authenticated demo client
```
