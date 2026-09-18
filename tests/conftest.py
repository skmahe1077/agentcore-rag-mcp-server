"""Shared pytest fixtures: a moto-mocked DynamoDB table matching
terraform/dynamodb.tf's schema, seeded with the same sample data used by
scripts/seed_demo_data.py."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("TABLE_NAME", "test-table")
os.environ.setdefault("AWS_REGION", "eu-west-1")
os.environ.setdefault("AWS_DEFAULT_REGION", "eu-west-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("KNOWLEDGE_BASE_ID", "test-kb-id")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from moto import mock_aws


@pytest.fixture()
def dynamodb_table():
    with mock_aws():
        import boto3

        from app.mcp_server.clients import dynamodb_resource, to_dynamodb_safe

        dynamodb_resource.cache_clear()

        client = boto3.client("dynamodb", region_name="eu-west-1")
        client.create_table(
            TableName="test-table",
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
                {"AttributeName": "gsi1pk", "AttributeType": "S"},
                {"AttributeName": "gsi1sk", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "gsi1",
                    "KeySchema": [
                        {"AttributeName": "gsi1pk", "KeyType": "HASH"},
                        {"AttributeName": "gsi1sk", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        import seed_demo_data

        resource = boto3.resource("dynamodb", region_name="eu-west-1")
        table = resource.Table("test-table")
        for item in seed_demo_data.build_items():
            table.put_item(Item=to_dynamodb_safe(item))

        yield table
