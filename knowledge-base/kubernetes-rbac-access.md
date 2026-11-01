# Kubernetes access and RBAC (Forbidden errors)

## Symptoms
- `kubectl` returns errors like:
  ```
  Error from server (Forbidden): pods is forbidden: User "dev@example.com" cannot list resource "pods"
  in API group "" in the namespace "prod"
  ```
- The CI deploy job fails with `forbidden` for its service account.
- An application that calls the Kubernetes API gets `403` responses.

## Access model
We follow least privilege: everyone gets the minimum access their job needs, and write access to prod is time-limited.

| Who | staging | prod |
|-----|---------|------|
| Developers | `edit` (deploy, exec, logs) | `view` (read-only; can't read Secrets) |
| On-call engineers | `edit` | `view`, plus `edit` for 4 hours through a break-glass request |
| Platform team | `admin` | `admin` through break-glass, audited |
| CI deploy pipeline | `ci-deployer` service account, limited to its own namespace | Same, and only from the `deploy-prod` stage |
| Applications | Their own service account, with no API access unless they need it | Same |

Nobody uses `cluster-admin` for daily work. The Kubernetes audit log records every action in `prod`.

## How to diagnose
Check who you are and what you're allowed to do:

```bash
kubectl auth whoami
kubectl auth can-i --list -n <namespace>
kubectl auth can-i get pods -n prod
```

Check a service account (this needs permission to impersonate, which the Platform team has):

```bash
kubectl auth can-i update deployments -n prod --as=system:serviceaccount:prod:ci-deployer
kubectl get rolebindings -n prod -o wide
kubectl describe role <role-name> -n prod
```

The error message tells you exactly what is missing: the verb (`list`), the resource (`pods`), the API group and the namespace.

## Fix
- **You need more access:** open an access request ticket with the namespace, the access level and the reason. Your team lead approves it and the Platform team applies it. During an incident, use the break-glass request in the access portal; it expires after 4 hours.
- **The CI service account is missing a permission:** the Platform team adds that specific verb and resource to its Role, through a PR in the cluster config repository. Never bind CI to `cluster-admin`.
- **An application needs the Kubernetes API:** create a dedicated service account and a Role with only the verbs and resources it needs. Apps that don't need the API should set `automountServiceAccountToken: false` in the pod spec.

## Don't
- Don't share your kubeconfig, or use someone else's, to get access quickly.
- Don't create RoleBindings to give yourself access, even if you're able to.
- Don't ask for `cluster-admin` to fix one missing permission.

## Escalate if
- You need break-glass access and the access portal is down. Page the Platform team.
- You see RoleBindings you don't recognise, or actions in the audit log from an unknown identity. Contact the Security team (see "Suspected compromised host or container").
