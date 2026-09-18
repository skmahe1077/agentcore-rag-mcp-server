# Contributing

This is a reference implementation, not a maintained product - but improvements are welcome.

## Development setup

```bash
scripts/bootstrap.sh
source .venv/bin/activate
```

## Before submitting a change

```bash
make fmt
make validate
make lint
make test
make security-scan
```

All of these must pass. `make test` runs the full Python test suite (`tests/`) against a moto-mocked AWS environment - no live AWS credentials are needed to run it.

## Conventions

- **Terraform**: one logical concern per file, matching the existing layout (`s3.tf`, `dynamodb.tf`, `agentcore.tf`, ...). Every variable needs a `description` and, where meaningful, a `validation` block. Never hardcode account IDs, ARNs, regions, model IDs, or secrets - add a variable instead.
- **Python**: type hints throughout, small testable functions, structured exceptions (`ValidationError`, `AuthorizationError` in `app/mcp_server/security.py`) rather than bare `Exception`. No comments explaining *what* code does - only *why*, when it's non-obvious.
- **MCP tools**: every tool re-derives authorization from DynamoDB by `user_id` (`security.resolve_entitlement`) - never trust a role or permission claim passed in the tool call's own arguments.
- **Tests**: new tools or authorization logic need a test proving the authorized case *and* the denied case. See `tests/test_retrieval.py` for the pattern.

## Changing a tool's input/output shape

If you add or change a field in `app/mcp_server/schemas.py`, update the matching entry in `terraform/agentcore.tf`'s `local.tool_schema_definitions` - the two are hand-kept in sync (see the comment above that local block for why).

## Reporting issues

Open an issue describing what you expected vs. what happened, including the correlation ID from the response if you have one (see OBSERVABILITY.md).
