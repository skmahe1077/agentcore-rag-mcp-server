# S3 Vectors is the default vector store (var.vector_store_backend =
# "s3_vectors"). It has no minimum billable compute capacity, unlike
# OpenSearch Serverless - see optional-opensearch-serverless.tf and
# ARCHITECTURE.md for when that alternative is appropriate instead.

resource "aws_s3vectors_vector_bucket" "runbooks" {
  count = local.create_s3_vectors ? 1 : 0

  vector_bucket_name = "${local.name_prefix}-vec-${random_id.bucket_suffix.hex}"
  force_destroy      = !local.is_production

  dynamic "encryption_configuration" {
    for_each = var.use_customer_managed_kms ? [1] : []
    content {
      sse_type    = "aws:kms"
      kms_key_arn = local.kms_key_arn
    }
  }

  tags = merge(local.common_tags, { Name = "${local.name_prefix}-vectors" })
}

resource "aws_s3vectors_index" "runbooks" {
  count = local.create_s3_vectors ? 1 : 0

  vector_bucket_name = aws_s3vectors_vector_bucket.runbooks[0].vector_bucket_name
  index_name         = "${local.name_prefix}-runbooks-index"
  data_type          = "float32"
  dimension          = var.embedding_dimensions
  distance_metric    = "cosine"

  dynamic "encryption_configuration" {
    for_each = var.use_customer_managed_kms ? [1] : []
    content {
      sse_type    = "aws:kms"
      kms_key_arn = local.kms_key_arn
    }
  }

  # The Bedrock-managed chunk text and auto-generated provenance blob
  # (AMAZON_BEDROCK_METADATA - includes a graphDocument.entities list whose
  # size scales with the source document's content, and isn't read by any
  # tool - see app/mcp_server/tools/search_runbooks.py) are stored as
  # non-filterable metadata so they don't count against the 2KB
  # filterable-metadata budget per vector (confirmed live: with only
  # AMAZON_BEDROCK_TEXT excluded, ingestion failed most documents with
  # "Filterable metadata must have at most 2048 bytes"). The
  # classification/role/service/environment attributes used for
  # authorization filtering remain filterable.
  metadata_configuration {
    non_filterable_metadata_keys = ["AMAZON_BEDROCK_TEXT", "AMAZON_BEDROCK_METADATA"]
  }

  tags = merge(local.common_tags, { Name = "${local.name_prefix}-runbooks-index" })
}
