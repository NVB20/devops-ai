# Terraform state lock and drift

## Background
The Platform team manages cloud infrastructure with Terraform: the network, Kubernetes node groups, database servers, DNS records and storage buckets. The state is kept in a remote backend (a storage bucket with versioning and state locking). All changes go through pull requests. CI runs `terraform plan` and posts the result on the PR, and `terraform apply` runs from the pipeline after approval.

## Symptoms
- `Error: Error acquiring the state lock`, with a lock ID, who holds the lock, and when it was created.
- `terraform plan` shows changes that nobody made in code. This is drift.
- `Error: Provider produced inconsistent result after apply`, or a resource fails with "already exists".

## Likely causes
- **Lock:** another plan or apply is running (another pipeline, or someone running Terraform locally), or a run was killed and never released its lock.
- **Drift:** someone changed a resource by hand in the cloud console, another tool or an autoscaler changed it, or a new provider version changed a default.
- **Already exists:** the resource was created by hand and Terraform doesn't know about it.

## How to diagnose
```bash
terraform init
terraform plan
terraform plan -refresh-only       # shows only what changed outside Terraform
terraform state list
terraform state show <resource-address>
```

For a lock, read the lock info in the error (ID, Who, Created). Look for a running Terraform job in the CI pipeline list, and ask the person named in "Who".

For drift, check the cloud provider's audit log to see who changed the resource and when.

## Fix
- **Lock held by a running job:** wait for it to finish.
- **Stale lock (you've confirmed the job is dead):**
  ```bash
  terraform force-unlock <LOCK_ID>
  ```
  Two applies running at the same time can corrupt the state, so only do this when you're sure nothing is running.
- **Drift you want to keep:** change the code to match. `terraform plan` should then show no changes.
- **Drift you want to undo:** run the normal PR and apply. Terraform puts the resource back to what the code says.
- **Resource created outside Terraform:** import it with `terraform import <resource-address> <cloud-resource-id>`, or an `import` block (Terraform 1.5 and later).
- **Before `terraform state mv` or `terraform state rm`:** take a backup with `terraform state pull > backup.tfstate`, and delete it when you're done.

## Security rules
- State files can contain secrets in plain text, such as database passwords and private keys. Never commit `.tfstate` files to git, never paste state into chat or tickets, and delete local state backups after use.
- Don't run `terraform apply` against prod from your laptop.
- Manual changes in the cloud console are allowed only during an incident, and must be added to the code within 2 business days.

## Escalate if
- The state looks corrupted, or resources have disappeared from the state.
- A plan wants to destroy and recreate a database, a cluster, or anything else that holds data. Stop, and ask the Platform team before you apply.
