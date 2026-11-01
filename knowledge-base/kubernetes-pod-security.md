# Kubernetes pod security (Pod Security Admission)

## Symptoms
- After a deploy, the Deployment creates no new pods.
- The ReplicaSet events show `FailedCreate` with a message like:
  ```
  pods "orders-api-7d9f..." is forbidden: violates PodSecurity "restricted:latest":
  allowPrivilegeEscalation != false, unrestricted capabilities, runAsNonRoot != true,
  seccompProfile not set
  ```
- After hardening, the container starts but fails with `Permission denied` or `Read-only file system`.
- Kyverno rejects the pod with a policy message, such as "image must be signed" or "image registry not allowed".

## Background
The `prod` and `staging` namespaces enforce the **restricted** Pod Security Standard with this namespace label:

```yaml
pod-security.kubernetes.io/enforce: restricted
```

Every pod must:
- run as a non-root user,
- not allow privilege escalation,
- drop all Linux capabilities,
- use the `RuntimeDefault` seccomp profile,
- not use host networking, host paths or privileged mode.

Our own standard also requires a read-only root filesystem, and resource requests and limits on every container.

## How to diagnose
```bash
kubectl get events -n <namespace> --field-selector reason=FailedCreate
kubectl describe replicaset -n <namespace> -l app=<name>
kubectl get namespace <namespace> --show-labels
```

Test the manifests before deploying. A server-side dry run goes through admission, so it shows the same errors:

```bash
helm template <release> ./chart -f values-prod.yaml | kubectl apply --dry-run=server -f -
```

## Fix
Add this to each container in the Helm chart:

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 10001
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  capabilities:
    drop: ["ALL"]
  seccompProfile:
    type: RuntimeDefault
```

Make the image run as that user. In the Dockerfile:

```dockerfile
RUN useradd --uid 10001 --no-create-home appuser
COPY --chown=10001:10001 app/ /app/
USER 10001
```

With a read-only root filesystem the app can't write anywhere in the image. Mount an `emptyDir` for paths that need writes, such as `/tmp`: add `volumes: [{name: tmp, emptyDir: {}}]` to the pod spec and `volumeMounts: [{name: tmp, mountPath: /tmp}]` to the container.

Other common problems:
- **Port below 1024:** a non-root user can't listen on ports under 1024. Listen on 8000 or 8080, and let the Service map port 80 to it.
- **Permission denied on files:** make sure files copied into the image are owned by or readable for UID 10001 (`COPY --chown`).

## Exceptions
Some system tools, such as log collectors, the network plugin and monitoring agents, need more privileges. They run in their own namespaces with a `baseline` or `privileged` label set by the Platform team. Application teams don't get exceptions in `prod`, and must not change namespace labels themselves.

## Escalate if
- A third-party tool you need can't run under "restricted". Ask the Platform and Security teams for a reviewed exception.
- You find a privileged pod in an application namespace. That shouldn't be possible, so tell the Security team (see "Suspected compromised host or container").
