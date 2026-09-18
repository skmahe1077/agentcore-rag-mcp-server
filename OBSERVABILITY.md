# Observability

## Correlation IDs

Every agent invocation gets a correlation ID (`app/agent/observability.py::new_correlation_id`, or the caller's own `correlation_id`/session ID if provided). It's set as a `contextvar` (`app/mcp_server/logging_config.py::set_correlation_id`) and included in every structured log line for that invocation, so you can trace one request across the agent, every tool call it made, and the retrieval it performed. `app/client/demo_client.py` prints it after every call.

## Structured logs

Every log line, from the agent and from every MCP tool, is one JSON object:

```json
{"timestamp": "...", "level": "INFO", "logger": "app.mcp_server.tools.search_runbooks", "message": "search_runbooks_completed", "correlation_id": "...", "user_id": "...", "role": "incident_commander", "result_count": 3}
```

This is queryable directly with CloudWatch Logs Insights - no custom parser needed. See SECURITY.md for what's redacted before it ever reaches this formatter.

## What gets measured

`app/agent/observability.py::InvocationMetrics` captures, per invocation: model duration, tool-call count, retrieved-source count, whether authorization was denied, whether the investigation was refused, MCP failure count, token usage (from the Strands `AgentResult.metrics`), and the model's stop reason. Logged once at `agent_invocation_completed`.

## Tracing

Sampled at `trace_sampling_percentage` (default 10%) - `app/agent/observability.py::should_sample_trace`. AgentCore Runtime and Gateway automatically emit OpenTelemetry-compatible traces once AgentCore Observability is enabled for the account/region (confirmed available in `eu-west-1`); no separate Terraform resource creates that pipeline - it comes from the IAM permissions already granted to the runtime/gateway roles (`terraform/iam.tf`) plus the `X-Amzn-Trace-Id`/`traceparent` headers the SDK propagates.

## Tool-call limiting as an observability signal

`app/agent/observability.py::ToolCallLimiter` is a Strands hook that counts every tool call and cancels further calls once `maximum_tool_calls` is reached, logging `tool_call_limit_reached` at WARNING. This is both a cost/reliability control (bounded tool-call budget per investigation) and a useful signal: a spike in this log message across invocations suggests the model is looping or the available tools aren't sufficient for the query pattern you're seeing.

## Metrics, alarms, and the dashboard

`terraform/observability.tf` derives CloudWatch metrics from the Lambda tools' structured logs via log metric filters (`AuthorizationDenied`, `ToolLoggedErrors`), and combines them with native Lambda/DynamoDB metrics. Alarms (all notify an SNS topic, emailed if `budget_alert_email` is set):

| Alarm | Signal | Threshold |
|---|---|---|
| `authorization-denied-spike` | Sum of authorization denials across all tools, 5 min | > 10 |
| `<tool>-failures` (×7) | Lambda `Errors`, 5 min | > 5 |
| `<tool>-high-latency` (×7) | Lambda `Duration` p99, 5 min | > 80% of that tool's configured timeout |
| `dynamodb-throttles` | DynamoDB `ThrottledRequests`, 5 min | > 5 |

The dashboard (`aws_cloudwatch_dashboard.main`, output as `dashboard_name`) shows invocation counts, error counts, and p99 duration for all 7 tools, authorization denials, DynamoDB capacity/throttling, and a Logs Insights widget of recent authorization decisions.

**AgentCore Runtime's own log group** is named by the service at deploy time, not by Terraform (there's no field on `aws_bedrockagentcore_agent_runtime` to set it). Once deployed, find it via the console or `aws bedrock-agentcore-control get-agent-runtime`, and add a metric filter for `agent_invocation_failed`/`agent_invocation_completed` the same way `terraform/observability.tf` does for the Lambda tools, if you want agent-level (not just tool-level) alarms.

## Viewing a single investigation end-to-end

1. Run a demo scenario (`scripts/run_demo.sh` or `app/client/demo_client.py` directly) and note the printed correlation ID.
2. CloudWatch Logs Insights, across the 7 tool log groups and (once known) the agent's own log group:
   ```
   fields @timestamp, logger, message, correlation_id, *
   | filter correlation_id = "<id>"
   | sort @timestamp asc
   ```
3. This shows, in order: the authorization check, each evidence-gathering tool call, the runbook retrieval (with its authorization_decision and citation count), and the final agent metrics.

## Cost-effective defaults

`cloudwatch_log_retention_days` (default 7) and `trace_sampling_percentage` (default 10%) both exist specifically to keep observability cost proportional to actual usage rather than defaulting to "log and trace everything forever" - see COST.md.
