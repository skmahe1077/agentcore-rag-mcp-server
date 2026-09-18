# Single table for entitlements, simulated operational evidence (alarms,
# resource status, recent events), incident records, idempotency records,
# and feedback. On-demand billing - no provisioned capacity to size or pay
# for while idle.
#
# Key design:
#   pk = "<ENTITY_TYPE>#<partition-key-value>"
#   sk = "<ENTITY_TYPE>#<sort-key-value>"
# gsi1 supports lookups by role (entitlements), by service+environment
# (evidence), and by status (incidents) without a full table scan.

resource "aws_dynamodb_table" "main" {
  name         = "${local.name_prefix}-table"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  attribute {
    name = "gsi1pk"
    type = "S"
  }

  attribute {
    name = "gsi1sk"
    type = "S"
  }

  global_secondary_index {
    name            = "gsi1"
    projection_type = "ALL"

    key_schema {
      attribute_name = "gsi1pk"
      key_type       = "HASH"
    }

    key_schema {
      attribute_name = "gsi1sk"
      key_type       = "RANGE"
    }
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = local.effective_point_in_time_recovery
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = var.use_customer_managed_kms ? local.kms_key_arn : null
  }

  deletion_protection_enabled = local.effective_deletion_protection

  tags = merge(local.common_tags, { Name = "${local.name_prefix}-table" })
}
