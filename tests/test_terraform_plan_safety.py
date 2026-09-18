"""Static checks over the Terraform source proving the demo profile's
acceptance criteria (#16, #17) without needing live AWS credentials to run
a real `terraform plan`. These complement, but do not replace, running
`terraform plan` in CI once credentials are available - see
TROUBLESHOOTING.md.
"""

from __future__ import annotations

import re
from pathlib import Path

TERRAFORM_DIR = Path(__file__).resolve().parent.parent / "terraform"


def _read_all_tf() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in TERRAFORM_DIR.glob("*.tf"))


def test_no_nat_gateway_resource_anywhere_in_the_config():
    content = _read_all_tf()
    assert "aws_nat_gateway" not in content


def test_no_ec2_instance_resource_anywhere_in_the_config():
    content = _read_all_tf()
    assert 'resource "aws_instance"' not in content


def test_no_eks_cluster_resource_anywhere_in_the_config():
    content = _read_all_tf()
    assert "aws_eks_cluster" not in content


def test_no_rds_cluster_or_instance_resource_anywhere_in_the_config():
    content = _read_all_tf()
    assert "aws_rds_cluster" not in content
    assert "aws_db_instance" not in content


def test_opensearch_serverless_resources_are_all_gated_on_a_disabled_local():
    content = (TERRAFORM_DIR / "optional-opensearch-serverless.tf").read_text(encoding="utf-8")
    resource_blocks = re.findall(
        r'resource\s+"aws_opensearchserverless_\w+"\s+"\w+"\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}',
        content,
    )
    assert resource_blocks, "expected at least one aws_opensearchserverless_* resource in the optional file"
    for block in resource_blocks:
        assert "count = local.create_opensearch_serverless ? 1 : 0" in block


def test_vector_store_backend_defaults_to_s3_vectors():
    content = (TERRAFORM_DIR / "variables.tf").read_text(encoding="utf-8")
    match = re.search(
        r'variable\s+"vector_store_backend"\s*\{.*?default\s*=\s*"([^"]+)"',
        content,
        re.DOTALL,
    )
    assert match is not None
    assert match.group(1) == "s3_vectors"


def test_opensearch_serverless_disabled_by_default():
    content = (TERRAFORM_DIR / "variables.tf").read_text(encoding="utf-8")
    match = re.search(
        r'variable\s+"enable_opensearch_serverless"\s*\{.*?default\s*=\s*(\w+)',
        content,
        re.DOTALL,
    )
    assert match is not None
    assert match.group(1) == "false"


def test_deletion_protection_disabled_by_default_for_clean_teardown():
    content = (TERRAFORM_DIR / "variables.tf").read_text(encoding="utf-8")
    match = re.search(
        r'variable\s+"enable_deletion_protection"\s*\{.*?default\s*=\s*(\w+)',
        content,
        re.DOTALL,
    )
    assert match is not None
    assert match.group(1) == "false"


def test_simulated_operational_data_enabled_by_default():
    content = (TERRAFORM_DIR / "variables.tf").read_text(encoding="utf-8")
    match = re.search(
        r'variable\s+"use_simulated_operational_data"\s*\{.*?default\s*=\s*(\w+)',
        content,
        re.DOTALL,
    )
    assert match is not None
    assert match.group(1) == "true"
