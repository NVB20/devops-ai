# Vulnerable dependencies in application code

## Symptoms
- The pipeline fails at the "dependency-scan" stage (pip-audit) with a list of vulnerable packages.
- Dependabot opens pull requests titled "Bump <package> from X to Y".
- The image scan (Trivy) reports a CVE in a Python package.

## Likely causes
- A direct dependency in `requirements.txt` has a published vulnerability.
- A **transitive** dependency (a dependency of one of our dependencies) is vulnerable, and we never listed it ourselves.
- Versions are not pinned, so a build picked up an old or unexpected version.
- The project hasn't had its dependencies updated in months.

## How to diagnose
```bash
pip install pip-audit pipdeptree
pip-audit -r requirements.txt
pip-audit -r requirements.txt --desc       # include the vulnerability descriptions
pipdeptree -r -p <package>                 # which packages pull this one in
pip index versions <package>               # available versions
```

For each finding, check:
1. Which version fixes it (the "Fix Versions" column).
2. Is it a direct or a transitive dependency?
3. Does our code use the vulnerable function? Read the advisory linked from the GHSA or CVE ID.
4. Does the fixed version have breaking changes? Read the changelog.

The fix deadlines are the same as for image CVEs (see "Container image vulnerabilities").

## Fix
- **Direct dependency:** raise its version in `requirements.txt` to at least the fixed version, run the tests, and deploy.
- **Transitive dependency:** first try upgrading the direct dependency that pulls it in. If that isn't possible, pin the safe version in a constraints file:
  ```bash
  pip install -r requirements.txt -c constraints.txt
  ```
- **Dependabot PRs:** review them like any other PR. The pipeline runs the tests, so merge when it's green. Security patches must be merged before the deadline, not left open.
- **No fixed version:** look for a workaround in the advisory, such as a config change or turning off a feature. If the vulnerable code isn't reachable, record a time-limited exception with the Security team's approval:
  ```bash
  pip-audit -r requirements.txt --ignore-vuln <VULN-ID>
  ```
  Put the ignore in the pipeline config, with a comment and an expiry date, not only on your laptop.
- **Prevent drift:** pin every version (`package==1.2.3`) and generate a full lock file with `pip-compile` (pip-tools) or `uv pip compile`, so every build installs the same versions.

Don't rush through several major-version upgrades at once. Upgrade only the vulnerable package, test, deploy, and do bigger upgrades separately.

## Escalate if
- The vulnerability is actively exploited and the package is used by an internet-facing service such as orders-api or payments-service. Contact the Security team.
- The fix needs a major upgrade that breaks the app and the deadline can't be met. Ask the Security team for a documented exception.
