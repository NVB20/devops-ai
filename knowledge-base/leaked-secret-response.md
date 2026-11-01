# Leaked secret response

## Symptoms
- The secret scanner (gitleaks) fails a pipeline or a pre-commit hook with "leaks found".
- GitHub secret scanning or push protection reports a secret.
- Someone sees a password, token, API key or private key in a commit, log, chat message, ticket, screenshot or document.
- An external provider tells us one of our keys was found in public.

## What counts as a leak
Any secret that was visible to people who shouldn't have it, or stored somewhere secrets don't belong. A secret committed to git is leaked even if the commit was removed a minute later, because it may already be in clones, forks, CI caches and logs. Treat it as compromised.

## Severity
| Situation | Severity |
|-----------|----------|
| Prod credential in a public place (public repo, public paste site, public log) | SEV1 |
| Prod credential in an internal place (private repo, internal chat, ticket) | SEV2 |
| Staging or dev credential, or a credential that has already expired | SEV3 |

## What to do
1. **Tell the Security team right away**, in a private message or by paging them. Don't post the secret, or where it is, in public channels.
2. **Revoke or rotate the secret first.** This is the real fix. Cleaning git history without rotating doesn't help. Follow "Secret rotation procedure" for that type of secret.
3. **Check whether it was used.** With the Security team, review the provider's audit logs (payment provider dashboard, cloud audit log, database connection logs) from the time of the leak until the rotation.
4. **Remove it from where it leaked:**
   - **Git:** remove the file in a new commit, then clean the history with `git filter-repo`. The Platform team coordinates this, because it rewrites history, needs a force push, and everyone has to clone the repository again.
   - **Logs:** ask the Platform team to delete the log lines in Loki, and fix the code that logged the secret.
   - **Chat or tickets:** delete the message and ask the tool's admin to purge it.
5. **Record it** in the incident channel. SEV1 and SEV2 need a postmortem.

## How to find secrets in a repository
```bash
gitleaks detect --source . -v          # scan the whole git history
gitleaks protect --staged -v           # scan only what you are about to commit
```

Newer gitleaks versions (8.19 and later) use `gitleaks git` and `gitleaks dir` instead. Check `gitleaks --help`.

## Prevention
- Install the pre-commit hook. The repository's `.pre-commit-config.yaml` runs gitleaks before each commit; enable it once with `pre-commit install`.
- Keep secrets only in the secret manager. Apps read them from environment variables or mounted files.
- Add `.env` and `*.tfstate` to `.gitignore`.
- Never log full request headers, connection strings or environment variables.

## Escalate if
Always escalate to the Security team. For a SEV1, also page the engineering manager on duty (see "Incident and escalation process").
