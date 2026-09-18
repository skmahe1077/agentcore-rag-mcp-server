output "aws_region" {
  description = "AWS region resources were deployed into."
  value       = var.aws_region
}

output "runbook_documents_bucket" {
  description = "S3 bucket holding runbook/procedure/architecture/restricted documents - upload targets for scripts/upload_runbooks.sh."
  value       = aws_s3_bucket.runbook_documents.id
}

output "deployment_artifacts_bucket" {
  description = "S3 bucket for deployment artifacts."
  value       = aws_s3_bucket.deployment_artifacts.id
}

output "knowledge_base_id" {
  description = "Bedrock Knowledge Base ID - used by scripts/sync_knowledge_base.sh."
  value       = aws_bedrockagent_knowledge_base.runbooks.id
}

output "knowledge_base_data_source_id" {
  description = "Bedrock Knowledge Base data source ID."
  value       = aws_bedrockagent_data_source.runbooks.data_source_id
}

output "dynamodb_table_name" {
  description = "DynamoDB table name - used by scripts/seed_demo_events.sh."
  value       = aws_dynamodb_table.main.name
}

output "cognito_user_pool_id" {
  description = "Cognito User Pool ID."
  value       = aws_cognito_user_pool.main.id
}

output "cognito_user_pool_client_id" {
  description = "Cognito demo app client ID - used by scripts/get_demo_token.sh."
  value       = aws_cognito_user_pool_client.demo.id
}

output "cognito_discovery_url" {
  description = "OIDC discovery URL for the Cognito user pool."
  value       = local.cognito_discovery_url
}

output "demo_user_ids" {
  description = "user_id (Cognito username) for each demo identity."
  value       = [for user in local.demo_users : user.user_id]
}

output "demo_user_passwords" {
  description = "Generated passwords for demo Cognito users, keyed by user_id. Sensitive - consumed by scripts/get_demo_token.sh via `terraform output -json`, never printed directly."
  value       = { for k, v in random_password.demo_user : k => v.result }
  sensitive   = true
}

output "ecr_repository_url" {
  description = "ECR repository URL for the agent container image - used by scripts/deploy.sh."
  value       = aws_ecr_repository.agent.repository_url
}

output "agent_runtime_id" {
  description = "AgentCore Runtime ID."
  value       = aws_bedrockagentcore_agent_runtime.assistant.agent_runtime_id
}

output "agent_runtime_arn" {
  description = "AgentCore Runtime ARN."
  value       = aws_bedrockagentcore_agent_runtime.assistant.agent_runtime_arn
}

output "gateway_url" {
  description = "AgentCore Gateway MCP endpoint URL."
  value       = aws_bedrockagentcore_gateway.mcp.gateway_url
}

output "gateway_id" {
  description = "AgentCore Gateway ID."
  value       = aws_bedrockagentcore_gateway.mcp.gateway_id
}

output "budget_name" {
  description = "AWS Budgets budget name for this project."
  value       = aws_budgets_budget.project.name
}

output "mcp_tool_function_names" {
  description = "Actual deployed Lambda function name for each MCP tool, keyed by tool name. Function names are truncated to fit AWS's 64-character limit - scripts must read this rather than reconstructing names from the project/environment naming convention."
  value       = { for k, fn in aws_lambda_function.mcp_tools : k => fn.function_name }
}

output "dashboard_name" {
  description = "CloudWatch dashboard name for this project."
  value       = aws_cloudwatch_dashboard.main.dashboard_name
}

output "vector_store_backend" {
  description = "Vector store backend in use (s3_vectors or opensearch_serverless)."
  value       = var.vector_store_backend
}
