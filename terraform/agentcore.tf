# AgentCore Runtime hosts the agent container as a consumption-based
# microVM - no continuously running compute, no instance-based Runtime
# compute (see variables.tf / ARCHITECTURE.md for the cost-profile
# rationale). AgentCore Gateway federates the 7 Lambda-backed MCP tools
# (lambda-tools.tf) into one MCP endpoint the agent connects to.

resource "aws_ecr_repository" "agent" {
  name                 = "${local.name_prefix}-agent"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = var.use_customer_managed_kms ? "KMS" : "AES256"
    kms_key         = var.use_customer_managed_kms ? local.kms_key_arn : null
  }

  tags = merge(local.common_tags, { Name = "${local.name_prefix}-agent" })
}

resource "aws_ecr_lifecycle_policy" "agent" {
  repository = aws_ecr_repository.agent.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images after 7 days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 7
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Keep only the 5 most recent tagged images"
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = ["v", "latest"]
          countType     = "imageCountMoreThan"
          countNumber   = 5
        }
        action = { type = "expire" }
      }
    ]
  })
}

# ---------------------------------------------------------------------------
# AgentCore Runtime
# ---------------------------------------------------------------------------

resource "aws_bedrockagentcore_agent_runtime" "assistant" {
  agent_runtime_name = replace("${local.name_prefix}-agent", "-", "_")
  description        = "Cloud Operations Runbook Assistant agent."
  role_arn           = aws_iam_role.agent_runtime.arn

  agent_runtime_artifact {
    container_configuration {
      container_uri = "${aws_ecr_repository.agent.repository_url}:${var.agent_image_tag}"
    }
  }

  network_configuration {
    network_mode = "PUBLIC"
  }

  protocol_configuration {
    server_protocol = "HTTP"
  }

  authorizer_configuration {
    custom_jwt_authorizer {
      discovery_url   = local.cognito_discovery_url
      allowed_clients = [aws_cognito_user_pool_client.demo.id]
    }
  }

  lifecycle_configuration {
    idle_runtime_session_timeout = var.agent_idle_session_timeout_seconds
    max_lifetime                 = var.agent_max_lifetime_seconds
  }

  environment_variables = {
    FOUNDATION_MODEL_ID       = var.foundation_model_id
    MAX_OUTPUT_TOKENS         = tostring(var.max_output_tokens)
    MAXIMUM_TOOL_CALLS        = tostring(var.maximum_tool_calls)
    MAXIMUM_AGENT_STEPS       = tostring(var.maximum_agent_steps)
    RETRIEVAL_RESULTS         = tostring(var.retrieval_results)
    GATEWAY_URL               = aws_bedrockagentcore_gateway.mcp.gateway_url
    COGNITO_DISCOVERY_URL     = local.cognito_discovery_url
    COGNITO_ISSUER            = local.cognito_issuer
    COGNITO_CLIENT_ID         = aws_cognito_user_pool_client.demo.id
    TRACE_SAMPLING_PERCENTAGE = tostring(var.trace_sampling_percentage)
    ENABLE_DEBUG_LOGGING      = tostring(var.enable_debug_logging)
  }

  tags = local.common_tags

  depends_on = [aws_iam_role_policy.agent_runtime]
}

resource "aws_bedrockagentcore_agent_runtime_endpoint" "assistant" {
  # Must match ^[a-zA-Z][a-zA-Z0-9_]{0,47}$ (letters/digits/underscore only,
  # max 48 chars, confirmed against the live API) - unlike most other names
  # in this project, hyphens are not allowed here.
  name             = replace("${local.name_prefix}-endpoint", "-", "_")
  agent_runtime_id = aws_bedrockagentcore_agent_runtime.assistant.agent_runtime_id
  description      = "Default endpoint for the Cloud Operations Runbook Assistant."

  tags = local.common_tags
}

# ---------------------------------------------------------------------------
# AgentCore Gateway - federates the 7 Lambda-backed MCP tools
# (lambda-tools.tf) into one MCP endpoint. Only the required capabilities
# are enabled (Runtime, Gateway, Identity, Observability) - no Memory,
# Browser, Code Interpreter, or semantic tool search for this small fixed
# toolset.
# ---------------------------------------------------------------------------

resource "aws_bedrockagentcore_gateway" "mcp" {
  name            = "${local.name_prefix}-gateway"
  description     = "MCP gateway exposing the cloud operations runbook assistant's tools."
  role_arn        = aws_iam_role.gateway.arn
  authorizer_type = "CUSTOM_JWT"
  protocol_type   = "MCP"

  authorizer_configuration {
    custom_jwt_authorizer {
      discovery_url   = local.cognito_discovery_url
      allowed_clients = [aws_cognito_user_pool_client.demo.id]
    }
  }

  protocol_configuration {
    mcp {
      instructions       = "Tools for investigating AWS incidents using approved runbooks and operational evidence."
      supported_versions = ["2025-06-18"]

      session_configuration {
        session_timeout_in_seconds = var.agent_idle_session_timeout_seconds
      }

      streaming_configuration {
        enable_response_streaming = true
      }
    }
  }

  tags = local.common_tags

  depends_on = [aws_iam_role_policy.gateway]
}

