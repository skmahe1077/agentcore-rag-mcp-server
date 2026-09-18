# Structured JSON logs (app/mcp_server/logging_config.py) flow into the
# Lambda tool log groups created in lambda-tools.tf; this file adds metric
# filters and alarms on top of them, plus native Lambda/DynamoDB metrics,
# and a dashboard tying it together. AgentCore Runtime/Gateway themselves
# emit metrics and sampled OpenTelemetry traces automatically once the
# AgentCore Observability feature is enabled for the account/region
# (confirmed available in eu-west-1 - see the region-support table in the
# project's implementation notes) - no separate Terraform resource creates
# that pipeline. The AgentCore Runtime's own CloudWatch log group name is
# assigned by the service at deploy time; once known (visible in the
# console or `aws bedrock-agentcore-control get-agent-runtime`), add a
# metric filter for it the same way as below - see OBSERVABILITY.md.

resource "aws_sns_topic" "alarms" {
  name              = "${local.name_prefix}-alarms"
  kms_master_key_id = var.use_customer_managed_kms ? local.kms_key_arn : "alias/aws/sns"

  tags = local.common_tags
}

resource "aws_sns_topic_subscription" "alarms_email" {
  count = length(var.budget_alert_email) > 0 ? 1 : 0

  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email"
  endpoint  = var.budget_alert_email
}

# ---------------------------------------------------------------------------
# Log-derived metrics from the MCP tools' structured JSON logs
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_log_metric_filter" "authorization_denied" {
  for_each = local.mcp_tools

  name           = "${local.name_prefix}-${each.key}-authz-denied"
  log_group_name = aws_cloudwatch_log_group.mcp_tools[each.key].name
  pattern        = "{ $.message = \"authorization_decision\" && $.allowed = false }"

  # CloudWatch Logs Metric Filter dimension *values* must be selectors
  # extracted from the log event (e.g. "$.field"), not arbitrary literal
  # strings (confirmed against the live API: "dimension value must be a
  # valid selector"). Each filter is already scoped to one tool's log
  # group, so there's no need for a dimension here - the tool identity is
  # encoded in the metric name instead.
  metric_transformation {
    name      = "AuthorizationDenied_${each.key}"
    namespace = "${local.name_prefix}/mcp-tools"
    value     = "1"
    unit      = "Count"
  }
}

resource "aws_cloudwatch_log_metric_filter" "tool_errors" {
  for_each = local.mcp_tools

  name           = "${local.name_prefix}-${each.key}-errors"
  log_group_name = aws_cloudwatch_log_group.mcp_tools[each.key].name
  pattern        = "{ $.level = \"ERROR\" }"

  metric_transformation {
    name      = "ToolLoggedErrors_${each.key}"
    namespace = "${local.name_prefix}/mcp-tools"
    value     = "1"
    unit      = "Count"
  }
}

