# Lambda Error Rate Investigation

- **Document ID:** RB-LAMBDA-ERR-001
- **Service:** checkout
- **Environment:** production, staging
- **Owner:** Cloud Platform Engineering
- **Classification:** internal
- **Effective date:** 2026-02-10
- **Review date:** 2027-02-10
- **Version:** 1
- **Status:** active
- **Permitted roles:** cloud_engineer, incident_commander, application_engineer, read_only_operator
- **Severity applicability:** SEV2, SEV3, SEV4

## Prerequisites

- Read-only access to Lambda resource status and recent events for the affected function.

## Investigation steps

1. Retrieve `get_resource_status` for the `lambda_function`. Note error count, throttle count, and concurrent-execution level relative to account/function concurrency limits.
2. Retrieve `get_recent_events` for the service/environment. A recent deployment (new version/alias shift), a configuration change (memory, timeout, reserved concurrency), or an upstream dependency failure are common causes.
3. Distinguish throttling (concurrency limit reached) from functional errors (unhandled exceptions in code) — these require different remediation paths.
4. If errors correlate with a downstream dependency, cross-reference `application-dependency-failure.md`.
5. This is a read-only investigation runbook. Do not modify function configuration, aliases, or concurrency settings during investigation.

## Escalation guidance

- Escalate immediately if the function serves a production customer-facing path and the error rate exceeds 5% sustained for more than 5 minutes.
- Escalate to the owning application team for functional/code-level errors; escalate to Cloud Platform Engineering for concurrency or platform-level throttling.

## Rollback guidance

- If a recent deployment correlates with the error spike, recommend rolling back to the previous published version/alias through the standard pipeline per `emergency-change-procedure.md`.

## Authoritative source

Cloud Platform Engineering runbook catalog.

## Expected evidence

A grounded conclusion should cite current error/throttle counts and at least one correlated recent event.
