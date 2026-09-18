locals {
  name_prefix = "${var.project_name}-${var.environment}"

  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.region
  partition  = data.aws_partition.current.partition

  is_production = var.cost_profile == "production"

  # Point-in-time recovery and deletion protection default on for the
  # production cost profile unless explicitly overridden downward.
  effective_point_in_time_recovery = local.is_production ? true : var.enable_point_in_time_recovery
  effective_deletion_protection    = local.is_production ? true : var.enable_deletion_protection

  create_opensearch_serverless = var.enable_opensearch_serverless && var.vector_store_backend == "opensearch_serverless"
  create_s3_vectors            = var.vector_store_backend == "s3_vectors"

  kms_key_arn = var.use_customer_managed_kms ? aws_kms_key.project[0].arn : null

  cognito_issuer        = "https://cognito-idp.${local.region}.amazonaws.com/${aws_cognito_user_pool.main.id}"
  cognito_discovery_url = "${local.cognito_issuer}/.well-known/openid-configuration"

  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    CostProfile = var.cost_profile
    ManagedBy   = "terraform"
    Application = "cloud-operations-runbook-assistant"
  }
}
