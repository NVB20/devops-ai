# Kubernetes pod stuck in CrashLoopBackOff

## Symptoms
- `kubectl get pods` shows the pod in `CrashLoopBackOff` and the RESTARTS count keeps going up.
- The alert "KubePodCrashLooping" fires for a deployment.
- The service returns 502/503 errors or gets slower because fewer replicas are ready.
- Kubernetes waits longer between each restart (10s, 20s, 40s, up to 5 minutes), so the pod looks "stuck".

## Likely causes
- The application exits on startup: a missing environment variable, a bad config value, or a failed database migration.
- A ConfigMap or Secret the pod needs doesn't exist, or the key name is wrong.
- The liveness probe is too strict and kills the container before it finishes starting.
- The container is OOMKilled because its memory limit is too low.
- Wrong image tag, entrypoint or command (for example, a command that exits right away).
- A dependency such as PostgreSQL or Redis is unreachable and the app exits instead of retrying.
- File permission problems: the container runs as non-root but writes to a protected path, or the root filesystem is read-only.

## How to diagnose
Start with the pod status, the events, and the logs from the previous (crashed) container:

```bash
kubectl get pods -n <namespace>
kubectl describe pod <pod-name> -n <namespace>
kubectl logs <pod-name> -n <namespace> --previous
kubectl get events -n <namespace> --sort-by=.lastTimestamp
```

In the `describe` output, look at "Last State: Terminated", the "Reason" and the "Exit Code":

| Exit code | Usual meaning |
|-----------|---------------|
| 0 | The process finished normally; the command is not a long-running process |
| 1 | Application error; read the logs |
| 126 / 127 | Command not executable / not found; check the entrypoint |
| 137 | Killed (SIGKILL); usually OOMKilled or a failed liveness probe |
| 139 | Segmentation fault |
| 143 | Terminated (SIGTERM); often a liveness probe restart |

Then check what changed recently:

```bash
kubectl rollout history deployment/<name> -n <namespace>
kubectl top pod <pod-name> -n <namespace>
```

If a deploy happened in the last hour, the new release is the most likely cause.

## Fix
- **Missing config or secret:** create or correct the ConfigMap/Secret, then restart the pods: `kubectl rollout restart deployment/<name> -n <namespace>`.
- **OOMKilled:** raise `resources.limits.memory` in the Helm values, or fix the memory leak. See the "High CPU or memory usage" runbook.
- **Liveness probe too strict:** add a `startupProbe`, or increase `initialDelaySeconds` and `failureThreshold`.
- **Bad release:** roll back with `kubectl rollout undo deployment/<name> -n <namespace>`. See the "Deploy and rollback procedure".
- **Dependency down:** fix the dependency first. See the "Database connection errors" runbook.

Deleting the pod again and again does not fix anything. The new pod will crash for the same reason.

## Escalate if
- Several different services are crash-looping at the same time. This points to a node or cluster problem, so page the Platform team on-call.
- Rolling back does not stop the crashes.
- A customer-facing service in `prod` has zero ready replicas for more than 10 minutes. Declare a SEV2 (see "Incident and escalation process").