resource "aws_cloudwatch_metric_alarm" "authorization_denied_spike" {
  alarm_name          = "${local.name_prefix}-authorization-denied-spike"
  alarm_description   = "Elevated rate of authorization denials across MCP tools - may indicate a misconfigured client or an attempted unauthorized access pattern."
  evaluation_periods  = 1
  threshold           = 10
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
  ok_actions          = [aws_sns_topic.alarms.arn]

  # AuthorizationDenied_<tool> is published as a separate metric name per
  # tool (see the log metric filter above - dimensions aren't usable here).
  # Sum across all 7 per-tool metrics with metric math.
  metric_query {
    id          = "total"
    expression  = "SUM(METRICS())"
    label       = "Total authorization denials"
    return_data = true
  }

  dynamic "metric_query" {
    for_each = local.mcp_tools
    content {
      id          = "m_${replace(metric_query.key, "-", "_")}"
      return_data = false

      metric {
        namespace   = "${local.name_prefix}/mcp-tools"
        metric_name = "AuthorizationDenied_${metric_query.key}"
        period      = 300
        stat        = "Sum"
      }
    }
  }

  tags = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "mcp_tool_failures" {
  for_each = local.mcp_tools

  alarm_name          = "${local.name_prefix}-${each.key}-failures"
  alarm_description   = "Elevated Lambda errors for the ${each.key} MCP tool."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = aws_lambda_function.mcp_tools[each.key].function_name }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 5
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
  ok_actions          = [aws_sns_topic.alarms.arn]

  tags = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "mcp_tool_timeouts" {
  for_each = local.mcp_tools

  alarm_name          = "${local.name_prefix}-${each.key}-high-latency"
  alarm_description   = "The ${each.key} MCP tool is running close to its configured timeout - a leading indicator of repeated timeouts."
  namespace           = "AWS/Lambda"
  metric_name         = "Duration"
  dimensions          = { FunctionName = aws_lambda_function.mcp_tools[each.key].function_name }
  extended_statistic  = "p99"
  period              = 300
  evaluation_periods  = 1
  threshold           = each.value.timeout * 1000 * 0.8 # 80% of the configured timeout, in milliseconds
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
  ok_actions          = [aws_sns_topic.alarms.arn]

  tags = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "dynamodb_throttles" {
  alarm_name          = "${local.name_prefix}-dynamodb-throttles"
  alarm_description   = "DynamoDB requests are being throttled - unexpected on-demand capacity, investigate hot-key access patterns."
  namespace           = "AWS/DynamoDB"
  metric_name         = "ThrottledRequests"
  dimensions          = { TableName = aws_dynamodb_table.main.name }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 5
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
  ok_actions          = [aws_sns_topic.alarms.arn]

  tags = local.common_tags
}

# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "${local.name_prefix}-dashboard"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title   = "MCP tool invocations"
          region  = local.region
          stat    = "Sum"
          period  = 300
          metrics = [for name, fn in aws_lambda_function.mcp_tools : ["AWS/Lambda", "Invocations", "FunctionName", fn.function_name, { label = name }]]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title   = "MCP tool errors"
          region  = local.region
          stat    = "Sum"
          period  = 300
          metrics = [for name, fn in aws_lambda_function.mcp_tools : ["AWS/Lambda", "Errors", "FunctionName", fn.function_name, { label = name }]]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6
        properties = {
          title   = "MCP tool duration (p99)"
          region  = local.region
          stat    = "p99"
          period  = 300
          metrics = [for name, fn in aws_lambda_function.mcp_tools : ["AWS/Lambda", "Duration", "FunctionName", fn.function_name, { label = name }]]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "Authorization denials"
          region = local.region
          stat   = "Sum"
          period = 300
          # AuthorizationDenied_<tool> is a separate metric name per tool
          # (see the log metric filter above - dimensions aren't usable here).
          metrics = [for name, fn in aws_lambda_function.mcp_tools : ["${local.name_prefix}/mcp-tools", "AuthorizationDenied_${name}", { label = name }]]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 12
        width  = 12
        height = 6
        properties = {
          title  = "DynamoDB capacity and throttling"
          region = local.region
          stat   = "Sum"
          period = 300
          metrics = [
            ["AWS/DynamoDB", "ThrottledRequests", "TableName", aws_dynamodb_table.main.name],
            ["AWS/DynamoDB", "ConsumedReadCapacityUnits", "TableName", aws_dynamodb_table.main.name],
            ["AWS/DynamoDB", "ConsumedWriteCapacityUnits", "TableName", aws_dynamodb_table.main.name],
          ]
        }
      },
      {
        type   = "log"
        x      = 12
        y      = 12
        width  = 12
        height = 6
        properties = {
          title  = "Recent authorization decisions"
          region = local.region
          query  = "SOURCE '${aws_cloudwatch_log_group.mcp_tools["check_operator_permissions"].name}' | fields @timestamp, correlation_id, allowed, role, environment, requested_action | sort @timestamp desc | limit 20"
        }
      }
    ]
  })
}
