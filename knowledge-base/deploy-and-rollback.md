# Deploy and rollback procedure

## When to use
Use this procedure to release a new version of a service to `staging` or `prod`, and to roll back a release that causes problems. All services run on Kubernetes and are deployed with Helm by the CI/CD pipeline.

## Before you deploy
- The pull request is approved and merged to `main`, and the pipeline is green.
- The change has run in `staging` for at least 30 minutes with no new errors.
- Database migrations are backward compatible: the old version of the code must still work with the new schema. Never drop or rename a column in the same release that stops using it.
- You know the current version, so you can roll back to it:
  ```bash
  helm history <release> -n prod
  ```
- Don't deploy to `prod` on Friday after 15:00, on public holidays, or during an open incident, unless the deploy is the fix.
- Post in #deployments: the service name, the version (git commit SHA) and a one-line summary.

## How to deploy
1. Merging to `main` builds the image, tags it with the git commit SHA, and pushes it to the container registry.
2. The pipeline deploys automatically to `staging`.
3. To deploy to `prod`, open the pipeline run and approve the "deploy-prod" stage. The pipeline runs:
   ```bash
   helm upgrade --install <release> ./chart -n prod --set image.tag=<git-sha> --atomic --timeout 10m
   ```
   `--atomic` rolls back automatically if the new pods don't become ready in time.

Don't deploy to `prod` by running `helm` or `kubectl apply` from your laptop. The only exception is during an incident, with approval from the incident commander.

## Verify the deploy
```bash
kubectl rollout status deployment/<name> -n prod
kubectl get pods -n prod -l app=<name>
curl -s https://app.example.com/health
```

For the next 15 minutes, watch the service's Grafana dashboard: error rate, p95 latency, and pod restarts. Search the logs in Loki for new error messages.

## How to roll back
If the new version raises the error rate, fails health checks, or crash-loops, roll back first and investigate after.

```bash
helm history <release> -n prod
helm rollback <release> <previous-revision> -n prod
kubectl rollout status deployment/<name> -n prod
```

If the service is not managed by Helm:

```bash
kubectl rollout undo deployment/<name> -n prod
```

After the rollback:
- Revert the bad commit in git, so the next pipeline run doesn't deploy it again.
- Post in #deployments that the release was rolled back and why.
- Rolling back the code does **not** roll back database migrations. If a migration caused the problem, contact the Data team before changing the schema.

## Escalate if
- The rollback fails, or the previous version fails too.
- The bad release wrote wrong data or deleted data.
- Customers are still affected 15 minutes after the rollback. Declare an incident (see "Incident and escalation process").