# Each tool's inputSchema, hand-maintained alongside app/mcp_server/schemas.py
# (the source of truth for validation) - keep the two in sync when a tool's
# input fields change. user_id is a flat field (not nested under an object)
# because this schema format can't express nested object properties
# (confirmed against the live API); it's present here as a defense-in-depth
# argument the model supplies, and app/mcp_server/security.py's
# enforce_identity_binding independently rejects a mismatch against the
# Gateway-authenticated caller.
locals {
  tool_schema_definitions = {
    check_operator_permissions = {
      description = "Check whether the current user is authorized for a requested action in a given environment."
      properties = [
        { name = "user_id", type = "string", required = true, description = "The caller's user_id." },
        { name = "environment", type = "string", required = true, description = "production or staging." },
        { name = "resource", type = "string", required = true, description = "The resource being acted on, e.g. a service name." },
        { name = "requested_action", type = "string", required = true, description = "e.g. read, write, create_incident_record." },
        { name = "correlation_id", type = "string", required = false, description = "The investigation's correlation_id, for cross-tool log tracing." },
      ]
    }
    search_runbooks = {
      description = "Search the approved runbook catalog, filtered to the caller's authorized classifications."
      properties = [
        { name = "query", type = "string", required = true, description = "Natural-language search query." },
        { name = "service", type = "string", required = true, description = "Service name, e.g. checkout." },
        { name = "environment", type = "string", required = true, description = "production or staging." },
        { name = "severity", type = "string", required = true, description = "SEV1-SEV4." },
        { name = "max_results", type = "number", required = false, description = "Maximum passages to return (default configured server-side)." },
        { name = "user_id", type = "string", required = true, description = "The calling user's user_id." },
        { name = "correlation_id", type = "string", required = false, description = "The investigation's correlation_id, for cross-tool log tracing." },
      ]
    }
    get_alarm_details = {
      description = "Get details for a named CloudWatch-style alarm (simulated by default)."
      properties = [
        { name = "alarm_name", type = "string", required = true },
        { name = "region", type = "string", required = true },
        { name = "user_id", type = "string", required = true, description = "The calling user's user_id." },
        { name = "correlation_id", type = "string", required = false, description = "The investigation's correlation_id, for cross-tool log tracing." },
      ]
    }
    get_resource_status = {
      description = "Get status for an allow-listed AWS resource type (application_load_balancer, target_group, ec2_instance, auto_scaling_group, lambda_function, rds_database)."
      properties = [
        { name = "resource_type", type = "string", required = true, description = "One of the allow-listed resource types." },
        { name = "resource_identifier", type = "string", required = true },
        { name = "region", type = "string", required = true },
        { name = "user_id", type = "string", required = true, description = "The calling user's user_id." },
        { name = "correlation_id", type = "string", required = false, description = "The investigation's correlation_id, for cross-tool log tracing." },
      ]
    }
    get_recent_events = {
      description = "Get a bounded list of approved operational events for a service/environment/time range."
      properties = [
        { name = "service", type = "string", required = true },
        { name = "environment", type = "string", required = true },
        { name = "start_time", type = "string", required = true, description = "ISO 8601 timestamp." },
        { name = "end_time", type = "string", required = true, description = "ISO 8601 timestamp." },
        { name = "user_id", type = "string", required = true, description = "The calling user's user_id." },
        { name = "correlation_id", type = "string", required = false, description = "The investigation's correlation_id, for cross-tool log tracing." },
      ]
    }
    create_incident_record = {
      description = "Create an incident record. Refuses unless confirmed_by_user is true and the caller's role allows writes."
      properties = [
        { name = "title", type = "string", required = true },
        { name = "severity", type = "string", required = true, description = "SEV1-SEV4." },
        { name = "affected_service", type = "string", required = true },
        { name = "summary", type = "string", required = true },
        { name = "evidence", type = "object", required = true, description = "Structured evidence supporting the incident." },
        { name = "confirmed_by_user", type = "boolean", required = true, description = "Must be true - set only after the user explicitly confirms in conversation." },
        { name = "idempotency_key", type = "string", required = true },
        { name = "user_id", type = "string", required = true, description = "The calling user's user_id." },
        { name = "correlation_id", type = "string", required = false, description = "The investigation's correlation_id, for cross-tool log tracing." },
      ]
    }
    submit_feedback = {
      description = "Submit bounded, redacted session feedback."
      properties = [
        { name = "session_id", type = "string", required = true },
        { name = "rating", type = "number", required = true, description = "1-5." },
        { name = "comments", type = "string", required = false },
        { name = "correlation_id", type = "string", required = false, description = "The investigation's correlation_id, for cross-tool log tracing." },
      ]
    }
  }
}

resource "aws_bedrockagentcore_gateway_target" "mcp_tools" {
  for_each = local.mcp_tools

  gateway_identifier = aws_bedrockagentcore_gateway.mcp.gateway_id
  name               = replace(each.key, "_", "-")
  description        = local.tool_schema_definitions[each.key].description

  credential_provider_configuration {
    gateway_iam_role {}
  }

  target_configuration {
    mcp {
      lambda {
        lambda_arn = aws_lambda_function.mcp_tools[each.key].arn

        tool_schema {
          inline_payload {
            name        = each.key
            description = local.tool_schema_definitions[each.key].description

            input_schema {
              type = "object"

              dynamic "property" {
                for_each = local.tool_schema_definitions[each.key].properties
                content {
                  name        = property.value.name
                  type        = property.value.type
                  required    = try(property.value.required, false)
                  description = try(property.value.description, null)
                }
              }
            }
          }
        }
      }
    }
  }
}
