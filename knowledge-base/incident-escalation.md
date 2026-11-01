# Incident and escalation process

## When to declare an incident
Declare an incident when customers are affected, or will be soon, and the problem won't be fixed in the next few minutes. If you're not sure, declare it. Lowering the severity later is easy.

## Severity levels
| Severity | Meaning | Examples | Response |
|----------|---------|----------|----------|
| SEV1 | Critical. The product or a core flow is down for all customers, or there is data loss or a security breach | Site down, checkout failing for everyone, primary database down, leaked credentials | Page on-call immediately, 24/7. Incident commander required. Updates every 30 minutes |
| SEV2 | Major. An important feature is broken or slow for many customers; a workaround may exist | Payments failing for one provider, a prod service with zero ready replicas, expired certificate on a customer-facing domain | Page on-call, 24/7. Updates every hour |
| SEV3 | Minor. Limited impact, few customers, or internal tools only | One feature slow, CI/CD pipeline red on `main` for over an hour, staging down | Handle during working hours. Ticket required |
| SEV4 | No customer impact | Disk at 80%, a warning alert, a flaky test | Ticket; fix as part of normal work |

## Roles
- **Incident commander (IC):** leads the response, makes decisions and assigns tasks. By default this is the first on-call engineer who responds, until they hand over.
- **Communications lead:** posts updates in the incident channel and on the status page. For SEV3 and SEV4 the IC does this.
- **Subject matter experts:** engineers from the owning team who investigate and fix the problem.

## How to declare
1. Create a channel named `#inc-<date>-<short-name>` and post in #incidents: the severity, what is broken, and who is IC.
2. Page the owning team's on-call through the on-call paging tool.
3. Start a timeline in the channel. Write down what you see and every change you make, with the time.

## Escalation path
Escalate when nobody answers, or when the problem is outside your knowledge.
1. **Primary on-call** of the owning team. Must acknowledge within 5 minutes for SEV1 and SEV2.
2. **Secondary on-call** of the same team, if there's no acknowledgement after 10 minutes.
3. **Team lead** of the owning team.
4. **Platform team on-call**, for Kubernetes, nodes, networking, CI/CD, ingress and certificates.
5. **Data team on-call**, for PostgreSQL, PgBouncer, Redis, RabbitMQ and backups.
6. **Engineering manager on duty**, for every SEV1, and for any SEV2 that lasts more than 1 hour.
7. **Security team**, immediately, for any suspected breach, leaked secret, or unknown process. Don't discuss the details in public channels.

To find the owning team of a service, see "Service overview and architecture".

## Communication
- Keep all discussion in the incident channel so the timeline is in one place.
- For SEV1, update the public status page within 15 minutes, then every 30 minutes.
- Never paste passwords, tokens or customer personal data into the channel or tickets.

## After the incident
- The IC closes the incident when the impact has ended and monitoring has been stable for 30 minutes.
- SEV1 and SEV2 need a blameless postmortem within 5 business days: timeline, root cause, what went well, what went wrong, and action items with owners and due dates.
- Update the runbook that would have helped, or write a new one.
