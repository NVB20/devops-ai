# Static code analysis (SAST) findings in the pipeline

## Symptoms
- The pipeline fails at the "sast" stage. Semgrep or Bandit reports issues with a rule ID, a file and a line number.
- The scanner posts a comment on the pull request listing new findings.

## How it works
Every pull request is scanned with Semgrep (rules for Python, Dockerfiles and Kubernetes YAML) and Bandit (Python security checks). Only **new** findings in the changed code block the merge; older findings are tracked in the security backlog. High-severity findings block the merge, while medium and low findings are shown as warnings.

## How to diagnose
Run the scanners locally on your branch:

```bash
pip install bandit semgrep
bandit -r app/ -ll                                       # medium and high severity only
semgrep scan --config p/python --config p/secrets app/
```

For each finding, read the rule description and the line it points to. Then ask: can untrusted input (an HTTP request, a queue message, an uploaded file) reach this line?

## Common findings and fixes (Python)
| Finding | Risk | Fix |
|---------|------|-----|
| SQL built with f-strings or `+` | SQL injection | Use query parameters: `cur.execute("SELECT * FROM orders WHERE id = %s", (order_id,))` |
| `subprocess` with `shell=True` | Command injection | Pass a list of arguments, without `shell=True`: `subprocess.run(["ls", path], check=True)` |
| `yaml.load(data)` | Code execution | Use `yaml.safe_load(data)` |
| `pickle.loads` on data from outside | Code execution | Use JSON |
| `requests.get(url, verify=False)` | Man-in-the-middle attacks | Keep TLS verification on, and fix the CA bundle instead |
| Hard-coded password or token | Secret leak | Read it from an environment variable filled from the secret manager, and treat the old value as leaked (see "Leaked secret response") |
| `hashlib.md5` or `sha1` for passwords | Weak hashing | Use a password hashing library such as bcrypt or argon2 |
| `random` used for tokens or IDs | Predictable values | Use the `secrets` module |

## False positives
If a finding isn't a real risk, suppress it on that line only, with a reason the reviewer can check:

```python
uvicorn.run(app, host="0.0.0.0", port=8000)  # nosec B104 - runs in a container, reachable only through the Service
```

For Semgrep, use `# nosemgrep: <rule-id>` followed by the reason.

Every suppression must be approved in the PR review by your team's security champion. Never suppress a whole file, or turn off a rule globally, just to make the pipeline pass.

## Escalate if
- The finding is in code that is already in prod, and the input can come from the internet. Tell the Security team; they decide whether it's an incident.
- You're not sure whether it's a real issue. Ask in #security.
