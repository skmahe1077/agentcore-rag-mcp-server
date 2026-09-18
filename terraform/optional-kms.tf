# Single project-level customer-managed KMS key, created only when
# use_customer_managed_kms = true. The demo profile uses AWS-owned/managed
# keys (no extra KMS charge, no key-policy management) - see COST.md.

resource "aws_kms_key" "project" {
  count = var.use_customer_managed_kms ? 1 : 0

  description             = "Customer-managed key for ${local.name_prefix} (S3, S3 Vectors, DynamoDB, CloudWatch Logs)."
  deletion_window_in_days = var.kms_deletion_window_in_days
  enable_key_rotation     = true

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "EnableRootAccountAccess"
        Effect    = "Allow"
        Principal = { AWS = "arn:${local.partition}:iam::${local.account_id}:root" }
        Action    = "kms:*"
        Resource  = "*"
      },
      {
        Sid    = "AllowCloudWatchLogsEncryption"
        Effect = "Allow"
        Principal = {
          Service = "logs.${local.region}.amazonaws.com"
        }
        Action = [
          "kms:Encrypt*",
          "kms:Decrypt*",
          "kms:ReEncrypt*",
          "kms:GenerateDataKey*",
          "kms:Describe*"
        ]
        Resource = "*"
        Condition = {
          ArnLike = {
            "kms:EncryptionContext:aws:logs:arn" = "arn:${local.partition}:logs:${local.region}:${local.account_id}:*"
          }
        }
      }
    ]
  })

  tags = merge(local.common_tags, { Name = "${local.name_prefix}-cmk" })
}

resource "aws_kms_alias" "project" {
  count = var.use_customer_managed_kms ? 1 : 0

  name          = "alias/${local.name_prefix}"
  target_key_id = aws_kms_key.project[0].key_id
}
