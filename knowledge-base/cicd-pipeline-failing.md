# CI/CD pipeline failing

## Symptoms
- The pipeline is red and the pull request can't be merged.
- A merge to `main` didn't deploy to `staging`.
- A job is stuck in "queued" or "pending" for a long time.
- The same pipeline passes on one run and fails on the next with no code change.

## Likely causes
- A real test failure caused by the code change.
- A flaky test (depends on timing, test order, or an external service).
- A dependency changed: a new library version, or a package registry is down.
- Lint or formatting errors.
- Expired or rotated credentials for the container registry or the cloud account.
- The CI runner is out of disk space or memory.
- A corrupted build cache.
- Docker Hub rate limits on image pulls.
- All runners are offline or busy.

## How to diagnose
1. Open the failed job log and find the **first** error, not the last one. Later errors are often side effects.
2. Check if `main` is also failing. If yes, the problem is not in your branch.
3. Retry the job once. If it passes, the failure is probably flaky.
4. Run the same steps locally:
   ```bash
   pip install -r requirements.txt
   pytest
   docker build -t test-image .
   ```
5. Compare with the last green run: which commits, lock files or base image changed?

Common error messages and what they mean:

| Error in the log | Likely cause |
|------------------|--------------|
| `401 Unauthorized`, `denied: requested access to the resource is denied` | Registry or cloud credentials expired or missing |
| `toomanyrequests: You have reached your pull rate limit` | Docker Hub rate limit |
| `No space left on device` | Runner disk is full |
| `Killed` or exit code 137 | Runner ran out of memory |
| `ModuleNotFoundError`, `Cannot find module` | Dependency missing from requirements or lock file |
| `Could not resolve host` | Network or DNS problem on the runner |
| Job cancelled after a fixed time | Job timeout; the step is too slow or hanging |

## Fix
- **Real test failure:** fix the code. Don't skip or delete the test to make the pipeline green.
- **Flaky test:** rerun to unblock, open a ticket, and mark the test as quarantined with an owner and a date.
- **Dependency change:** pin the version in `requirements.txt` or the lock file.
- **Expired credentials:** ask the Platform team to update the secret in the CI secret store. Never paste credentials into pipeline files, commit messages or job logs.
- **Corrupted cache:** clear the pipeline cache and rerun.
- **Runner disk or memory:** clean the runner or move the job to a bigger runner. Contact the Platform team for shared runners.
- **Rate limits:** pull base images from the internal registry mirror instead of Docker Hub.

## Escalate if
- `main` has been red for more than 1 hour and blocks releases. This is a SEV3 (see "Incident and escalation process").
- Runners are down for all teams. Contact the Platform team.
- A secret appears in a job log or in git history. Contact the Security team immediately so the secret can be rotated, and don't just delete the log (see "Leaked secret response").
