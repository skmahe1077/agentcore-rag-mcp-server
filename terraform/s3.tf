resource "random_id" "bucket_suffix" {
  byte_length = 4
}

# ---------------------------------------------------------------------------
# Runbook / procedure / architecture documents (Bedrock Knowledge Base source)
# ---------------------------------------------------------------------------

resource "aws_s3_bucket" "runbook_documents" {
  bucket        = "${local.name_prefix}-runbooks-${random_id.bucket_suffix.hex}"
  force_destroy = !local.is_production

  tags = merge(local.common_tags, { Name = "${local.name_prefix}-runbooks" })
}

resource "aws_s3_bucket_versioning" "runbook_documents" {
  bucket = aws_s3_bucket.runbook_documents.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "runbook_documents" {
  bucket = aws_s3_bucket.runbook_documents.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = var.use_customer_managed_kms ? "aws:kms" : "AES256"
      kms_master_key_id = var.use_customer_managed_kms ? local.kms_key_arn : null
    }
    bucket_key_enabled = var.use_customer_managed_kms
  }
}

resource "aws_s3_bucket_public_access_block" "runbook_documents" {
  bucket = aws_s3_bucket.runbook_documents.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "runbook_documents" {
  bucket = aws_s3_bucket.runbook_documents.id

  rule {
    id     = "expire-noncurrent-versions"
    status = "Enabled"

    noncurrent_version_expiration {
      noncurrent_days = 30
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

resource "aws_s3_bucket_policy" "runbook_documents_tls_only" {
  bucket = aws_s3_bucket.runbook_documents.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource = [
          aws_s3_bucket.runbook_documents.arn,
          "${aws_s3_bucket.runbook_documents.arn}/*"
        ]
        Condition = {
          Bool = { "aws:SecureTransport" = "false" }
        }
      }
    ]
  })
}

# ---------------------------------------------------------------------------
# Deployment artifacts: Lambda tool zips and AgentCore Runtime code package.
# Kept separate from documents so lifecycle/versioning and the Knowledge
# Base data-source scope never overlap with deployable code.
# ---------------------------------------------------------------------------

resource "aws_s3_bucket" "deployment_artifacts" {
  bucket        = "${local.name_prefix}-artifacts-${random_id.bucket_suffix.hex}"
  force_destroy = !local.is_production

  tags = merge(local.common_tags, { Name = "${local.name_prefix}-artifacts" })
}

resource "aws_s3_bucket_versioning" "deployment_artifacts" {
  bucket = aws_s3_bucket.deployment_artifacts.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "deployment_artifacts" {
  bucket = aws_s3_bucket.deployment_artifacts.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = var.use_customer_managed_kms ? "aws:kms" : "AES256"
      kms_master_key_id = var.use_customer_managed_kms ? local.kms_key_arn : null
    }
    bucket_key_enabled = var.use_customer_managed_kms
  }
}

resource "aws_s3_bucket_public_access_block" "deployment_artifacts" {
  bucket = aws_s3_bucket.deployment_artifacts.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "deployment_artifacts" {
  bucket = aws_s3_bucket.deployment_artifacts.id

  rule {
    id     = "expire-noncurrent-versions"
    status = "Enabled"

    noncurrent_version_expiration {
      noncurrent_days = 14
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}
