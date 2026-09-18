# Emergency Change Procedure

- **Document ID:** PR-CHANGE-001
- **Service:** all
- **Environment:** production
- **Owner:** Cloud Platform Engineering
- **Classification:** restricted
- **Effective date:** 2026-01-01
- **Review date:** 2027-01-01
- **Version:** 3
- **Status:** active
- **Permitted roles:** incident_commander, administrator
- **Severity applicability:** SEV1, SEV2, SEV3

## Prerequisites

- An open incident record (`create_incident_record`) with `confirmed_by_user: true`.
- Incident-commander or administrator role, verified via `check_operator_permissions`.

## Investigation steps

Not applicable — this procedure governs change execution after investigation is complete, not investigation itself.

## Escalation guidance

- Any remediation action (rollback, restart, scaling change, failover, parameter change) against a production resource requires:
  1. An open incident record.
  2. Explicit human confirmation captured for that specific action — a general "yes, proceed with the incident" is not sufficient confirmation for a specific write action.
  3. The action executed through the standard deployment/change pipeline, never through direct manual modification of running infrastructure.
- No automated remediation is performed by the assistant in this version of the system. The assistant may recommend an action and prepare the incident record, but a human always executes the change through existing tooling.

## Rollback guidance

- Every emergency change must have a pre-identified rollback path documented in the incident record before execution.
- If a rollback path cannot be identified, escalate to the incident commander before proceeding with the change rather than proceeding without one.

## Authoritative source

Cloud Platform Engineering change-management policy, aligned with the organization's production change control standard.

## Expected evidence

Any statement that a change was authorized must cite the specific incident record ID and the explicit confirmation captured for that action.
