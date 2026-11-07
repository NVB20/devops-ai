# DevOps AI – notes for Claude

A DevOps troubleshooting assistant built step by step for the DevOps Mentor–Mentee project. One folder per step; each step's app is a copy of the previous one plus that step's change. README.md documents every step and is the source of truth.

## Layout
- `NN-Name/app/` – FastAPI app (`main.py`), `ingest.py`, `static/index.html` (chat UI + live architecture view), `requirements.txt`
- `NN-Name/tests/` – pytest with a fake LLM and fake search; `test_retrieval.py` needs Postgres and is skipped without it
- `knowledge-base/` – the runbooks (markdown, chunked per `##` section)
- `docker-compose.yml` – step 06 stack (db, ingest, app). Later steps add to it with `-f NN-Name/compose.yml` overrides; relative paths in overrides resolve from the repo root
- `.github/workflows/ci.yml` – step 08 CI: tests per step on real pgvector, config checks, image to GHCR (`APP_STEP` = the deployed step)
- `10-Kubernetes/` – kind config + plain manifests for the step 09 image
- `12-Helm/` – chart `devops-ai/` (app, service, config, secrets, ingest Job, optional pgvector StatefulSet), `values-kind.yaml`, `values-floci.yaml`, and `floci/` (Terraform `helm_release` on Floci's EKS, reads step 11 infra state)
- `11-Terraform-Floci/` – `compose.yml` runs Floci (local AWS emulator, :4566); `infra/` (VPC, S3, ECR, RDS pgvector, EKS, IAM, Secrets Manager, kubeconfig) and `app/` (Kubernetes provider, reads infra state) are separate Terraform roots

## Current state (steps 07–12)
- LLM: `LLM_PROVIDER=openrouter|ollama` (step 07+). Ollama runs on the host; containers use `host.docker.internal:11434`
- n8n workflow `07-n8n-Ollama/n8n/devops-ai-chat.json`: Chat Trigger → POST `app:8000/chat` → `output` field. Imported on n8n start
- Metrics (step 09+): `/metrics`, names prefixed `devops_ai_`; labels only from fixed lists (route, outcome, kind, path template)
- K8s: app readiness = `/health`, liveness = TCP only (DB outage must not restart the app); containers run as uid 1000
- Floci: RDS image overridden to `pgvector/pgvector:pg17` (keep a pg17 tag); pods reach RDS at `localhost.floci.io:<proxy port>`; ECR uses path-style URIs; EKS tokens need the deployer IAM key (test/test refused)
- Terraform state, kubeconfig and tfvars are git-ignored (they hold the DB password and deployer key)
- Helm: ingest Job name = hash of image + database URL + ingest settings (reruns only when they change; not a hook, so it works under ArgoCD's revision-1 rendering); exactly one of postgres.enabled / database.url / database.existingSecret, enforced in `_helpers.tpl`
- Next per the project plan: ArgoCD (13), full platform (14)

## Conventions
- New step = new folder copied from the latest app step; add it to `.dockerignore`, the CI test matrix, README's status table and a README section
- Tests run from the step folder: `python -m pytest tests` (needs `OPENROUTER_API_KEY` set to anything)
- Keep comments short and explain why; README in plain, short sentences
- Update this file with any new feature or design change
