# 502, 503 or 504 errors from the ingress

## Symptoms
- Users see `502 Bad Gateway`, `503 Service Temporarily Unavailable` or `504 Gateway Time-out` pages from nginx.
- The alert "High 5xx rate on ingress" fires.
- The application pods may look healthy, and the app's own logs may show nothing.

## What each code means
| Code | Meaning at ingress-nginx |
|------|--------------------------|
| 502 | The ingress reached the pod but the connection failed or was closed (app crashed, wrong port, app closed a keep-alive connection) |
| 503 | The service has no ready endpoints (all pods not ready, or the selector matches no pods) |
| 504 | The pod accepted the request but didn't answer within the proxy timeout (60 seconds by default) |

## Likely causes
- All pods fail their readiness probe or are crash-looping.
- The Service `targetPort` doesn't match the port the container listens on.
- The Service selector doesn't match the pod labels, often after a label was renamed.
- A slow endpoint: a slow database query, or a slow external API such as the payment provider.
- Pods were killed during a deploy without a graceful shutdown.
- The app's keep-alive timeout is shorter than nginx's, which causes random 502s.

## How to diagnose
```bash
kubectl get ingress -n prod
kubectl describe ingress <name> -n prod
kubectl get endpointslices -n prod -l kubernetes.io/service-name=<service>
kubectl get svc <service> -n prod -o yaml | grep -A 4 ports
kubectl get pods -n prod -l app=<name>
kubectl logs -n ingress-nginx deploy/ingress-nginx-controller --tail 200 | grep <host-or-path>
```

Skip the ingress to see whether the app itself works:

```bash
kubectl port-forward svc/<service> 8080:80 -n prod
curl -i http://localhost:8080/health
```

In the ingress controller logs, `upstream timed out` means a 504, and `connection refused` or `upstream prematurely closed connection` means a 502.

## Fix
- **No endpoints (503):** fix the readiness probe or the crashing pods (see "Kubernetes pod stuck in CrashLoopBackOff"), or fix the Service selector.
- **Wrong port (502):** set the Service `targetPort` to the port the container listens on.
- **Slow requests (504):** find the slow endpoint on the Grafana dashboard and fix the cause. Check the database dashboard for slow queries. Only raise the timeout when the slowness is expected:
  ```yaml
  nginx.ingress.kubernetes.io/proxy-read-timeout: "120"
  ```
- **Errors during deploys:** add a `preStop` hook that sleeps 5–10 seconds, and make the app handle SIGTERM so pods finish in-flight requests before they stop.
- **Random 502s:** make the app's keep-alive timeout longer than nginx's upstream keep-alive timeout.
- **Bad release:** roll back (see "Deploy and rollback procedure").

## Escalate if
- Every service behind the ingress returns errors. The ingress controller itself is probably the problem, so page the Platform team.
- The customer-facing 5xx rate is above 5% for more than 5 minutes. Declare an incident (see "Incident and escalation process").
