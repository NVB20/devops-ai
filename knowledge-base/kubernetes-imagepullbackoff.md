# Kubernetes pod stuck in ImagePullBackOff

## Symptoms
- `kubectl get pods` shows `ErrImagePull` first, then `ImagePullBackOff`.
- The pod never starts, so there are no application logs.
- A deploy hangs and `kubectl rollout status` never finishes. With `helm upgrade --atomic` it times out and rolls back.

## Likely causes
- The image tag doesn't exist: a typo, or the pipeline failed before it pushed the image.
- The image is in a private registry and the pod has no `imagePullSecrets`, or the pull credentials expired.
- Docker Hub rate limits (`toomanyrequests`).
- The image was built only for another CPU architecture (for example arm64 on amd64 nodes).
- The nodes can't reach the registry: firewall, DNS, or the registry is down.
- An admission policy only allows images from `registry.example.com`, but the image comes from somewhere else.

## How to diagnose
```bash
kubectl describe pod <pod-name> -n <namespace>
kubectl get events -n <namespace> --field-selector reason=Failed
```

The "Events" section shows the real error:

| Error message | Meaning |
|---------------|---------|
| `manifest unknown`, `not found` | The tag or image name doesn't exist |
| `pull access denied`, `unauthorized: authentication required` | Missing or expired pull credentials |
| `toomanyrequests` | Registry rate limit |
| `no matching manifest for linux/amd64` | Image built for a different architecture |
| `i/o timeout`, `connection refused` | The node can't reach the registry |

Check that the image exists:

```bash
docker manifest inspect registry.example.com/<service>:<tag>
```

Check which pull secret the pod uses and that it exists. Don't print or decode its contents:

```bash
kubectl get pod <pod-name> -n <namespace> -o jsonpath='{.spec.imagePullSecrets}'
kubectl get secret <pull-secret-name> -n <namespace>
```

## Fix
- **Wrong tag:** deploy a tag that exists. Tags are git commit SHAs, so check the pipeline run that should have pushed it. If the push step failed, rerun the pipeline.
- **Missing or expired credentials:** pull credentials for `registry.example.com` are managed by the Platform team in the secret manager and synced into each namespace. Ask them to refresh the secret (see "Secret rotation procedure").
- **Rate limit:** use the internal registry mirror instead of Docker Hub, both in the Dockerfile `FROM` line and in the Helm values.
- **Wrong architecture:** rebuild with `docker buildx build --platform linux/amd64 -t <image> .`
- **Network:** from a debug pod, `curl -sI https://registry.example.com/v2/` should return `200` or `401`, not a timeout.
- **Image from an unapproved registry:** bring the image into `registry.example.com` through the pipeline so it gets scanned and signed (see "DevSecOps pipeline security gates").

Kubernetes retries the pull with a growing delay. After you fix the cause, `kubectl delete pod <pod-name> -n <namespace>` makes it retry right away.

## Escalate if
- Pods in many namespaces fail to pull at the same time. This means a registry outage or expired shared credentials, so contact the Platform team.
- A prod fix during an incident is blocked by the pull error. Tell the incident commander.
