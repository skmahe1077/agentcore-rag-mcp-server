# The 7 MCP tools as individual Lambda functions, each wrapped as one
# AgentCore Gateway MCP target (agentcore.tf). ARM64, minimum practical
# memory, short timeouts, no provisioned concurrency, no VPC attachment -
# cost-effective on-demand execution for short-running tools.
#
# Dependencies are a Lambda layer built by scripts/build_lambda_packages.sh
# (Terraform cannot cross-compile Python wheels for a different
# architecture); the tool code itself is zipped declaratively below.

data "archive_file" "mcp_tools_code" {
  type        = "zip"
  output_path = "${path.module}/../build/mcp_tools_code.zip"

  dynamic "source" {
    for_each = fileset("${path.module}/../app/mcp_server", "**/*.py")
    content {
      content  = file("${path.module}/../app/mcp_server/${source.value}")
      filename = "app/mcp_server/${source.value}"
    }
  }

  source {
    content  = file("${path.module}/../app/__init__.py")
    filename = "app/__init__.py"
  }
}

data "archive_file" "mcp_tools_layer" {
  type        = "zip"
  source_dir  = "${path.module}/../build/lambda-layer"
  output_path = "${path.module}/../build/lambda-layer.zip"
}

resource "aws_lambda_layer_version" "mcp_tools_dependencies" {
  layer_name               = "${local.name_prefix}-mcp-tools-deps"
  compatible_runtimes      = ["python3.12"]
  compatible_architectures = ["arm64"]
  filename                 = data.archive_file.mcp_tools_layer.output_path
  source_code_hash         = data.archive_file.mcp_tools_layer.output_base64sha256
}

# ---------------------------------------------------------------------------
# Shared execution role for all 7 tool functions - separate from the
# AgentCore Runtime role and the Gateway role (iam.tf).
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "lambda_tools_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda_tools" {
  name               = "${local.name_prefix}-lambda-tools-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_tools_assume_role.json
  tags               = local.common_tags
}

data "aws_iam_policy_document" "lambda_tools_permissions" {
  statement {
    sid    = "Logging"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["arn:${local.partition}:logs:${local.region}:${local.account_id}:log-group:/aws/lambda/${local.lambda_name_prefix}-*"]
  }

  statement {
    sid    = "DynamoDbAccess"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:Query",
      "dynamodb:Scan",
    ]
    resources = [aws_dynamodb_table.main.arn, "${aws_dynamodb_table.main.arn}/index/*"]
  }

  statement {
    sid       = "KnowledgeBaseRetrieval"
    effect    = "Allow"
    actions   = ["bedrock:Retrieve"]
    resources = [aws_bedrockagent_knowledge_base.runbooks.arn]
  }

  # Read-only live-diagnostics permissions, used only when
  # enable_live_aws_diagnostics = true; harmless (and unused) otherwise
  # since the tools default to simulated data.
  statement {
    sid    = "LiveReadOnlyDiagnostics"
    effect = "Allow"
    actions = [
      "cloudwatch:DescribeAlarms",
      "elasticloadbalancing:DescribeLoadBalancers",
      "elasticloadbalancing:DescribeTargetGroups",
      "elasticloadbalancing:DescribeTargetHealth",
      "ec2:DescribeInstances",
      "autoscaling:DescribeAutoScalingGroups",
      "lambda:GetFunction",
      "rds:DescribeDBInstances",
      "cloudtrail:LookupEvents",
    ]
    resources = ["*"]
  }

  dynamic "statement" {
    for_each = var.use_customer_managed_kms ? [1] : []
    content {
      sid       = "KmsForDynamoDb"
      effect    = "Allow"
      actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
      resources = [local.kms_key_arn]
    }
  }
}

resource "aws_iam_role_policy" "lambda_tools" {
  name   = "${local.name_prefix}-lambda-tools-policy"
  role   = aws_iam_role.lambda_tools.id
  policy = data.aws_iam_policy_document.lambda_tools_permissions.json
}

# ---------------------------------------------------------------------------
# One Lambda function per MCP tool.
# ---------------------------------------------------------------------------

locals {
  mcp_tools = {
    check_operator_permissions = { handler = "app.mcp_server.tools.check_operator_permissions.lambda_handler", timeout = 5 }
    search_runbooks            = { handler = "app.mcp_server.tools.search_runbooks.lambda_handler", timeout = 10 }
    get_alarm_details          = { handler = "app.mcp_server.tools.get_alarm_details.lambda_handler", timeout = 8 }
    get_resource_status        = { handler = "app.mcp_server.tools.get_resource_status.lambda_handler", timeout = 8 }
    get_recent_events          = { handler = "app.mcp_server.tools.get_recent_events.lambda_handler", timeout = 8 }
    create_incident_record     = { handler = "app.mcp_server.tools.create_incident_record.lambda_handler", timeout = 5 }
    submit_feedback            = { handler = "app.mcp_server.tools.submit_feedback.lambda_handler", timeout = 5 }
  }

  # Lambda function names are capped at 64 characters. The longest tool
  # suffix ("-check-operator-permissions") is 27 chars, so the prefix must
  # be truncated to at most 37 to always fit, regardless of how long
  # var.project_name/var.environment end up being.
  lambda_name_prefix = substr(local.name_prefix, 0, 36)
}

resource "aws_lambda_function" "mcp_tools" {
  for_each = local.mcp_tools

  function_name = "${local.lambda_name_prefix}-${replace(each.key, "_", "-")}"
  role          = aws_iam_role.lambda_tools.arn
  handler       = each.value.handler
  runtime       = "python3.12"
  architectures = ["arm64"]
  memory_size   = 256
  timeout       = each.value.timeout

  filename         = data.archive_file.mcp_tools_code.output_path
  source_code_hash = data.archive_file.mcp_tools_code.output_base64sha256
  layers           = [aws_lambda_layer_version.mcp_tools_dependencies.arn]

  reserved_concurrent_executions = -1 # no reservation - shares the account's unreserved pool

  environment {
    # AWS_REGION is provided automatically by the Lambda runtime and must
    # not be set here - Lambda rejects environment variables prefixed
    # "AWS_" as reserved.
    variables = {
      TABLE_NAME                     = aws_dynamodb_table.main.name
      KNOWLEDGE_BASE_ID              = aws_bedrockagent_knowledge_base.runbooks.id
      USE_SIMULATED_OPERATIONAL_DATA = tostring(var.use_simulated_operational_data)
      ENABLE_LIVE_AWS_DIAGNOSTICS    = tostring(var.enable_live_aws_diagnostics)
      RETRIEVAL_RESULTS              = tostring(var.retrieval_results)
      MAX_RETRIEVAL_RESULTS_CAP      = "10"
      ENABLE_DEBUG_LOGGING           = tostring(var.enable_debug_logging)
    }
  }

  tracing_config {
    mode = "Active"
  }

  tags = merge(local.common_tags, { Name = "${local.name_prefix}-${each.key}" })
}

resource "aws_cloudwatch_log_group" "mcp_tools" {
  for_each = local.mcp_tools

  # Derived from the function's own name (not recomputed from
  # lambda_name_prefix) so the two can never drift apart.
  name              = "/aws/lambda/${aws_lambda_function.mcp_tools[each.key].function_name}"
  retention_in_days = var.cloudwatch_log_retention_days
  kms_key_id        = var.use_customer_managed_kms ? local.kms_key_arn : null

  tags = local.common_tags
}
