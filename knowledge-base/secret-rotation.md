# Secret rotation procedure

## When to rotate
- On a schedule: every 90 days for database passwords and API keys, and before expiry for certificates.
- Immediately after a leak (see "Leaked secret response").
- When someone who had access leaves the team or the company.
- When a secret was shared in an insecure way, even internally.

## Where secrets live
All application secrets are stored in the secret manager. External Secrets Operator syncs them into Kubernetes Secrets in each namespace, and pods read them as environment variables or files. Secrets are never stored in git, Helm values, Dockerfiles, documentation, tickets or chat.

## General steps (no downtime)
The idea is to keep both the old and the new secret valid for a short time, so the app never breaks.
1. **Create the new credential** next to the old one: a second API key, a second database role, or a new password while the old one still works.
2. **Store it** in the secret manager under the same name, as a new version.
3. **Sync it** to Kubernetes. The operator refreshes on a schedule; to force it now:
   ```bash
   kubectl annotate externalsecret <name> -n <namespace> force-sync=$(date +%s) --overwrite
   kubectl get externalsecret <name> -n <namespace>     # STATUS should be SecretSynced
   ```
4. **Restart the pods** so they read the new value. Environment variables are only read when the container starts.
   ```bash
   kubectl rollout restart deployment/<name> -n <namespace>
   kubectl rollout status deployment/<name> -n <namespace>
   ```
5. **Check** that the app works: health checks, error rate, and no authentication errors in the logs.
6. **Revoke the old credential.**
7. **Record** the rotation in the rotation ticket: date, secret name and who did it. Never write the value itself.

## Specific secrets
- **PostgreSQL app password:** the Data team sets the new password in `psql` with `\password <role>`. It prompts for the password, so it never appears in shell history or logs. The old password stops working right away, so for zero downtime use two login roles (for example `orders_app_a` and `orders_app_b`) and switch the app from one to the other.
- **Payment provider API key:** the Payments team creates a second key in the provider's dashboard, rolls it out, then deletes the old key.
- **Container registry pull credentials:** the Platform team rotates them. Check afterwards that new pods can still pull images (see "Kubernetes pod stuck in ImagePullBackOff").
- **TLS certificates:** cert-manager renews them automatically (see "SSL certificate expired").
- **CI/CD secrets:** the Platform team updates them in the CI secret store.

## Don't
- Don't send a secret by email or chat, even to a teammate. Give them access to the entry in the secret manager instead.
- Don't decode a Kubernetes Secret with `base64 -d` and paste the output anywhere.
- Don't reuse the same secret in different environments.

## Escalate if
- The new secret breaks the app and the old one is already revoked. Switch back to the previous version in the secret manager if it's still valid, and declare an incident (see "Incident and escalation process").
- You don't know which systems use the secret. Ask the owning team before you revoke anything.
