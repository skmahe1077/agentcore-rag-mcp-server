resource "aws_bedrockagent_knowledge_base" "runbooks" {
  name        = "${local.name_prefix}-kb"
  description = "Approved cloud operations runbooks, procedures, and architecture references for grounded incident investigation."
  role_arn    = aws_iam_role.knowledge_base.arn

  knowledge_base_configuration {
    type = "VECTOR"

    vector_knowledge_base_configuration {
      embedding_model_arn = "arn:${local.partition}:bedrock:${local.region}::foundation-model/${var.embedding_model_id}"

      embedding_model_configuration {
        bedrock_embedding_model_configuration {
          dimensions          = var.embedding_dimensions
          embedding_data_type = "FLOAT32"
        }
      }
    }
  }

  storage_configuration {
    type = local.create_s3_vectors ? "S3_VECTORS" : "OPENSEARCH_SERVERLESS"

    dynamic "s3_vectors_configuration" {
      for_each = local.create_s3_vectors ? [1] : []
      content {
        # index_arn is mutually exclusive with vector_bucket_arn/index_name
        # (confirmed against the live API - Terraform rejects the
        # combination at plan time: "cannot be specified when index_arn is
        # specified"). index_arn alone fully identifies the vector index.
        index_arn = aws_s3vectors_index.runbooks[0].index_arn
      }
    }

    dynamic "opensearch_serverless_configuration" {
      for_each = local.create_opensearch_serverless ? [1] : []
      content {
        collection_arn    = aws_opensearchserverless_collection.runbooks[0].arn
        vector_index_name = "${local.name_prefix}-runbooks-index"

        field_mapping {
          vector_field   = "bedrock-knowledge-base-default-vector"
          text_field     = "AMAZON_BEDROCK_TEXT_CHUNK"
          metadata_field = "AMAZON_BEDROCK_METADATA"
        }
      }
    }
  }

  tags = local.common_tags

  depends_on = [aws_iam_role_policy.knowledge_base]
}

resource "aws_bedrockagent_data_source" "runbooks" {
  knowledge_base_id = aws_bedrockagent_knowledge_base.runbooks.id
  name              = "${local.name_prefix}-runbook-docs"
  description       = "S3 source for approved runbooks, procedures, architecture references, and restricted recovery commands."

  data_deletion_policy = local.effective_deletion_protection ? "RETAIN" : "DELETE"

  data_source_configuration {
    type = "S3"

    s3_configuration {
      bucket_arn = aws_s3_bucket.runbook_documents.arn
    }
  }

  vector_ingestion_configuration {
    chunking_configuration {
      chunking_strategy = "FIXED_SIZE"

      fixed_size_chunking_configuration {
        max_tokens         = var.chunking_max_tokens
        overlap_percentage = var.chunking_overlap_percentage
      }
    }
  }

  server_side_encryption_configuration {
    kms_key_arn = var.use_customer_managed_kms ? local.kms_key_arn : null
  }
}
