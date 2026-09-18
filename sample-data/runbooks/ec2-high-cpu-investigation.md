# EC2 High CPU Investigation

- **Document ID:** RB-EC2-CPU-001
- **Service:** checkout
- **Environment:** production, staging
- **Owner:** Cloud Platform Engineering
- **Classification:** internal
- **Effective date:** 2026-02-01
- **Review date:** 2027-02-01
- **Version:** 2
- **Status:** active
- **Permitted roles:** cloud_engineer, incident_commander, application_engineer, read_only_operator
- **Severity applicability:** SEV2, SEV3, SEV4

## Prerequisites

- Read-only access to CloudWatch EC2 metrics and Auto Scaling group configuration for the affected environment.
- Confirmed instance identifiers before requesting resource status.

## Investigation steps

1. Retrieve `get_resource_status` for the `ec2_instance` and its `auto_scaling_group`. Note CPU utilization trend, instance count, and whether the group is at its configured maximum.
2. Retrieve `get_recent_events` for the service/environment. A traffic spike, a stuck retry loop in a dependent service, or a recent deployment introducing an inefficient code path are the most common causes.
3. Distinguish sustained high CPU (likely a genuine load or regression issue) from a brief spike (often self-resolving and not actionable).
4. If the Auto Scaling group is at maximum capacity and still saturated, this is a capacity-planning issue, not a code-level incident — escalate per `incident-escalation-procedure.md` rather than attempting ad hoc scaling changes.
5. Do not terminate, reboot, or manually resize instances during investigation; this is a read-only investigation runbook.

## Escalation guidance

- Escalate immediately if sustained CPU exceeds 90% for more than 15 minutes on a production service with customer-facing impact.
- Escalate to the application-owning team if a specific recent deployment correlates with the CPU increase.

## Rollback guidance

- If a recent deployment is the likely cause, recommend rollback through the standard pipeline per `emergency-change-procedure.md`. Do not modify Auto Scaling group desired capacity manually as a substitute for addressing the root cause.

## Authoritative source

Cloud Platform Engineering runbook catalog.

## Expected evidence

A grounded conclusion should cite current CPU utilization, instance/ASG counts, and at least one correlated recent event before attributing cause.
