# OpenSearch Serverless is an OPTIONAL production-scale vector backend.
# It is not created by default: var.enable_opensearch_serverless = false and
# var.vector_store_backend = "s3_vectors" out of the box, so every resource
# in this file has count = 0 unless BOTH are explicitly changed.
#
# OpenSearch Serverless carries a minimum billable OCU footprint even when
# idle, which is not cost-effective for a low-traffic demonstration - see
# ARCHITECTURE.md. Consider it instead of S3 Vectors when you need:
#   - hybrid (keyword + vector) search
#   - high query throughput or complex metadata filtering at scale
#   - very large-scale retrieval beyond S3 Vectors' per-vector metadata limits
#   - you already operate OpenSearch and want a single search stack

resource "aws_opensearchserverless_security_policy" "encryption" {
  count = local.create_opensearch_serverless ? 1 : 0

  name = "${local.name_prefix}-enc"
  type = "encryption"
  policy = jsonencode({
    Rules = [
      {
        ResourceType = "collection"
        Resource     = ["collection/${local.name_prefix}-runbooks"]
      }
    ]
    AWSOwnedKey = !var.use_customer_managed_kms
    KmsARN      = var.use_customer_managed_kms ? local.kms_key_arn : null
  })
}

resource "aws_opensearchserverless_security_policy" "network" {
  count = local.create_opensearch_serverless ? 1 : 0

  name = "${local.name_prefix}-net"
  type = "network"
  policy = jsonencode([
    {
      Rules = [
        {
          ResourceType = "collection"
          Resource     = ["collection/${local.name_prefix}-runbooks"]
        },
        {
          ResourceType = "dashboard"
          Resource     = ["collection/${local.name_prefix}-runbooks"]
        }
      ]
      AllowFromPublic = true
    }
  ])
}

resource "aws_opensearchserverless_access_policy" "collection" {
  count = local.create_opensearch_serverless ? 1 : 0

  name = "${local.name_prefix}-access"
  type = "data"
  policy = jsonencode([
    {
      Rules = [
        {
          ResourceType = "index"
          Resource     = ["index/${local.name_prefix}-runbooks/*"]
          Permission   = ["aoss:*"]
        },
        {
          ResourceType = "collection"
          Resource     = ["collection/${local.name_prefix}-runbooks"]
          Permission   = ["aoss:*"]
        }
      ]
      Principal = [
        aws_iam_role.knowledge_base.arn,
        "arn:${local.partition}:iam::${local.account_id}:root"
      ]
    }
  ])
}

# NOTE: no official Terraform resource creates a vector index *inside* an
# OpenSearch Serverless collection (that requires an OpenSearch document-API
# PUT, not a control-plane API). If you opt into this backend, create the
# index with a small idempotent script (e.g. opensearch-py or `curl` using
# SigV4) against the collection endpoint before running the Knowledge Base
# ingestion job - this is the documented last-resort step from the project
# brief, scoped only to this optional, disabled-by-default path.

resource "aws_opensearchserverless_collection" "runbooks" {
  count = local.create_opensearch_serverless ? 1 : 0

  name = "${local.name_prefix}-runbooks"
  type = "VECTORSEARCH"

  tags = merge(local.common_tags, { Name = "${local.name_prefix}-runbooks-collection" })

  depends_on = [
    aws_opensearchserverless_security_policy.encryption,
    aws_opensearchserverless_security_policy.network
  ]
}
