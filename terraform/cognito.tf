# Cognito User Pool backing AgentCore Identity's JWT authorizer. Two demo
# identities (read-only operator, incident commander) are created directly
# from sample-data/simulated-operations/demo_users.json, so Terraform and
# the DynamoDB seed script (scripts/seed_demo_data.py) share one source of
# truth for user_id/role mapping.

locals {
  demo_users = jsondecode(file("${path.module}/../sample-data/simulated-operations/demo_users.json"))
}

resource "aws_cognito_user_pool" "main" {
  name = "${local.name_prefix}-users"

  deletion_protection = local.effective_deletion_protection ? "ACTIVE" : "INACTIVE"

  # Custom attributes only: the JWT authorizer at the AgentCore Gateway
  # validates signature/issuer/audience/expiry; each MCP tool then
  # re-derives the caller's role and permissions from DynamoDB by user_id
  # (see app/mcp_server/security.py) rather than trusting this claim -
  # custom:role here is informational and used only for Gateway-level
  # defense-in-depth claim matching, never as the sole authorization source.
  schema {
    name                     = "role"
    attribute_data_type      = "String"
    mutable                  = true
    required                 = false
    developer_only_attribute = false

    string_attribute_constraints {
      min_length = 1
      max_length = 50
    }
  }

  password_policy {
    minimum_length                   = 12
    require_lowercase                = true
    require_numbers                  = true
    require_symbols                  = true
    require_uppercase                = true
    temporary_password_validity_days = 7
  }

  # Demo users use @example.invalid addresses - no real inbox to verify
  # against, so recovery is admin-only rather than email-based.
  account_recovery_setting {
    recovery_mechanism {
      name     = "admin_only"
      priority = 1
    }
  }

  auto_verified_attributes = []

  tags = merge(local.common_tags, { Name = "${local.name_prefix}-users" })
}

resource "aws_cognito_user_pool_client" "demo" {
  name         = "${local.name_prefix}-demo-client"
  user_pool_id = aws_cognito_user_pool.main.id

  generate_secret = false

  explicit_auth_flows = [
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
  ]

  prevent_user_existence_errors = "ENABLED"

  # Short-lived tokens for a demo client - reduces the blast radius of a
  # leaked token without needing revocation infrastructure.
  access_token_validity  = 60
  id_token_validity      = 60
  refresh_token_validity = 1

  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }

  read_attributes  = ["email", "custom:role"]
  write_attributes = ["email"]
}

resource "random_password" "demo_user" {
  for_each = { for user in local.demo_users : user.user_id => user }

  length      = 24
  special     = true
  min_lower   = 1
  min_upper   = 1
  min_numeric = 1
  min_special = 1
}

resource "aws_cognito_user" "demo" {
  for_each = { for user in local.demo_users : user.user_id => user }

  user_pool_id         = aws_cognito_user_pool.main.id
  username             = each.value.user_id
  password             = random_password.demo_user[each.key].result
  message_action       = "SUPPRESS" # fake @example.invalid addresses - never send real mail
  force_alias_creation = false

  attributes = {
    email          = each.value.email
    email_verified = "true"
    "custom:role"  = each.value.role
  }
}
