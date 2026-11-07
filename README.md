# DevOps AI

My work on the [DevOps Mentor–Mentee project](https://github.com/yehudasho/dinghy-mentor-mentee), one folder per step.

| Step | Folder | Status |
|------|--------|--------|
| 01 | [01-chatbot](./01-chatbot) – Python FastAPI echo chatbot | ✅ |
| 02 | [02-AI-AgentTools](./02-AI-AgentTools) – AI answers via OpenRouter | ✅ |
| 03 | [03-RAG](./03-RAG) – answers from our runbooks (RAG with Postgres + pgvector), with sources | ✅ |
| 04 | [04-LangGraph](./04-LangGraph) – LangGraph routes each question (troubleshooting / knowledge / other) | ✅ |
| 05 | [05-Agents](./05-Agents) – a Troubleshooting Agent and a Knowledge Agent that search the runbooks themselves | ✅ |
| 06 | [06-Deploy](./06-Deploy) – tested retrieval, `/health` that checks the database, everything in Docker | ✅ |
| 07 | [07-n8n-Ollama](./07-n8n-Ollama) – a local LLM (Ollama) as an alternative to OpenRouter, and an n8n chat workflow | 🚧 first run pending |
| 08 | [08-CICD](./08-CICD) – GitHub Actions: tests on a real pgvector, config checks, image pushed to GHCR | 🚧 first run pending |
| 09 | [09-Monitoring](./09-Monitoring) – `/metrics`, Prometheus with alert rules, a Grafana dashboard | 🚧 first run pending |
| 10 | [10-Kubernetes](./10-Kubernetes) – Postgres, the ingest Job and the chatbot on a local kind cluster | 🚧 first run pending |
| 11 | [11-Terraform-Floci](./11-Terraform-Floci) – Terraform builds the AWS side (VPC, S3, ECR, RDS with pgvector, EKS) on Floci, a local AWS emulator, and deploys the chatbot there | 🚧 first run pending |

| 12 | [12-Helm](./12-Helm) – one Helm chart for the chatbot, with values for kind (Postgres in the cluster) and for Floci's EKS (RDS, ECR), installed by Terraform there | 🚧 first run pending |

Next, following the project plan: ArgoCD (13), the full platform (14).

## Setup (once)

Create a `.env` file in the repo root (it's git-ignored):

```
OPENROUTER_API_KEY=your_api_key_here
OPENROUTER_MODEL=openrouter/free
DATABASE_URL=postgresql://devops:devops@127.0.0.1:5435/knowledge
```

Get a key at https://openrouter.ai/workspaces/default/keys. `openrouter/free` picks a free model, so it costs nothing.

## Knowledge base database (Postgres + pgvector)

```powershell
docker compose up -d db   # only the database (steps 03-05; first run creates the DB and enables the vector extension)
docker compose ps         # should show devops-ai-db as healthy
docker exec -it devops-ai-db psql -U devops -d knowledge   # SQL shell
docker compose down       # stop (data is kept in the pgdata volume)
docker compose down -v    # stop and wipe all data
```

The database listens on `127.0.0.1:5435` (use the IP, not `localhost`: on Windows `localhost` tries IPv6 first and stalls), and only this machine can reach it.

### Load the knowledge base (step 03)

```powershell
cd 03-RAG
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r app/requirements.txt
python -m app.ingest
```

This splits each runbook in `knowledge-base/` into chunks, one per `##` section (long sections are split further). It embeds each chunk with `all-MiniLM-L6-v2` (384 dimensions, runs locally, free) and stores `(source, text, embedding)` in the `chunks` table. Re-running it replaces the table contents. The first run downloads the model (~90 MB).

Then start the chatbot with `uvicorn app.main:app --reload` (see below). For each question it:

1. embeds the question with the same model,
2. fetches the 5 closest chunks from Postgres (chunks below 0.3 similarity are dropped; if none are left, it says it couldn't find an answer, without calling the LLM),
3. sends those chunks and the question to OpenRouter, with instructions to answer only from them and cite the runbook file,
4. returns the answer plus the runbook files it cited (`sources`), which the chat UI shows under each reply.

### Route questions with LangGraph (step 04)

Step 04 uses the same database and chunks as step 03, so there's nothing new to ingest. Before answering, a LangGraph graph decides what kind of question it got:

```
question → [classify] ── other ──► "I only help with DevOps" → END
               │
               ▼
          [retrieve] ── troubleshooting ──► [troubleshoot] → END
                     └─ knowledge ────────► [knowledge]    → END
```

- `classify` makes one short LLM call that returns one word: `troubleshooting`, `knowledge` or `other`. Any other reply counts as `knowledge`.
- `retrieve` is the step 03 `search()`.
- `troubleshoot` and `knowledge` both use the step 03 answer code for now. They become real specialized agents in the next step.

`/chat` also returns `route`, which the chat UI shows under each reply. `GET /graph` returns the graph as a Mermaid diagram; paste it into https://mermaid.live to see it.

The step 04 UI (`/ui`, also where `/` redirects) has the chat on the left and a live architecture diagram on the right. The diagram follows your message through Chat UI → FastAPI → classify → embed → pgvector search → troubleshoot / knowledge → answer, and a step log under it shows the route, the retrieved chunks with their similarity, the model and the time for each step. Click an earlier reply to see its path again.

It's fed by `POST /chat/stream`, which runs the same graph but sends a [Server-Sent Event](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events) as each node starts and finishes (`start`, `running`, `step`, then `done` or `error`). Watch it raw with:

```bash
curl -N -X POST http://127.0.0.1:8000/chat/stream -H "Content-Type: application/json" -d '{"message":"disk is full"}'
```

Tests (fake LLM and database, no network needed):

```powershell
cd 04-LangGraph
python -m pip install pytest
python -m pytest tests
```

### Specialized agents (step 05)

Same database as step 03/04, nothing new to ingest. The two answer nodes become real agents, and the `retrieve` node is gone: each agent searches the runbooks itself.

```
question → [classify] ── other ──────────► "I only help with DevOps" → END
               ├─ troubleshooting ──► [Troubleshooting Agent] ⇄ search_runbooks → END
               └─ knowledge ────────► [Knowledge Agent]       ⇄ search_runbooks → END
```

- `search_runbooks(query)` is the step 03 `search()`, given to the LLM as a tool (OpenAI function calling through OpenRouter). The LLM only asks for a search; our code runs it and sends back the excerpts, each tagged with its runbook file.
- Each agent may search up to 3 times (`MAX_SEARCHES`), with its own wording each time, for example once per symptom. After the third search it must answer (`tool_choice="none"`).
- **Troubleshooting Agent**: always answers as `Likely cause` → `Check` → `Fix` → `Escalate if`. If the question is too vague ("something is broken"), it asks one clarifying question instead of searching or guessing.
- **Knowledge Agent**: answers with a short explanation, then `Steps:`, and can combine several runbooks.
- Both answer only from what they found and cite it like `[disk-full.md]`. `sources` lists only the runbooks the answer cites.

`/chat` also returns `searches` and `clarify`. `/chat/stream` adds the agent loop's events: `llm` (one per LLM call: search, answer or clarify), `tool` (one per search: query, chunks, ms), and `token` / `reasoning` (the reply as it is written).

The ▶ button next to the input plays an example question for real, through OpenRouter. **Fast** sends it like a typed message. **Guided** holds each step for a moment and captions it above the diagram (the route, what OpenRouter decided, what pgvector returned and its best match), so you can follow the RAG loop step by step.

Tests (fake LLM and database):

```powershell
cd 05-Agents
python -m pytest tests
```

Check the real answers (needs Postgres, the `.env` key, and about 25 requests from the free tier's 50 a day):

```powershell
python -m tests.live_check        # all 8 questions
python -m tests.live_check 7 8    # only "something is broken" and "pods are pending and a node is NotReady"
```

It prints each answer with its searches and sources, and flags a wrong route, a troubleshooting answer missing a part or out of order, a knowledge answer without `Steps:`, a missing citation, a vague question that didn't get one clarifying question, and the pods/node question not citing both `kubernetes-pod-pending.md` and `kubernetes-node-notready.md`.

### Test and deploy (step 06)

The step 05 app with tests on what it retrieves, a health check that knows about the database, and Docker.

**Run everything in Docker** (needs the `.env` from Setup, for the OpenRouter key):

```powershell
docker compose up -d --build   # database, then ingest (loads the runbooks, then exits), then the app
docker compose ps -a           # devops-ai-db and devops-ai-app healthy, ingest Exited (0)
```

The chat is at http://127.0.0.1:8081/ui (8081, so `uvicorn` on 8000 still works for the other steps). The image is built from `06-Deploy/Dockerfile`, with the repo root as the build context because it needs `knowledge-base/` too. `.dockerignore` sends it only the app, its tests and the runbooks. The embedding model is downloaded when the image is built. In Docker, Whisper runs on the CPU and downloads its models on the first voice message (~480 MB for `small`, plus `base` for the live preview).

**`/health`** runs `SELECT count(*) FROM chunks`:

| Database | Response |
|---|---|
| up | `200 {"status": "healthy", "database": "up", "chunks": 177}` |
| down, or the `chunks` table is missing | `503 {"status": "unhealthy", "database": "down", "detail": "..."}` |

The app container's healthcheck calls it, so `docker stop devops-ai-db` turns `devops-ai-app` unhealthy in about 40 s, and `docker start devops-ai-db` brings it back.

**Tests:**

```powershell
cd 06-Deploy
python -m pytest tests                                           # local venv
docker compose exec app python -m pytest tests -p no:cacheprovider   # inside the running container
```

- `test_stream.py`: the agent loop and `/chat/stream`, with a fake LLM and database (from step 05).
- `test_health.py`: `/health` up, and down (a real connection attempt to a host that can't exist).
- `test_ingest.py`: ingest exits with an error, before touching the database, when it finds no runbooks (so compose doesn't start the app with an empty knowledge base).
- `test_retrieval.py`: 30 known questions, one per runbook, worded the way an engineer asks. Each must find its runbook as the **first** search result, through the real embedding model and database, with no LLM. It also checks that every runbook has a question, that "pods are pending and a node is NotReady" finds both runbooks, and that off-topic questions find nothing. Skipped when Postgres isn't reachable.

### Local LLM and n8n (step 07)

The step 06 app, plus a switch for which LLM answers, and an n8n workflow in front of it.

**Ollama instead of OpenRouter.** Both speak the OpenAI API, so only the base URL, key and model change. Add to `.env`:

```
LLM_PROVIDER=ollama          # openrouter (default) or ollama
OLLAMA_MODEL=llama3.2        # any model you pulled that supports tools: ollama pull llama3.2
# OLLAMA_BASE_URL=http://127.0.0.1:11434/v1   # default when running uvicorn; compose uses host.docker.internal
```

Ollama runs on your machine, not in compose: the containers reach it at `host.docker.internal:11434`. If they can't, set the Windows environment variable `OLLAMA_HOST=0.0.0.0` and restart Ollama. A 3B model on the CPU is slower than OpenRouter (the LLM timeout is 180 s instead of 60 s) and follows the answer format less strictly. `/health` now also says which LLM is in use (without calling it), and the chat UI labels the LLM station with it.

**n8n.** Start step 07 (from the repo root):

```powershell
docker compose -f docker-compose.yml -f 07-n8n-Ollama/compose.yml up -d --build
```

`07-n8n-Ollama/compose.yml` only adds to the root file: the app and ingest are built from `07-n8n-Ollama/Dockerfile`, and there's an `n8n` service. On every start n8n imports `07-n8n-Ollama/n8n/devops-ai-chat.json` (same id, so it updates instead of duplicating):

```
When chat message received ──► Ask the DevOps AI API (POST http://app:8000/chat) ──► Answer with sources
```

Open http://127.0.0.1:5678, create the owner account (first time only), open **DevOps AI chat** and click **Open chat** to try it. To get its public chat page, activate the workflow; the Chat Trigger node shows the URL.

Tests: `test_provider.py` checks the switch (default OpenRouter, Ollama's URL and model, a typo fails at startup).

### CI/CD (step 08)

`.github/workflows/ci.yml` runs on every pull request and every push to `main`. Details in [08-CICD](./08-CICD).

### Monitoring (step 09)

The step 07 app with a `/metrics` endpoint, plus Prometheus and Grafana:

```powershell
docker compose -f docker-compose.yml -f 07-n8n-Ollama/compose.yml -f 09-Monitoring/compose.yml up -d --build
```

| URL | What |
|-----|------|
| http://127.0.0.1:8081/metrics | The raw metrics |
| http://127.0.0.1:9090/alerts | Prometheus: the alert rules and which are firing |
| http://127.0.0.1:3000 | Grafana (admin / admin, change with `GRAFANA_ADMIN_PASSWORD` in `.env`), opens on the **DevOps AI** dashboard |

What the app counts (all start with `devops_ai_`):

- `questions_total{endpoint, route, outcome}`: outcome is `answered` (cites a runbook), `no_answer`, `clarify`, `off_topic` or `error`. `question_duration_seconds` is how long the whole answer took.
- `llm_call_duration_seconds{provider, kind}` and `llm_errors_total`: `kind` is `classify` or `agent` (one turn of the agent loop).
- `searches_total{agent}`, `search_duration_seconds`, `search_top_similarity`: how good the best match of each search was (0 when nothing matched). Low values show what the runbooks don't cover.
- `kb_chunks`: the chunk count `/health` last saw, -1 when Postgres is down. The container healthcheck keeps it fresh.
- `http_requests_total{method, path, status}` and `http_request_duration_seconds`: `path` is the route (`/search`), never the URL, so questions don't create new series.

Alert rules (`09-Monitoring/prometheus/alerts.yml`): app down, knowledge base down or empty, over 20% of questions failing, p95 answer time over a minute, over half the DevOps questions finding no runbook. They show in Prometheus; nothing is sent anywhere yet (no Alertmanager).

Tests: `test_metrics.py` checks what an answered, off-topic, clarifying, unanswered and failed question each add, and that `/search?q=...` stays one series.

### Kubernetes (step 10)

The step 09 image on a local [kind](https://kind.sigs.k8s.io) cluster: Postgres as a StatefulSet with its own volume, the ingest as a Job, the chatbot as a Deployment. From the repo root:

```powershell
kind create cluster --config 10-Kubernetes/kind-config.yaml
docker build -f 09-Monitoring/Dockerfile -t devops-ai-app:09 .
kind load docker-image devops-ai-app:09 --name devops-ai

kubectl apply -f 10-Kubernetes/manifests/00-namespace.yaml
kubectl -n devops-ai create secret generic openrouter --from-literal=OPENROUTER_API_KEY=<your key>
kubectl apply -f 10-Kubernetes/manifests/
kubectl -n devops-ai get pods -w     # postgres-0 Running, ingest Completed, app 1/1 Ready
```

The chat is at http://127.0.0.1:8082/ui (kind publishes the app's NodePort 30082 there).

| File | What |
|---|---|
| `kind-config.yaml` | One node, NodePort 30082 published on 127.0.0.1:8082 |
| `00-namespace.yaml` | Everything lives in `devops-ai` |
| `10-postgres.yaml` | pgvector StatefulSet + 1 Gi volume, headless Service `db`, the init SQL, the local credentials |
| `20-config.yaml` | `LLM_PROVIDER` and the models. The OpenRouter key is the `openrouter` Secret above, never in Git |
| `30-ingest-job.yaml` | Loads the runbooks; retries while Postgres starts |
| `40-app.yaml` | The chatbot and its NodePort Service |

The app's **readiness** probe is `/health`: no traffic while Postgres is down or the runbooks aren't loaded. Its **liveness** probe only checks the port, so a database outage doesn't make Kubernetes restart a healthy app. Both containers run as a non-root user.

Useful checks:

```powershell
kubectl -n devops-ai logs job/ingest
kubectl -n devops-ai scale statefulset postgres --replicas=0   # app turns 0/1 (not ready), but isn't restarted
kubectl -n devops-ai scale statefulset postgres --replicas=1   # and back to 1/1
kind delete cluster --name devops-ai
```

To use Ollama instead, set `LLM_PROVIDER: ollama` in `20-config.yaml`, apply it, and `kubectl -n devops-ai rollout restart deployment app`. To pull the image from GHCR (step 08) instead of loading it, make the package public (or add an image pull secret) and set `image: ghcr.io/nvb20/devops-ai-app:latest`.

### Terraform on a local AWS (step 11)

The AWS part of the project plan without an AWS account: [Floci](https://github.com/floci-io/floci) emulates AWS on your machine (`localhost:4566`), and the normal Terraform AWS provider talks to it. RDS, EKS and ECR are real containers that Floci starts: a pgvector Postgres, a k3s cluster and a registry.

```
infra stage:  VPC + 2 subnets ─ S3 (runbooks) ─ ECR ─ RDS Postgres 17 + pgvector ─ EKS 1.33 + node group
              IAM roles, a deployer user, the DB credentials in Secrets Manager, a kubeconfig
app stage:    on the EKS cluster: ingest Job → RDS, the chatbot Deployment + Service, image from ECR
```

Two stages because the app stage's Kubernetes provider needs the cluster to exist before Terraform can plan against it. The app stage reads the infra stage's outputs from its state file.

Needs: Docker, Terraform 1.6+, kubectl, and AWS CLI v2 (only for kubectl's login: `aws eks get-token`). From the repo root:

```powershell
# 1. Floci (once). The first EKS cluster also pulls the k3s image.
docker compose -f 11-Terraform-Floci/compose.yml up -d

# 2. The AWS side: about 2-5 minutes, mostly the cluster starting
terraform -chdir=11-Terraform-Floci/infra init
terraform -chdir=11-Terraform-Floci/infra apply

# 3. The chatbot image, into ECR (the push_image output prints these two lines)
docker build -f 09-Monitoring/Dockerfile -t localhost:4566/000000000000/us-east-1/devops-ai-app:09 .
docker push localhost:4566/000000000000/us-east-1/devops-ai-app:09

# 4. The chatbot on EKS. It waits for the ingest Job and for the app to be ready.
$env:TF_VAR_openrouter_api_key = "<your key>"
terraform -chdir=11-Terraform-Floci/app init
terraform -chdir=11-Terraform-Floci/app apply

# 5. Open it (the cluster's ports aren't published, so through kubectl)
kubectl --kubeconfig 11-Terraform-Floci/infra/kubeconfig -n devops-ai port-forward svc/app 8083:8000
```

The chat is at http://127.0.0.1:8083/ui. `terraform output` in each stage shows the rest (ECR URL, RDS endpoint, cluster endpoint). Tear down with `terraform destroy` in `app`, then in `infra`, then `docker compose -f 11-Terraform-Floci/compose.yml down -v`.

How the Floci parts fit together (all set in `11-Terraform-Floci/compose.yml`):

- **pgvector on RDS.** Floci's RDS runs `postgres:16-alpine` by default, which has no pgvector. `FLOCI_SERVICES_RDS_DEFAULT_POSTGRES_IMAGE=pgvector/pgvector:pg17` swaps the image. The RDS master user is a superuser there, so the ingest's `CREATE EXTENSION vector` works, as on real RDS.
- **Pods reach RDS** at `localhost.floci.io:<port>`. Floci proxies each database on a port of 7001-7099 inside its own container, and Floci's DNS answers that name with its container's address inside the cluster. On real AWS, set `db_host_in_cluster = ""` to use the RDS address.
- **ECR URLs** use the path style (`localhost:4566/<account>/<region>/<repo>`), because Docker Desktop's containerd image store pushes over plain HTTP only to `localhost`. Floci points the cluster's containerd at the same registry, so pods pull the same URL.
- **EKS logins** need a real IAM key: Floci refuses its public `test/test` key for them (it would grant cluster-admin). The infra stage creates a `devops-ai-deployer` user with an access entry; the kubeconfig and the app stage sign in as it. The kubeconfig and the state files hold that key and the database password, so they're git-ignored.
- **No AWS CLI?** Use k3s's own admin kubeconfig instead: `docker cp floci-aws-eks-devops-ai:/etc/rancher/k3s/k3s.yaml k3s.yaml`, then replace `https://127.0.0.1:6443` in it with the `cluster_endpoint` output.

What's emulated, not real: security groups and routes are recorded but not enforced, IAM policies aren't enforced, and there's no cost or AWS limit. It shows the Terraform works and the pieces connect; it doesn't prove it on AWS. To use Ollama from the cluster, `-var llm_provider=ollama` (whether pods reach your host's Ollama through Floci's DNS isn't tested).

CI runs `terraform fmt -check` and `terraform validate` on both stages (no Floci needed).

### Helm (step 12)

Steps 10 and 11 describe the same app twice: plain YAML for kind, Terraform resources for Floci's EKS. Step 12 replaces both with one chart, `12-Helm/devops-ai`, and a values file per environment.

| File | What |
|---|---|
| `devops-ai/values.yaml` | The defaults: image, LLM, database, resources, probes |
| `values-kind.yaml` | Postgres in the cluster, the image loaded into kind, NodePort 30082 |
| `values-floci.yaml` | No Postgres (RDS), the image from Floci's ECR, ClusterIP |
| `floci/` | Terraform that installs the chart on Floci's EKS (`helm_release`), with the ECR repository and the RDS URL from step 11's infra stage |

The chart renders: the app Deployment and Service, a ConfigMap (LLM settings), a Secret for `DATABASE_URL` and one for the OpenRouter key, the ingest Job, and with `postgres.enabled` a pgvector StatefulSet with its volume.

**On kind** (the cluster and image from step 10; if step 10's manifests are still applied, `kubectl delete namespace devops-ai` first):

```powershell
helm upgrade --install devops-ai 12-Helm/devops-ai -n devops-ai --create-namespace `
  -f 12-Helm/values-kind.yaml --set-string llm.openrouterApiKey=<your key> `
  --wait --wait-for-jobs --timeout 10m
```

The chat is at http://127.0.0.1:8082/ui. `--wait --wait-for-jobs` returns only once the runbooks are loaded and the app is ready.

**On Floci's EKS** (after step 11's infra stage and image push; it replaces step 11's app stage, so `terraform destroy` that one first):

```powershell
$env:TF_VAR_openrouter_api_key = "<your key>"
terraform -chdir=12-Helm/floci init
terraform -chdir=12-Helm/floci apply
kubectl --kubeconfig 11-Terraform-Floci/infra/kubeconfig -n devops-ai port-forward svc/devops-ai 8083:8000
```

**Day 2** (kind shown; on Floci change `image_tag` and apply):

```powershell
helm upgrade devops-ai 12-Helm/devops-ai -n devops-ai -f 12-Helm/values-kind.yaml --reuse-values --set image.tag=10 --wait --wait-for-jobs
helm -n devops-ai history devops-ai      # every revision, with its chart and app version
helm -n devops-ai rollback devops-ai     # back to the previous revision
```

How it behaves:

- **The ingest Job** is named after a hash of what it depends on: the image (which holds `knowledge-base/`), the database URL and its settings. It runs again exactly when one of those changes, and is left alone otherwise. Changing a Job in place is refused by Kubernetes, so a new name is what makes a rerun possible. It's a plain resource, not a Helm hook: hooks run before the database Secret exists or after the app is ready, and the app can't be ready before the runbooks are loaded. This also works the same under ArgoCD (step 13).
- **Changing the model, key or database URL restarts the pods**, through checksum annotations on the ConfigMap and Secrets.
- **Wrong settings fail at render time**, not as crashing pods: no database or two of them, an unknown `llm.provider`, a key given both ways.
- **Secrets stay out of Git:** pass the key with `--set-string` (or `TF_VAR_openrouter_api_key`), or point `llm.existingSecret` / `database.existingSecret` at Secrets you created.

CI lints the chart, renders it with both values files, checks the result against the Kubernetes schema, and checks the behaviour above: Postgres only on kind, the ingest Job name stable unless the image changes, and the render-time errors.

## Run a step (PowerShell)

```powershell
cd 02-AI-AgentTools
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r app/requirements.txt
uvicorn app.main:app --reload
```

In Git Bash, activate with `source venv/Scripts/activate` instead.

| URL | What |
|-----|------|
| http://127.0.0.1:8000/ui | Chat frontend |
| http://127.0.0.1:8000/docs | Swagger UI |
| http://127.0.0.1:8000 | API status (step 04: redirects to the chat) |
| http://127.0.0.1:8000/health | Health check (step 02+) |
| http://127.0.0.1:8000/search?q=pod+crashing | Which runbook chunks a question finds, no LLM (step 03) |
