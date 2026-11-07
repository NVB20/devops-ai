# Step 08 – CI/CD with GitHub Actions

The workflow is [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) (GitHub only runs workflows from that folder). It runs on every pull request, every push to `main`, and by hand from the Actions tab.

```
             ┌─ test (06-Deploy) ─────┐
pull request ┼─ test (07-n8n-Ollama) ─┼─► image: build 09-Monitoring/Dockerfile ─► push to GHCR (main only)
or push      ├─ test (09-Monitoring) ─┤
             └─ configs ──────────────┘
```

| Job | What it checks |
|---|---|
| `test` (one per step) | A real Postgres + pgvector as a service container, a real ingest of `knowledge-base/`, then `pytest tests`. So `test_retrieval.py` runs for real here (it's skipped on a machine without Postgres): every runbook must be the first search result for its question. The LLM is faked in the tests, so no OpenRouter key or quota is used. |
| `configs` | The compose files of steps 06, 07 and 09 (`docker compose config`), the Prometheus config and alert rules (`promtool check config`), and the step 10 Kubernetes manifests against the Kubernetes schema (`kubeconform -strict`). |
| `image` | Builds the latest step's image (`APP_STEP` in the workflow). Pull requests only build it. On `main` it's pushed to `ghcr.io/nvb20/devops-ai-app` as `latest` and `sha-<commit>`. Runs only when `test` and `configs` pass. |

**Secrets:** none to add. The push uses the built-in `GITHUB_TOKEN` (the job has `packages: write`). The tests use a dummy OpenRouter key, since they fake the LLM.

**The image:** GHCR packages start private. To pull it without logging in (kind, step 10), open the package on GitHub → Package settings → Change visibility → Public. Or log in: `docker login ghcr.io -u <user>` with a personal access token that has `read:packages`.

**Caches:** pip packages (per step's `requirements.txt`), the embedding model (`.fastembed`), and the Docker layers (`type=gha`), so a run after the first one is much faster.

**When a new step is added:** add its folder to the `test` matrix, its paths to `.dockerignore`, and point `APP_STEP` at it if it's the new image to deploy.
