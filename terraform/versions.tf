terraform {
  required_version = ">= 1.8"

  required_providers {
    aws = {
      source = "hashicorp/aws"
      # Pinned to the range verified against this project's Terraform config:
      # aws_bedrockagentcore_* resources and aws_bedrockagent_knowledge_base's
      # s3_vectors_configuration block require aws >= 6.x (absent in 5.x).
      version = ">= 6.65.0, < 7.0.0"
    }
    random = {
      source  = "hashicorp/random"
      version = ">= 3.6.0, < 4.0.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = ">= 2.4.0, < 3.0.0"
    }
  }
}
