# Kubernetes NetworkPolicy blocking traffic

## Symptoms
- A service can't reach another service, PostgreSQL, Redis or an external API, and the requests **time out**. ("Connection refused" usually means something else: the target is down or listening on another port.)
- It started after a new service was deployed, a label was renamed, or a new external dependency was added.
- DNS lookups fail in a new namespace (see "DNS resolution failures in Kubernetes").

## Background
The `prod` namespace uses **default deny**: a pod can't receive or send any traffic unless a NetworkPolicy allows it. If an attacker takes over one pod, this limits what they can reach. The allowed flows follow the architecture (see "Service overview and architecture"):

| From | To | Port |
|------|----|------|
| ingress-nginx | web-frontend, orders-api, payments-service | the app's port |
| orders-api, payments-service | PgBouncer | 5432 |
| orders-api | Redis | 6379 |
| orders-api, notifications-worker | RabbitMQ | 5672 |
| payments-service | External payment provider | 443 |
| notifications-worker | External email provider | 443 |
| All pods | kube-dns in `kube-system` | 53 UDP and TCP |
| Prometheus | All pods | Metrics port |

## How to diagnose
```bash
kubectl get networkpolicy -n prod
kubectl describe networkpolicy <name> -n prod
kubectl get pods -n prod --show-labels
```

Test the connection from the source pod:

```bash
kubectl exec -n prod deploy/orders-api -- nc -zv -w 3 pgbouncer 5432
```

If the image has no `nc`, use a temporary debug container. It shares the pod's network, so the same policies apply:

```bash
kubectl debug -n prod <pod-name> -it --image=busybox:1.36 -- nc -zv -w 3 pgbouncer 5432
```

A timeout means the traffic is blocked (or the target is down). "open" means it's allowed. Compare the source and target pod labels with the `podSelector`, `from` and `to` selectors in the policies. A renamed label is the most common cause.

## Fix
Add a policy that allows exactly the flow you need. For example, to let a new service `reports-api` reach PgBouncer:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: pgbouncer-allow-reports-api
  namespace: prod
spec:
  podSelector:
    matchLabels:
      app: pgbouncer
  policyTypes: ["Ingress"]
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: reports-api
      ports:
        - protocol: TCP
          port: 5432
```

Egress is denied by default too, so `reports-api` also needs an egress rule to PgBouncer on port 5432, and one to DNS.

Keep NetworkPolicies in the service's Helm chart, so changes are reviewed in pull requests.

## Don't
- Don't delete the default-deny policy, or add an "allow all" policy, to fix a problem. That removes the protection for every service in the namespace.
- Don't open egress to `0.0.0.0/0`. Allow only the address ranges the external provider publishes.

## Escalate if
- Traffic is blocked even though a matching policy exists. This may be a network plugin problem, so contact the Platform team.
- You need a new external destination in prod. Ask the Security team to review it.
