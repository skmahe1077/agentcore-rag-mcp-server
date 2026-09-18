# ---------------------------------------------------------------------------
# Least-privilege role for the Bedrock Knowledge Base service.
# Additional roles (Lambda tool execution, AgentCore Runtime, AgentCore
# Gateway) are added in lambda-tools.tf and agentcore.tf, kept separate so
# each execution context has its own minimally-scoped role.
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "knowledge_base_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["bedrock.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:${local.partition}:bedrock:${local.region}:${local.account_id}:knowledge-base/*"]
    }
  }
}

resource "aws_iam_role" "knowledge_base" {
  name               = "${local.name_prefix}-kb-role"
  assume_role_policy = data.aws_iam_policy_document.knowledge_base_assume_role.json
  tags               = local.common_tags
}

data "aws_iam_policy_document" "knowledge_base_permissions" {
  statement {
    sid       = "ReadRunbookDocuments"
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:ListBucket"]
    resources = [aws_s3_bucket.runbook_documents.arn, "${aws_s3_bucket.runbook_documents.arn}/*"]
  }

  statement {
    sid       = "InvokeEmbeddingModel"
    effect    = "Allow"
    actions   = ["bedrock:InvokeModel"]
    resources = ["arn:${local.partition}:bedrock:${local.region}::foundation-model/${var.embedding_model_id}"]
  }

  dynamic "statement" {
    for_each = local.create_s3_vectors ? [1] : []
    content {
      sid    = "S3VectorsAccess"
      effect = "Allow"
      actions = [
        "s3vectors:GetIndex",
        "s3vectors:GetVectorBucket",
        "s3vectors:PutVectors",
        "s3vectors:GetVectors",
        "s3vectors:QueryVectors",
        "s3vectors:ListVectors",
        "s3vectors:DeleteVectors"
      ]
      resources = [
        aws_s3vectors_vector_bucket.runbooks[0].vector_bucket_arn,
        aws_s3vectors_index.runbooks[0].index_arn
      ]
    }
  }

  dynamic "statement" {
    for_each = local.create_opensearch_serverless ? [1] : []
    content {
      sid       = "OpenSearchServerlessAccess"
      effect    = "Allow"
      actions   = ["aoss:APIAccessAll"]
      resources = [aws_opensearchserverless_collection.runbooks[0].arn]
    }
  }

  dynamic "statement" {
    for_each = var.use_customer_managed_kms ? [1] : []
    content {
      sid       = "KmsForKnowledgeBase"
      effect    = "Allow"
      actions   = ["kms:Decrypt", "kms:GenerateDataKey", "kms:DescribeKey"]
      resources = [local.kms_key_arn]
    }
  }
}

resource "aws_iam_role_policy" "knowledge_base" {
  name   = "${local.name_prefix}-kb-policy"
  role   = aws_iam_role.knowledge_base.id
  policy = data.aws_iam_policy_document.knowledge_base_permissions.json
}

# ---------------------------------------------------------------------------
# AgentCore Runtime execution role - separate from the Gateway role and the
# Lambda tool-execution roles (lambda-tools.tf) so each execution context is
# independently, minimally scoped.
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "agent_runtime_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["bedrock-agentcore.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_iam_role" "agent_runtime" {
  name               = "${local.name_prefix}-agent-runtime-role"
  assume_role_policy = data.aws_iam_policy_document.agent_runtime_assume_role.json
  tags               = local.common_tags
}

data "aws_iam_policy_document" "agent_runtime_permissions" {
  statement {
    sid    = "InvokeFoundationModel"
    effect = "Allow"
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream",
    ]
    # Covers both direct model IDs and cross-region inference profiles, both
    # of which foundation_model_id may hold (see variables.tf). A cross-
    # region inference profile (e.g. the "eu." prefix) fans requests out to
    # underlying foundation models in OTHER regions within its geography,
    # not just local.region - confirmed live: an "eu." profile routed a
    # request to eu-north-1 and was denied when this resource was scoped to
    # local.region only. foundation-model ARNs carry no account ID, so a
    # region wildcard here doesn't broaden access beyond "any Bedrock
    # foundation model, any region" - it can't reach another account's
    # resources.
    resources = [
      "arn:${local.partition}:bedrock:*::foundation-model/*",
      "arn:${local.partition}:bedrock:${local.region}:${local.account_id}:inference-profile/*",
    ]
  }

  statement {
    sid       = "PullAgentImage"
    effect    = "Allow"
    actions   = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability"]
    resources = [aws_ecr_repository.agent.arn]
  }

  statement {
    sid       = "EcrAuth"
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid    = "Logging"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "logs:DescribeLogGroups",
      "logs:DescribeLogStreams",
    ]
    resources = ["arn:${local.partition}:logs:${local.region}:${local.account_id}:log-group:/aws/bedrock-agentcore/*"]
  }

  statement {
    sid       = "Tracing"
    effect    = "Allow"
    actions   = ["xray:PutTraceSegments", "xray:PutTelemetryRecords", "cloudwatch:PutMetricData"]
    resources = ["*"]
  }

  statement {
    sid       = "WorkloadIdentity"
    effect    = "Allow"
    actions   = ["bedrock-agentcore:GetWorkloadAccessToken", "bedrock-agentcore:GetResourceOauth2Token"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "agent_runtime" {
  name   = "${local.name_prefix}-agent-runtime-policy"
  role   = aws_iam_role.agent_runtime.id
  policy = data.aws_iam_policy_document.agent_runtime_permissions.json
}

# ---------------------------------------------------------------------------
# AgentCore Gateway role - invokes the 7 Lambda-backed MCP tools on the
# agent's behalf.
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "gateway_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["bedrock-agentcore.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_iam_role" "gateway" {
  name               = "${local.name_prefix}-gateway-role"
  assume_role_policy = data.aws_iam_policy_document.gateway_assume_role.json
  tags               = local.common_tags
}

data "aws_iam_policy_document" "gateway_permissions" {
  statement {
    sid       = "InvokeMcpToolLambdas"
    effect    = "Allow"
    actions   = ["lambda:InvokeFunction"]
    resources = [for fn in aws_lambda_function.mcp_tools : fn.arn]
  }

  statement {
    sid    = "Logging"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["arn:${local.partition}:logs:${local.region}:${local.account_id}:log-group:/aws/bedrock-agentcore/*"]
  }
}

resource "aws_iam_role_policy" "gateway" {
  name   = "${local.name_prefix}-gateway-policy"
  role   = aws_iam_role.gateway.id
  policy = data.aws_iam_policy_document.gateway_permissions.json
}
