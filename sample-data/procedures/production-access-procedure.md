# Production Access Procedure

- **Document ID:** PR-ACCESS-001
- **Service:** all
- **Environment:** production
- **Owner:** Cloud Security & Platform Engineering
- **Classification:** restricted
- **Effective date:** 2026-01-01
- **Review date:** 2027-01-01
- **Version:** 5
- **Status:** active
- **Permitted roles:** incident_commander, administrator
- **Severity applicability:** SEV1, SEV2, SEV3, SEV4

## Prerequisites

- Active incident-commander or administrator role assignment, verified via `check_operator_permissions` before any production access is granted.
- A valid, current business justification (an open incident or an approved change record).

## Investigation steps

This procedure governs *access*, not investigation technique — see the relevant service runbook for investigation steps once access is confirmed.

1. Confirm the requester's role and permitted environments through `check_operator_permissions`. Never infer authorization from the requester's stated role in conversation; the authorization decision must come from the entitlements check, not the prompt.
2. Confirm the request maps to an open incident or approved change record before granting any production-scoped action.
3. All production access is read-only by default. Write access requires the explicit confirmation flow described in `emergency-change-procedure.md`.
4. All access decisions are recorded; there is no "temporary" or "off the record" production access.

## Escalation guidance

- Any access request that cannot be mapped to an open incident or approved change must be denied and escalated to the on-call incident commander for review, not granted provisionally.

## Rollback guidance

- Not applicable — this procedure does not itself modify infrastructure. See the specific runbook or `emergency-change-procedure.md` for rollback guidance on the underlying action.

## Authoritative source

Cloud Security & Platform Engineering policy catalog. This procedure implements the organization's least-privilege access policy for production systems.

## Expected evidence

Any assertion that a user is authorized for a production action must cite the `check_operator_permissions` decision (`allowed`, `applied_role`, `decision_reason`), never the user's self-reported role.
