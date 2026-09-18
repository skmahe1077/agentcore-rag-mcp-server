# Application Dependency Failure Investigation

- **Document ID:** RB-DEP-FAIL-001
- **Service:** checkout
- **Environment:** production, staging
- **Owner:** Checkout Service Engineering
- **Classification:** internal
- **Effective date:** 2026-02-05
- **Review date:** 2027-02-05
- **Version:** 2
- **Status:** active
- **Permitted roles:** cloud_engineer, incident_commander, application_engineer, read_only_operator
- **Severity applicability:** SEV1, SEV2, SEV3

## Prerequisites

- Familiarity with the checkout service's dependency graph (see `checkout-service-architecture.md`).
- Read-only access to resource status and recent events for the checkout service and its declared dependencies (database, payment gateway, cache).

## Investigation steps

1. Retrieve `get_resource_status` for the checkout service's compute (ALB/target group or Lambda) to confirm the failure is presenting as 5xx errors or elevated latency.
2. Retrieve `get_resource_status` for each declared dependency (database, cache) and check `dependency_status` in the evidence payload for explicit failure indicators (e.g. "database connection failures detected").
3. Retrieve `get_recent_events` across the service and its dependencies for the last 60 minutes; a dependency-side deployment or incident is a common trigger even when the checkout service itself has not changed.
4. Determine whether the checkout service fails open (returns errors) or degrades gracefully (serves cached/partial results) when a dependency is unavailable. This runbook assumes the current implementation fails open on database unavailability — confirm this against `checkout-service-architecture.md` rather than assuming it.
5. This is a read-only investigation runbook. Remediating a dependency failure (failover, scaling, restart) is governed by that dependency's own runbook (e.g. `rds-connection-exhaustion.md`) and requires incident-commander confirmation.

## Escalation guidance

- Escalate to the incident commander when a production dependency failure is confirmed, since it typically requires cross-team coordination (checkout service team + the owning dependency team).
- Page the dependency-owning team directly per `incident-escalation-procedure.md` once the failing dependency is identified.

## Rollback guidance

- If the dependency failure correlates with a recent deployment to that dependency, recommend rollback through the dependency owner's standard pipeline. The checkout service itself may not need rollback if it is a downstream victim rather than the cause.

## Authoritative source

Checkout Service Engineering runbook catalog, cross-reviewed with Database Platform Engineering.

## Expected evidence

A grounded conclusion should cite the checkout service's own resource status, the specific dependency's status/evidence, and at least one correlated recent event before naming a dependency as the cause.
