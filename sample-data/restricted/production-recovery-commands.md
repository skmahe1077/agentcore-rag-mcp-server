# Production Recovery Commands

- **Document ID:** RS-RECOVERY-001
- **Service:** checkout
- **Environment:** production
- **Owner:** Cloud Platform Engineering
- **Classification:** restricted
- **Effective date:** 2026-01-01
- **Review date:** 2027-01-01
- **Version:** 2
- **Status:** active
- **Permitted roles:** incident_commander, administrator
- **Severity applicability:** SEV1, SEV2

## Prerequisites

- Open incident record with `confirmed_by_user: true`.
- Incident-commander or administrator role, verified via `check_operator_permissions` for the `production` environment specifically.
- This document is intentionally excluded from retrieval for the `read_only_operator` and `cloud_engineer`/`application_engineer` roles. `search_runbooks` must filter it out before any content reaches the model for those roles — it must never be sent to the foundation model as context for an unauthorized user, and its absence should be explained as a denied-access outcome, not a retrieval miss.

## Investigation steps

Not applicable — this is a remediation reference, gated behind `emergency-change-procedure.md`, not an investigation runbook.

## Escalation guidance

Any use of the commands referenced by this document is itself an emergency change and must follow `emergency-change-procedure.md` in full, including a pre-identified rollback path and specific per-action confirmation.

## Rollback guidance

Each command class below has a corresponding rollback path; neither the commands nor their rollback paths are executed by the assistant automatically. The assistant may reference this document's existence and its access requirements, and — for an authorized, confirmed user — its content, but never executes infrastructure changes itself in this version of the system.

## Authoritative source

Cloud Platform Engineering emergency-operations catalog. Access to this document is separately audited via CloudTrail in addition to the standard authorization-decision logging applied to every retrieval.

## Expected evidence

Any reference to this document's content in an incident summary must cite the confirmed incident record ID and the verified `incident_commander`/`administrator` role of the requester.

## Restricted content

Forced target-group deregistration, manual database failover, and cache flush procedures for the checkout service are documented here for authorized incident commanders only. Content withheld from this sample dataset's non-restricted excerpt — this file exists primarily to validate that the retrieval and authorization layers correctly withhold restricted, classification-gated content from unauthorized roles.
