# ALB / Target Group HTTP 5xx Investigation

- **Document ID:** RB-ALB-5XX-001
- **Service:** checkout
- **Environment:** production, staging
- **Owner:** Cloud Platform Engineering
- **Classification:** internal
- **Effective date:** 2026-01-15
- **Review date:** 2027-01-15
- **Version:** 3
- **Status:** active
- **Permitted roles:** cloud_engineer, incident_commander, application_engineer, read_only_operator
- **Severity applicability:** SEV1, SEV2, SEV3

## Prerequisites

- Read-only access to CloudWatch alarms and ALB/target-group metrics for the affected environment.
- Confirmed identity of the affected service and environment before taking any action.
- For production, an active on-call or incident-commander assignment before recommending remediation.

## Investigation steps

1. **Confirm the alarm.** Retrieve the triggering alarm (`get_alarm_details`) and note `alarm_state`, `state_reason`, and `transition_time`. A single noisy datapoint is not the same as a sustained `ALARM` state.
2. **Check target health.** Retrieve `get_resource_status` for the `target_group` and `application_load_balancer`. Compare `healthy_targets` to `unhealthy_targets`. If most targets are unhealthy, the failure is likely upstream of the ALB (application or dependency), not the load balancer itself.
3. **Correlate with recent changes.** Retrieve `get_recent_events` for the service/environment over the last 60 minutes. A deployment, configuration change, or scaling event immediately preceding the alarm is the most common correlated factor.
4. **Check dependency health.** 5xx spikes on a checkout-style service are frequently caused by a downstream dependency (database, payment gateway, cache) failing open as 500s rather than the ALB or compute layer itself. See `application-dependency-failure.md` and `rds-connection-exhaustion.md` if a database dependency is implicated.
5. **Distinguish 5xx source.** `502`/`504` typically indicate the target failed to respond or timed out (application or dependency issue). `503` typically indicates no healthy targets (capacity or health-check issue). `500` typically indicates an unhandled application exception.
6. **Do not restart, redeploy, or scale production resources during investigation.** Investigation is read-only; remediation requires a confirmed incident record and, for production, incident-commander approval per `emergency-change-procedure.md`.

## Escalation guidance

- Escalate to the incident commander immediately if `healthy_targets` is 0 for a production service, or if the alarm has been in `ALARM` state for more than 10 minutes without a clear root cause.
- Escalate to the application-owning team if evidence points to an application-level exception rather than infrastructure.
- Follow `incident-escalation-procedure.md` for severity classification and paging.

## Rollback guidance

- If the correlated recent event is a deployment, the fastest mitigation is typically rolling back to the last known-good deployment, not further investigation. Rollback requires incident-commander confirmation and is executed through the standard deployment pipeline, never manually against running infrastructure.
- Do not attempt manual instance termination or target deregistration as a first response; this can mask the root cause and complicate the timeline.

## Authoritative source

Cloud Platform Engineering runbook catalog, reviewed by the Checkout Service on-call rotation. This document supersedes RB-ALB-5XX-001 v2 (retired 2025-11-01).

## Expected evidence

A grounded conclusion for an ALB 5xx incident should cite at minimum: current `alarm_state`, `healthy_targets`/`unhealthy_targets` counts, and at least one correlated recent event or dependency-status observation. Do not assert a root cause without at least two corroborating evidence points.
