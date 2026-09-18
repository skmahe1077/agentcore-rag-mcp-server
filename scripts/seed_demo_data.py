#!/usr/bin/env python3
"""Seed the project's DynamoDB table with simulated evidence, entitlements,
and demo users from sample-data/simulated-operations/*.json.

Idempotent: every item uses a deterministic key, so re-running this script
overwrites the same items rather than duplicating them.

Usage:
    python3 scripts/seed_demo_data.py --table-name <table> [--region eu-west-1]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "sample-data" / "simulated-operations"
EVENT_TTL_SECONDS = 30 * 24 * 60 * 60  # simulated events are temporary demo data


def _load(name: str) -> list[dict[str, Any]]:
    path = DATA_DIR / name
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def build_items() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    for role_entitlement in _load("entitlements.json"):
        role = role_entitlement["role"]
        items.append(
            {
                "pk": f"ENTITLEMENT#{role}",
                "sk": f"ENTITLEMENT#{role}",
                "gsi1pk": "ENTITLEMENT",
                "gsi1sk": role,
                "entity_type": "entitlement",
                **role_entitlement,
            }
        )

    for user in _load("demo_users.json"):
        user_id = user["user_id"]
        items.append(
            {
                "pk": f"USER#{user_id}",
                "sk": f"USER#{user_id}",
                "gsi1pk": "USER",
                "gsi1sk": user_id,
                "entity_type": "user",
                **user,
            }
        )

    for alarm in _load("alarms.json"):
        service, environment, alarm_name = (
            alarm["service"],
            alarm["environment"],
            alarm["alarm_name"],
        )
        items.append(
            {
                "pk": f"ALARM#{service}#{environment}",
                "sk": f"ALARM#{alarm_name}",
                "gsi1pk": f"EVIDENCE#{service}#{environment}",
                "gsi1sk": f"ALARM#{alarm_name}",
                "entity_type": "alarm",
                **alarm,
            }
        )

    for resource in _load("resource_status.json"):
        service, environment = resource["service"], resource["environment"]
        resource_key = f"{resource['resource_type']}#{resource['resource_identifier']}"
        items.append(
            {
                "pk": f"RESOURCE#{service}#{environment}",
                "sk": f"RESOURCE#{resource_key}",
                "gsi1pk": f"EVIDENCE#{service}#{environment}",
                "gsi1sk": f"RESOURCE#{resource_key}",
                "entity_type": "resource_status",
                **resource,
            }
        )

    now = int(time.time())
    for idx, event in enumerate(_load("recent_events.json")):
        service, environment, timestamp = (
            event["service"],
            event["environment"],
            event["timestamp"],
        )
        items.append(
            {
                "pk": f"EVENT#{service}#{environment}",
                "sk": f"EVENT#{timestamp}#{idx}",
                "gsi1pk": f"EVIDENCE#{service}#{environment}",
                "gsi1sk": f"EVENT#{timestamp}",
                "entity_type": "event",
                "ttl": now + EVENT_TTL_SECONDS,
                **event,
            }
        )

    return items


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--table-name",
        required=True,
        help="DynamoDB table name (see terraform output dynamodb_table_name)",
    )
    parser.add_argument("--region", default="eu-west-1", help="AWS region")
    parser.add_argument("--dry-run", action="store_true", help="Print items instead of writing them")
    args = parser.parse_args()

    items = build_items()

    if args.dry_run:
        for item in items:
            print(json.dumps(item, default=str))
        print(f"\n{len(items)} items (dry run, nothing written).", file=sys.stderr)
        return 0

    import boto3

    dynamodb = boto3.resource("dynamodb", region_name=args.region)
    table = dynamodb.Table(args.table_name)

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from app.mcp_server.clients import to_dynamodb_safe

    with table.batch_writer(overwrite_by_pkeys=["pk", "sk"]) as batch:
        for item in items:
            batch.put_item(Item=to_dynamodb_safe(item))

    print(f"Seeded {len(items)} items into {args.table_name}.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
