# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

variable "aws_region" {
  description = "AWS region to deploy into. S3 Vectors and AgentCore Runtime/Gateway/Identity/Observability are confirmed available in eu-west-1."
  type        = string
  default     = "eu-west-1"
}

variable "project_name" {
  description = "Project name used as a prefix for resource names and tags."
  type        = string
  default     = "cloud-operations-runbook-assistant"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,40}$", var.project_name))
    error_message = "project_name must be lowercase alphanumeric with hyphens, 3-41 characters, starting with a letter."
  }
}

variable "environment" {
  description = "Deployment environment name (demo, staging, production, ...)."
  type        = string
  default     = "demo"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,20}$", var.environment))
    error_message = "environment must be lowercase alphanumeric with hyphens, 2-21 characters."
  }
}

variable "cost_profile" {
  description = "Deployment cost profile. 'demo' avoids continuously running or oversized infrastructure. 'production' enables optional hardening (PITR, longer retention, deletion protection)."
  type        = string
  default     = "demo"

  validation {
    condition     = contains(["demo", "production"], var.cost_profile)
    error_message = "cost_profile must be 'demo' or 'production'."
  }
}

# ---------------------------------------------------------------------------
# Vector store
# ---------------------------------------------------------------------------

variable "vector_store_backend" {
  description = "Vector backend for the Bedrock Knowledge Base."
  type        = string
  default     = "s3_vectors"

  validation {
    condition = contains([
      "s3_vectors",
      "opensearch_serverless"
    ], var.vector_store_backend)

    error_message = "Supported values are s3_vectors and opensearch_serverless."
  }
}

variable "enable_opensearch_serverless" {
  description = "Deploy OpenSearch Serverless as an optional vector backend. Leave false for the demo profile - OpenSearch Serverless has a minimum billable OCU footprint that is not cost-effective for a low-traffic demonstration. See ARCHITECTURE.md for when to enable it."
  type        = bool
  default     = false
}

# ---------------------------------------------------------------------------
# Bedrock models
# ---------------------------------------------------------------------------

variable "foundation_model_id" {
  description = <<-EOT
    Bedrock model ID or inference-profile ID used by the agent for reasoning and response generation.
    Left blank intentionally: Bedrock model access is granted per-account via the console (a manual
    step - see README.md), and eu-west-1 requires an EU cross-region inference profile for most
    cost-effective chat models (e.g. eu.anthropic.claude-3-5-haiku-20241022-v1:0 or
    eu.amazon.nova-lite-v1:0). Confirm the exact ID for your account in the Bedrock console before
    setting this value.
  EOT
  type        = string
  default     = ""

  validation {
    condition     = length(var.foundation_model_id) > 0
    error_message = "Set foundation_model_id in terraform.tfvars after confirming Bedrock model access and the exact model/inference-profile ID for your account in the Bedrock console."
  }
}

variable "embedding_model_id" {
  description = "Bedrock embedding model ID used by the Knowledge Base. Default recommendation: amazon.titan-embed-text-v2:0 (confirmed available in-region in eu-west-1)."
  type        = string
  default     = ""

  validation {
    condition     = length(var.embedding_model_id) > 0
    error_message = "Set embedding_model_id in terraform.tfvars, e.g. amazon.titan-embed-text-v2:0."
  }
}

variable "embedding_dimensions" {
  description = "Output vector dimensions for the embedding model (Titan Embed Text v2 supports 256, 512, or 1024)."
  type        = number
  default     = 1024

  validation {
    condition     = contains([256, 512, 1024], var.embedding_dimensions)
    error_message = "embedding_dimensions must be 256, 512, or 1024."
  }
}

variable "max_output_tokens" {
  description = "Maximum output tokens the agent's foundation-model calls may generate."
  type        = number
  default     = 1200

  validation {
    condition     = var.max_output_tokens > 0 && var.max_output_tokens <= 4096
    error_message = "max_output_tokens must be between 1 and 4096."
  }
}

variable "retrieval_results" {
  description = "Number of passages retrieved from the Knowledge Base per query."
  type        = number
  default     = 4

  validation {
    condition     = var.retrieval_results > 0 && var.retrieval_results <= 20
    error_message = "retrieval_results must be between 1 and 20."
  }
}

variable "maximum_tool_calls" {
  description = "Maximum MCP tool calls allowed per agent invocation."
  type        = number
  default     = 8

  validation {
    condition     = var.maximum_tool_calls > 0 && var.maximum_tool_calls <= 25
    error_message = "maximum_tool_calls must be between 1 and 25."
  }
}

variable "maximum_agent_steps" {
  description = "Maximum reasoning/tool-use iterations allowed per agent invocation."
  type        = number
  default     = 10

  validation {
    condition     = var.maximum_agent_steps > 0 && var.maximum_agent_steps <= 25
    error_message = "maximum_agent_steps must be between 1 and 25."
  }
}

# ---------------------------------------------------------------------------
# Retrieval / chunking
# ---------------------------------------------------------------------------

variable "chunking_max_tokens" {
  description = "Maximum tokens per chunk when ingesting runbook documents into the Knowledge Base."
  type        = number
  default     = 300

  validation {
    condition     = var.chunking_max_tokens > 0 && var.chunking_max_tokens <= 8192
    error_message = "chunking_max_tokens must be between 1 and 8192."
  }
}

variable "chunking_overlap_percentage" {
  description = "Percentage overlap between consecutive chunks."
  type        = number
  default     = 20

  validation {
    condition     = var.chunking_overlap_percentage >= 0 && var.chunking_overlap_percentage < 100
    error_message = "chunking_overlap_percentage must be between 0 and 99."
  }
}

