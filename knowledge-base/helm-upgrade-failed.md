# Helm upgrade failed or release stuck

## Symptoms
The deploy stage in the pipeline fails with one of these errors:
- `Error: UPGRADE FAILED: another operation (install/upgrade/rollback) is in progress`
- `Error: UPGRADE FAILED: timed out waiting for the condition` or `context deadline exceeded`
- `rendered manifests contain a resource that already exists`
- `cannot patch "..." with kind Deployment: ... field is immutable`

`helm list -n <namespace> -a` shows the release as `pending-upgrade`, `pending-install`, `pending-rollback` or `failed`.

## Likely causes
- A previous pipeline run was cancelled, or its runner died, in the middle of `helm upgrade`. The release is left locked in a `pending-*` state.
- The new pods never became ready (crash loop, image pull error, failing probe), so `--atomic` timed out and rolled back.
- A resource was created by hand with `kubectl apply`, and Helm doesn't own it.
- The chart changed a field Kubernetes doesn't allow you to change, such as a Deployment's `spec.selector`.

## How to diagnose
```bash
helm list -n <namespace> -a
helm status <release> -n <namespace>
helm history <release> -n <namespace>
helm get values <release> -n <namespace>
kubectl get pods -n <namespace> -l app.kubernetes.io/instance=<release>
```

Preview what the chart will create:

```bash
helm template <release> ./chart -f values-prod.yaml | less
helm diff upgrade <release> ./chart -n <namespace> -f values-prod.yaml   # needs the helm-diff plugin
```

If the error was a timeout, the real problem is in the pods. Check their events and logs.

## Fix
- **Stuck in `pending-upgrade`:** first make sure no other pipeline is deploying this service. Then roll back to the last revision with status `deployed` in `helm history`, and rerun the pipeline:
  ```bash
  helm rollback <release> <last-deployed-revision> -n <namespace>
  ```
- **Timed out:** fix the pod problem (see "Kubernetes pod stuck in CrashLoopBackOff" and "Kubernetes pod stuck in ImagePullBackOff"), then deploy again.
- **Resource already exists:** let Helm adopt it by adding the ownership label and annotations:
  ```bash
  kubectl label <kind> <name> -n <namespace> app.kubernetes.io/managed-by=Helm
  kubectl annotate <kind> <name> -n <namespace> \
    meta.helm.sh/release-name=<release> meta.helm.sh/release-namespace=<namespace>
  ```
- **Immutable field:** the resource has to be deleted and created again. For a Deployment that means downtime, unless you first deploy the new version under a new name. Plan it with the owning team, outside peak hours.

Helm keeps the release history in Kubernetes Secrets named `sh.helm.release.v1.<release>.v<number>`. Don't delete them to unstick a release unless the Platform team agrees, because you lose the rollback history.

## Escalate if
- The rollback fails too.
- A prod release has been broken for more than 15 minutes (see "Incident and escalation process").
