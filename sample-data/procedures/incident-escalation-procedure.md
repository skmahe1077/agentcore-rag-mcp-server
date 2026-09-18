# Incident Escalation Procedure

- **Document ID:** PR-ESC-001
- **Service:** all
- **Environment:** production, staging
- **Owner:** Incident Management Office
- **Classification:** internal
- **Effective date:** 2026-01-01
- **Review date:** 2027-01-01
- **Version:** 6
- **Status:** active
- **Permitted roles:** cloud_engineer, incident_commander, application_engineer, read_only_operator
- **Severity applicability:** SEV1, SEV2, SEV3, SEV4

## Prerequisites

- Familiarity with the severity matrix below.

## Investigation steps

Severity classification (used across all runbooks in this catalog):

| Severity | Definition | Example |
|---|---|---|
| SEV1 | Full outage of a customer-facing production service | Checkout completely unavailable |
| SEV2 | Significant degradation of a production service | Checkout 5xx rate elevated but partially functional |
| SEV3 | Limited or non-customer-facing production impact | Internal tooling degraded |
| SEV4 | No current production impact | Investigation of a transient, resolved anomaly |

1. Any engineer investigating an alarm classifies severity using the matrix above before paging.
2. SEV1 and SEV2 page the on-call incident commander immediately, in parallel with continued investigation — do not wait for root cause before paging.
3. SEV3 and SEV4 are logged and investigated during business hours unless they show signs of escalating.
4. The incident commander owns the decision to create a formal incident record (`create_incident_record`) and to authorize any remediation action.

## Escalation guidance

This document *is* the escalation guidance referenced by every other runbook in this catalog.

## Rollback guidance

Not applicable.

## Authoritative source

Incident Management Office policy catalog.

## Expected evidence

Severity classifications cited in an incident summary should reference this document's matrix, not an ad hoc judgment.