# ---------------------------------------------------------------------------
# Operational data
# ---------------------------------------------------------------------------

variable "use_simulated_operational_data" {
  description = "Use simulated alarm/resource/event data stored in DynamoDB instead of calling live AWS diagnostic APIs. Enabled by default for the demo."
  type        = bool
  default     = true
}

variable "enable_live_aws_diagnostics" {
  description = "Allow MCP tools to call live, read-only AWS diagnostic APIs (CloudWatch, ELB, EC2, Lambda, RDS) instead of/in addition to simulated data. The MCP tool schemas are identical either way."
  type        = bool
  default     = false
}

# ---------------------------------------------------------------------------
# Encryption
# ---------------------------------------------------------------------------

variable "use_customer_managed_kms" {
  description = "Use a customer-managed KMS key for S3, S3 Vectors, DynamoDB, and CloudWatch Logs encryption instead of AWS-owned/managed keys. AWS-owned keys are sufficient protection for the low-cost demo profile; a customer-managed key adds per-key and per-request KMS charges plus key-policy management overhead. See COST.md."
  type        = bool
  default     = false
}

variable "kms_deletion_window_in_days" {
  description = "Waiting period before a customer-managed KMS key is deleted, when use_customer_managed_kms is true."
  type        = number
  default     = 30

  validation {
    condition     = var.kms_deletion_window_in_days >= 7 && var.kms_deletion_window_in_days <= 30
    error_message = "kms_deletion_window_in_days must be between 7 and 30."
  }
}

# ---------------------------------------------------------------------------
# Deletion protection / backup
# ---------------------------------------------------------------------------

variable "enable_deletion_protection" {
  description = "Enable deletion protection on stateful resources (Knowledge Base data source deletion policy, DynamoDB table). Disabled by default so the demo profile can be cleanly destroyed."
  type        = bool
  default     = false
}

variable "enable_point_in_time_recovery" {
  description = "Enable DynamoDB point-in-time recovery. Recommended for the production profile; adds no charge unless a restore is performed, but is left off by default for the demo table's short-lived data."
  type        = bool
  default     = false
}

# ---------------------------------------------------------------------------
# Observability
# ---------------------------------------------------------------------------

variable "cloudwatch_log_retention_days" {
  description = "CloudWatch Logs retention, in days."
  type        = number
  default     = 7

  validation {
    condition = contains([
      1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731,
      1096, 1827, 2192, 2557, 2922, 3288, 3653, 0
    ], var.cloudwatch_log_retention_days)
    error_message = "cloudwatch_log_retention_days must be a value accepted by aws_cloudwatch_log_group (see AWS docs)."
  }
}

variable "trace_sampling_percentage" {
  description = "Percentage of agent invocations traced (0-100). Sampled tracing keeps observability cost-effective for a low-traffic demo."
  type        = number
  default     = 10

  validation {
    condition     = var.trace_sampling_percentage >= 0 && var.trace_sampling_percentage <= 100
    error_message = "trace_sampling_percentage must be between 0 and 100."
  }
}

variable "enable_debug_logging" {
  description = "Enable verbose debug logging in the agent and MCP tools. Keep false to avoid the risk of logging sensitive request/response detail."
  type        = bool
  default     = false
}

variable "enable_detailed_metrics" {
  description = "Enable higher-resolution/detailed CloudWatch metrics (additional cost) instead of standard metrics."
  type        = bool
  default     = false
}

# ---------------------------------------------------------------------------
# Cost controls
# ---------------------------------------------------------------------------

variable "monthly_budget_limit" {
  description = "Monthly AWS Budgets limit, in USD, for this project's tagged resources."
  type        = number
  default     = 20

  validation {
    condition     = var.monthly_budget_limit > 0
    error_message = "monthly_budget_limit must be greater than 0."
  }
}

variable "budget_alert_email" {
  description = "Email address for AWS Budgets actual/forecasted spend notifications. Leave empty to create the budget without an email subscriber (AWS Budgets tracks spend but does not stop resources automatically)."
  type        = string
  default     = ""
}

# ---------------------------------------------------------------------------
# AgentCore Runtime
# ---------------------------------------------------------------------------

variable "agent_image_tag" {
  description = "Tag of the agent container image in the project's ECR repository. scripts/deploy.sh builds and pushes this tag before the agent_runtime resource is applied."
  type        = string
  default     = "latest"
}

variable "agent_idle_session_timeout_seconds" {
  description = "AgentCore Runtime idle session timeout - bounds how long a warm microVM is kept for an inactive session."
  type        = number
  default     = 900

  validation {
    condition     = var.agent_idle_session_timeout_seconds > 0 && var.agent_idle_session_timeout_seconds <= 3600
    error_message = "agent_idle_session_timeout_seconds must be between 1 and 3600."
  }
}

variable "agent_max_lifetime_seconds" {
  description = "AgentCore Runtime maximum session lifetime, regardless of activity - a hard cost/runaway-session bound."
  type        = number
  default     = 3600

  validation {
    condition     = var.agent_max_lifetime_seconds > 0 && var.agent_max_lifetime_seconds <= 28800
    error_message = "agent_max_lifetime_seconds must be between 1 and 28800 (8 hours)."
  }
}

# ---------------------------------------------------------------------------
# Networking (optional production hardening)
# ---------------------------------------------------------------------------

variable "enable_private_networking" {
  description = "Optional production hardening: place the AgentCore Runtime/Gateway on a private VPC network configuration instead of the AWS-managed public endpoint. Not used by the demo profile."
  type        = bool
  default     = false
}
