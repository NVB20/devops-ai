# Container image vulnerabilities

## Symptoms
- The pipeline fails at the "image-scan" stage with a list of `CRITICAL` or `HIGH` vulnerabilities (CVEs).
- The nightly scan report lists CVEs in an image that is running in prod.
- The Security team opens a ticket about a CVE in one of our images.

## How scanning works
Trivy scans every image the pipeline builds. It also rescans every image running in prod each night, because new CVEs are published every day; an image that was clean last week can fail today. It reports two kinds of findings:
- **OS packages** from the base image, such as `openssl` or `glibc`.
- **Application dependencies** inside the image, such as Python packages from `requirements.txt`.

## Fix deadlines
| Severity | Fix within |
|----------|------------|
| Critical | 7 days (48 hours if the service is internet-facing and a public exploit exists) |
| High | 30 days |
| Medium | 90 days |
| Low | Next routine update |

The pipeline blocks on Critical findings, and on High findings when a fixed version exists.

## How to diagnose
Run the same scan locally:

```bash
trivy image --severity HIGH,CRITICAL registry.example.com/<service>:<tag>
trivy image --severity HIGH,CRITICAL --ignore-unfixed registry.example.com/<service>:<tag>
```

For each finding, read:
- **Library and type:** an OS package or a Python package?
- **Installed Version and Fixed Version:** if Fixed Version is empty, there's no fix yet.
- **Is it reachable?** A vulnerable library our code never loads is lower risk, but it still counts.

Scan the base image too:

```bash
trivy image --severity HIGH,CRITICAL python:3.12-slim
```

If the base image has the same CVEs, the fix is to update the base image, not your code.

## Fix
- **OS package CVEs:** rebuild on the latest patch of the base image. Pin the base image to a version such as `python:3.12-slim` (never `latest`), and let the weekly pipeline rebuild pick up patches.
- **Use a smaller base image:** switch from a full image to `-slim` or a distroless image. Fewer packages means fewer CVEs.
- **Remove what you don't need:** compilers and build tools belong in the build stage of a multi-stage Dockerfile, not in the final image.
- **Python package CVEs:** see "Vulnerable dependencies in application code".
- **No fix available:** add a time-limited exception to `.trivyignore` with a comment explaining why the risk is acceptable, and get the Security team's approval in the PR:
  ```
  # openssl CVE in the base image, no fix released yet, not reachable from our code
  CVE-YYYY-NNNNN exp:2026-12-31
  ```
  Exceptions without an expiry date are rejected.

After the fix, rebuild, scan again, and deploy.

## Escalate if
- The CVE is known to be actively exploited (for example, it's on the CISA KEV list) and affects an internet-facing service. Contact the Security team the same day; this can be a SEV2.
- The fix needs a major version upgrade that the owning team can't finish before the deadline.
