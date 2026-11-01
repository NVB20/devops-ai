# Service overview and architecture

## What the platform does
The Orders platform lets customers browse products, place orders and pay online. It runs on a Kubernetes cluster with two namespaces, `staging` and `prod`. Customers use the web app at `app.example.com`, and the public API is at `api.example.com`.

## Request flow
1. The browser loads the single-page app from **web-frontend**.
2. API calls go through the **ingress** (ingress-nginx), which terminates TLS. Certificates are issued and renewed by **cert-manager**.
3. The ingress routes `/orders/*` to **orders-api** and `/payments/*` to **payments-service**.
4. orders-api reads and writes order data in **PostgreSQL** through **PgBouncer**, and caches product data in **Redis**.
5. When an order is placed, orders-api publishes an `order.created` message to **RabbitMQ**.
6. **notifications-worker** consumes the message and sends the confirmation email.

## Services
| Service | What it does | Tech | Owner |
|---------|--------------|------|-------|
| web-frontend | Customer web app (static files served by nginx) | React, nginx | Orders team |
| orders-api | Creates, reads and updates orders; serves the product catalog | Python, FastAPI | Orders team |
| payments-service | Talks to the external payment provider and stores payment status | Python, FastAPI | Payments team |
| notifications-worker | Sends emails for order events from RabbitMQ | Python | Orders team |
| ingress-nginx | Entry point for all traffic: TLS and routing | nginx | Platform team |
| cert-manager | Issues and renews TLS certificates from Let's Encrypt | Kubernetes operator | Platform team |

## Data stores
| Component | Used for | Notes | Owner |
|-----------|----------|-------|-------|
| PostgreSQL | Orders, customers, payments | One primary and one read replica. `max_connections` is 200. All apps connect through PgBouncer | Data team |
| Redis | Product cache and user sessions | Data can be rebuilt. Flushing it in an emergency is safe, but users are logged out | Data team |
| RabbitMQ | Async messages between services | If it's down, orders still work but emails are delayed | Data team |

## Infrastructure and tools
- **Kubernetes:** 6 worker nodes in `prod`. Each service has its Helm chart in its own repository.
- **CI/CD:** every push runs tests and builds an image. A merge to `main` deploys to `staging`; `prod` needs a manual approval (see "Deploy and rollback procedure").
- **Monitoring:** Prometheus collects metrics, Grafana shows one dashboard per service, and Alertmanager sends alerts to the on-call paging tool.
- **Logs:** all container logs go to Loki and can be searched in Grafana.
- **Infrastructure as code:** cloud resources (network, node groups, database servers, DNS records) are managed with Terraform by the Platform team (see "Terraform state lock and drift").
- **Secrets:** kept in the secret manager and synced into Kubernetes Secrets by External Secrets Operator. They are never stored in git, documentation or tickets (see "Secret rotation procedure").
- **Security checks:** every change goes through secret scanning, code and dependency scanning, image scanning and image signing before it can run in `prod` (see "DevSecOps pipeline security gates").
- **Backups:** PostgreSQL is backed up nightly with continuous WAL archiving (see "Database backup and restore procedure").

## What happens when a component is down
| Component down | Customer impact | Severity |
|----------------|-----------------|----------|
| orders-api | Customers can't see or place orders | SEV1 |
| payments-service | Customers can browse but can't pay | SEV1 or SEV2, depending on scope |
| PostgreSQL primary | Almost everything fails | SEV1; page the Data team |
| Redis | Pages are slower and users are logged out | SEV2 |
| notifications-worker | Emails are delayed; messages wait in RabbitMQ and are sent when it recovers | SEV3 |
| web-frontend | The web app doesn't load; the API still works | SEV1 |

## Team contacts
- **Orders team:** #orders-team
- **Payments team:** #payments-team
- **Platform team:** #platform-team, on-call in the paging tool
- **Data team:** #data-team, on-call in the paging tool
- **Security team:** #security, or page them for urgent issues

For severity levels and how to page, see "Incident and escalation process".
