# DevSecOps pipeline security gates

## Purpose
Security checks run automatically at every step from commit to production, so problems are found early, when they are cheap to fix ("shift left"). This document lists which checks run, where they run, and what they block. Use it to answer questions like "why did my pipeline fail at a security step?" or "what checks does code go through before it reaches prod?".

## The stages
| Stage | Check | Tool | Blocks when |
|-------|-------|------|-------------|
| Developer laptop | Secret scan before commit | gitleaks (pre-commit hook) | A secret is found |
| Pull request | Secret scan | gitleaks | A secret is found |
| Pull request | Static code analysis (SAST) | Semgrep, Bandit | A new high-severity finding |
| Pull request | Dependency scan (SCA) | pip-audit, Dependabot | Critical, or High with a fix available |
| Pull request | Infrastructure-as-code scan | `trivy config` on Terraform, Helm charts and Dockerfiles | A high-severity misconfiguration, such as a privileged container or a public bucket |
| Build | Image vulnerability scan | Trivy | Critical, or High with a fix available |
| Build | SBOM (list of everything in the image) | Trivy, CycloneDX format | Never blocks; stored next to the image |
| Build | Image signing | cosign | Signing fails |
| Deploy | Admission policies in the cluster | Kyverno, Pod Security Admission | The image is unsigned, not from `registry.example.com`, or the pod breaks the "restricted" profile |
| Runtime | Nightly rescan of running images | Trivy | Never blocks; opens tickets with deadlines |
| Runtime | Audit logs and alerts | Kubernetes audit log, cloud audit log | Never blocks; reviewed by the Security team |

## Rules
- Security stages can't be skipped or marked as "allowed to fail" on `main`.
- Images in prod must come from `registry.example.com`, be signed by the pipeline, and have passed the image scan. The cluster enforces this, so images built by hand are rejected.
- Exceptions, such as a CVE with no fix or a false positive, are made in code (`.trivyignore`, `# nosec`, `# nosemgrep`) with a reason, an expiry date and the Security team's approval in the PR.
- Fix deadlines: Critical within 7 days, High within 30 days, Medium within 90 days.

## Who owns what
- **Owning team:** fixes findings in its own code, images and Helm charts.
- **Platform team:** runs the pipeline, the scanners and the admission policies.
- **Security team:** sets the rules, approves exceptions, and reviews the nightly reports.
- **Security champion:** one engineer in each team who reviews suppressions and helps the team with findings.

## What to do when a gate fails
1. Open the failed job and read which tool and which rule failed.
2. Find the matching runbook:
   - Secret found: "Leaked secret response"
   - SAST: "Static code analysis (SAST) findings in the pipeline"
   - Dependency scan: "Vulnerable dependencies in application code"
   - Image scan: "Container image vulnerabilities"
   - Pod rejected at deploy: "Kubernetes pod security (Pod Security Admission)"
3. Fix it in your branch. If you think it's a false positive, ask your security champion.
4. In an emergency, when an incident fix is blocked by an old finding that has nothing to do with the fix, the incident commander can ask the Security team for a one-time exception. It is recorded in the incident channel.

## Escalate if
- A scanner or the admission controller is broken and blocks every team. Contact the Platform team.
- Teams disagree about whether a finding must block. The Security team decides.
