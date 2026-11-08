<div align="center">

# 🤖 DevOps AI

### An agentic RAG copilot for on-call engineers: ask in plain English, get runbook-grounded fixes with citations

[![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-async%20API-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-multi--agent-1C3C3C?logo=langchain&logoColor=white)](https://langchain-ai.github.io/langgraph/)
[![pgvector](https://img.shields.io/badge/Postgres-pgvector-4169E1?logo=postgresql&logoColor=white)](https://github.com/pgvector/pgvector)
[![OpenRouter](https://img.shields.io/badge/LLM-OpenRouter-6566F1)](https://openrouter.ai/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](https://docs.docker.com/compose/)
[![Tests](https://img.shields.io/badge/tests-pytest-0A9EDC?logo=pytest&logoColor=white)](https://docs.pytest.org/)
[![Cost](https://img.shields.io/badge/inference-%240-brightgreen)](https://openrouter.ai/)

*Built step by step for the [DevOps Mentor–Mentee project](https://github.com/yehudasho/dinghy-mentor-mentee): from echo bot to a multi-agent AI platform on Kubernetes with GitOps.*

</div>

---

## ✨ Highlights

| | |
|---|---|
| 🧠 **Agentic RAG** | Specialized LLM agents use tool calling to search the runbooks themselves, rewording the query up to 3 times |
| 🔀 **Intent routing** | A LangGraph state machine classifies every question as troubleshooting, knowledge or off-topic |
| 🔎 **Semantic search** | 384-dim vector embeddings (`all-MiniLM-L6-v2`) in Postgres + pgvector, with a similarity cutoff |
| 📚 **Grounded answers** | Answers only from the 30 runbooks in the knowledge base and cites them like `[disk-full.md]`. No hallucinated fixes |
| ⚡ **Real-time streaming** | Server-Sent Events stream every graph node, tool call and token live to the UI |
| 🛰️ **Live architecture view** | Watch each request flow through Chat UI → FastAPI → classify → embed → pgvector → agent |
| 🎙️ **Voice input** | Local speech-to-text with Whisper |
| 🐳 **One command deploy** | `docker compose up` runs database → ingest job → app, gated on health checks |
| 🩺 **Health-aware** | `/health` checks the database and returns `503` when it's down, so the container shows as unhealthy |
| ✅ **Retrieval evals** | 30 golden questions must find their runbook as the **top-1** result |
| 💸 **Zero-cost inference** | `openrouter/free` model routing plus a local embedding model: $0 to run |

---

## 🏗️ Architecture

```mermaid
flowchart LR
    U([👩‍💻 Engineer]) -->|question / voice| UI[Chat UI]
    UI -->|SSE stream| API[FastAPI]
    API --> C{classify<br/>LLM router}
    C -->|other| X[🚫 I only help with DevOps]
    C -->|troubleshooting| T[🔧 Troubleshooting Agent]
    C -->|knowledge| K[📖 Knowledge Agent]
    T <-->|search_runbooks| S[(Postgres<br/>+ pgvector)]
    K <-->|search_runbooks| S
    T --> A([Answer + sources])
    K --> A
    KB[[📁 30 runbooks]] -->|ingest: chunk + embed| S
    T -.-> OR[☁️ OpenRouter LLM]
    K -.-> OR
    C -.-> OR
```

---

## 🗺️ Roadmap

| Step | Module | What ships | Status |
|:---:|---|---|:---:|
| 01 | [01-chatbot](./01-chatbot) | Python FastAPI echo chatbot | ✅ |
| 02 | [02-AI-AgentTools](./02-AI-AgentTools) | LLM answers via OpenRouter | ✅ |
| 03 | [03-RAG](./03-RAG) | Retrieval-augmented generation over our runbooks (Postgres + pgvector), with sources | ✅ |
| 04 | [04-LangGraph](./04-LangGraph) | LangGraph intent router: troubleshooting / knowledge / other | ✅ |
| 05 | [05-Agents](./05-Agents) | Troubleshooting Agent and Knowledge Agent with tool calling | ✅ |
| 06 | [06-Deploy](./06-Deploy) | Retrieval tests, DB-aware `/health`, fully containerized | ✅ |
| 07 | [07-n8n-Ollama](./07-n8n-Ollama) | Local LLM (Ollama) as an alternative to OpenRouter, n8n chat workflow | ✅ |
| 08 | [08-CICD](./08-CICD) | GitHub Actions: tests on real pgvector, config checks, image to GHCR | ✅ |
| 09 | [09-Monitoring](./09-Monitoring) | `/metrics`, Prometheus alert rules, Grafana dashboard | ✅ |
| 10 | [10-Kubernetes](./10-Kubernetes) | Postgres, ingest Job and chatbot on a local kind cluster | 🚧 |
| 11 | [11-Terraform-Floci](./11-Terraform-Floci) | Terraform builds VPC, S3, ECR, RDS (pgvector) and EKS on Floci (local AWS) | ✅ |
| 12 | [12-Helm](./12-Helm) | One Helm chart with values for kind and Floci's EKS | ✅ |
| 13 | [13-ArgoCD](./13-ArgoCD) | GitOps: ArgoCD deploys from `main`, CI commits each image tag | ✅ |
| 14 | [14-Platform](./14-Platform) | Answer review against runbooks, alerts → n8n → chatbot → Discord, Postgres + n8n metrics | ✅ |

---

## 🧰 Tech Stack

| Layer | Tech |
|---|---|
| **API** | FastAPI, Uvicorn, Server-Sent Events |
| **Orchestration** | LangGraph |
| **LLM** | OpenRouter (OpenAI-compatible function calling) |
| **Embeddings** | `all-MiniLM-L6-v2` via fastembed (local, 384 dims) |
| **Vector store** | PostgreSQL 17 + pgvector |
| **Speech-to-text** | faster-whisper |
| **Local LLM / automation** | Ollama, n8n |
| **Infra** | Docker, Docker Compose, health checks, named volumes |
| **Kubernetes** | kind, Helm, ArgoCD (GitOps) |
| **Cloud (emulated)** | Terraform, Floci (VPC, S3, ECR, RDS, EKS) |
| **Observability** | Prometheus, Alertmanager, Grafana, postgres-exporter, Discord alerts |
| **CI/CD** | GitHub Actions, GHCR |
| **Quality** | pytest, retrieval evals, live LLM checks |

---

## 🚀 Quickstart

**1. Configure secrets.** Create a `.env` in the repo root (it's git-ignored):

```env
OPENROUTER_API_KEY=your_api_key_here
OPENROUTER_MODEL=openrouter/free
DATABASE_URL=postgresql://devops:devops@127.0.0.1:5435/knowledge
```

Get a key at https://openrouter.ai/workspaces/default/keys. `openrouter/free` picks a free model, so it costs nothing.

**2. Launch the whole stack.**

```powershell
docker compose up -d --build   # database, then ingest (loads the runbooks, then exits), then the app
docker compose ps -a           # devops-ai-db and devops-ai-app healthy, ingest Exited (0)
```

**3. Open** 👉 http://127.0.0.1:8081/ui

---

## 🗄️ Vector Database (Postgres + pgvector)

```powershell
docker compose up -d db   # only the database (steps 03-05; first run creates the DB and enables the vector extension)
docker compose ps         # should show devops-ai-db as healthy
docker exec -it devops-ai-db psql -U devops -d knowledge   # SQL shell
docker compose down       # stop (data is kept in the pgdata volume)
docker compose down -v    # stop and wipe all data
```

> [!NOTE]
> The database listens on `127.0.0.1:5435` and only this machine can reach it. Use the IP, not `localhost`: on Windows `localhost` tries IPv6 first and stalls.

---

## 📦 Step by Step

<details>
<summary><b>📥 Step 03: RAG pipeline (ingest + retrieve + generate)</b></summary>

### Ingest the knowledge base

```powershell
cd 03-RAG
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r app/requirements.txt
python -m app.ingest
```

This splits each runbook in `knowledge-base/` into chunks, one per `##` section (long sections are split further). It embeds each chunk with `all-MiniLM-L6-v2` (384 dimensions, runs locally, free) and stores `(source, text, embedding)` in the `chunks` table. Re-running it replaces the table contents. The first run downloads the model (~90 MB).

### Query flow

Start the chatbot with `uvicorn app.main:app --reload` (see Run a Step Locally below). For each question it:

1. embeds the question with the same model,
2. fetches the 5 closest chunks from Postgres (chunks below 0.3 similarity are dropped; if none are left, it says it couldn't find an answer, without calling the LLM),
3. sends those chunks and the question to OpenRouter, with instructions to answer only from them and cite the runbook file,
4. returns the answer plus the runbook files it cited (`sources`), which the chat UI shows under each reply.

</details>

<details>
<summary><b>🔀 Step 04: LangGraph intent routing + live architecture view</b></summary>

Same database and chunks as step 03, so there's nothing new to ingest. Before answering, a LangGraph graph decides what kind of question it got:

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

### 🛰️ Live observability UI

The step 04 UI (`/ui`, also where `/` redirects) has the chat on the left and a live architecture diagram on the right. The diagram follows your message through Chat UI → FastAPI → classify → embed → pgvector search → troubleshoot / knowledge → answer, and a step log under it shows the route, the retrieved chunks with their similarity, the model and the time for each step. Click an earlier reply to see its path again.

It's fed by `POST /chat/stream`, which runs the same graph but sends a [Server-Sent Event](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events) as each node starts and finishes (`start`, `running`, `step`, then `done` or `error`). Watch it raw with:

```bash
curl -N -X POST http://127.0.0.1:8000/chat/stream -H "Content-Type: application/json" -d '{"message":"disk is full"}'
```

### 🧪 Tests (fake LLM and database, no network needed)

```powershell
cd 04-LangGraph
python -m pip install pytest
python -m pytest tests
```

</details>

<details>
<summary><b>🧠 Step 05: Multi-agent tool calling</b></summary>

Same database as step 03/04, nothing new to ingest. The two answer nodes become real agents, and the `retrieve` node is gone: each agent searches the runbooks itself.

```
question → [classify] ── other ──────────► "I only help with DevOps" → END
               ├─ troubleshooting ──► [Troubleshooting Agent] ⇄ search_runbooks → END
               └─ knowledge ────────► [Knowledge Agent]       ⇄ search_runbooks → END
```

- `search_runbooks(query)` is the step 03 `search()`, given to the LLM as a tool (OpenAI function calling through OpenRouter). The LLM only asks for a search; our code runs it and sends back the excerpts, each tagged with its runbook file.
- Each agent may search up to 3 times (`MAX_SEARCHES`), with its own wording each time, for example once per symptom. After the third search it must answer (`tool_choice="none"`).
- 🔧 **Troubleshooting Agent**: always answers as `Likely cause` → `Check` → `Fix` → `Escalate if`. If the question is too vague ("something is broken"), it asks one clarifying question instead of searching or guessing.
- 📖 **Knowledge Agent**: answers with a short explanation, then `Steps:`, and can combine several runbooks.
- Both answer only from what they found and cite it like `[disk-full.md]`. `sources` lists only the runbooks the answer cites.

`/chat` also returns `searches` and `clarify`. `/chat/stream` adds the agent loop's events: `llm` (one per LLM call: search, answer or clarify), `tool` (one per search: query, chunks, ms), and `token` / `reasoning` (the reply as it is written).

### ▶️ Demo mode

The ▶ button next to the input plays an example question for real, through OpenRouter. **Fast** sends it like a typed message. **Guided** holds each step for a moment and captions it above the diagram (the route, what OpenRouter decided, what pgvector returned and its best match), so you can follow the RAG loop step by step.

### 🧪 Tests (fake LLM and database)

```powershell
cd 05-Agents
python -m pytest tests
```

### 🔬 Live LLM checks

Needs Postgres, the `.env` key, and about 25 requests from the free tier's 50 a day:

```powershell
python -m tests.live_check        # all 8 questions
python -m tests.live_check 7 8    # only "something is broken" and "pods are pending and a node is NotReady"
```

It prints each answer with its searches and sources, and flags a wrong route, a troubleshooting answer missing a part or out of order, a knowledge answer without `Steps:`, a missing citation, a vague question that didn't get one clarifying question, and the pods/node question not citing both `kubernetes-pod-pending.md` and `kubernetes-node-notready.md`.

</details>

<details open>
<summary><b>🐳 Step 06: Test, containerize, deploy</b></summary>

The step 05 app with tests on what it retrieves, a health check that knows about the database, and Docker.

### Run everything in Docker

Needs the `.env` from [Quickstart](#-quickstart), for the OpenRouter key:

```powershell
docker compose up -d --build
docker compose ps -a
```

The chat is at http://127.0.0.1:8081/ui (8081, so `uvicorn` on 8000 still works for the other steps). The image is built from `06-Deploy/Dockerfile`, with the repo root as the build context because it needs `knowledge-base/` too. `.dockerignore` sends it only the app, its tests and the runbooks. The embedding model is downloaded when the image is built. In Docker, Whisper runs on the CPU and downloads its models on the first voice message (~480 MB for `small`, plus `base` for the live preview).

### 🩺 Health checks

**`/health`** runs `SELECT count(*) FROM chunks`:

| Database | Response |
|---|---|
| 🟢 up | `200 {"status": "healthy", "database": "up", "chunks": 177}` |
| 🔴 down, or the `chunks` table is missing | `503 {"status": "unhealthy", "database": "down", "detail": "..."}` |

The app container's healthcheck calls it, so `docker stop devops-ai-db` turns `devops-ai-app` unhealthy in about 40 s, and `docker start devops-ai-db` brings it back.

### 🧪 Test suite

```powershell
cd 06-Deploy
python -m pytest tests                                               # local venv
docker compose exec app python -m pytest tests -p no:cacheprovider   # inside the running container
```

| Test | Covers |
|---|---|
| `test_stream.py` | The agent loop and `/chat/stream`, with a fake LLM and database (from step 05) |
| `test_health.py` | `/health` up, and down (a real connection attempt to a host that can't exist) |
| `test_ingest.py` | Ingest exits with an error, before touching the database, when it finds no runbooks (so compose doesn't start the app with an empty knowledge base) |
| `test_retrieval.py` | 30 known questions, one per runbook, worded the way an engineer asks. Each must find its runbook as the **first** search result, through the real embedding model and database, with no LLM. It also checks that every runbook has a question, that "pods are pending and a node is NotReady" finds both runbooks, and that off-topic questions find nothing. Skipped when Postgres isn't reachable |

</details>

<details>
<summary><b>🦙 Step 07: Local LLM (Ollama) + n8n</b></summary>

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

</details>

<details>
<summary><b>🔁 Step 08: CI/CD with GitHub Actions</b></summary>

`.github/workflows/ci.yml` runs on every pull request and every push to `main`. Details in [08-CICD](./08-CICD).

</details>

<details>
<summary><b>📈 Step 09: Monitoring (Prometheus + Grafana)</b></summary>

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

</details>

<details>
<summary><b>☸️ Step 10: Kubernetes on kind</b></summary>

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

</details>

<details>
<summary><b>🏗️ Step 11: Terraform on a local AWS (Floci)</b></summary>

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
- **Pods reach RDS** at the RDS endpoint address, as on real AWS. On Floci that's the Floci container's address on the `floci` network (e.g. `172.29.0.2:7001`), where it proxies each database on a port of 7001-7099; the EKS node is on that network too. `localhost.floci.io` doesn't work: pods resolve it to `127.0.0.1`, themselves. If Floci restarts with a new address, `terraform apply` in `infra/` updates the secret.
- **ECR URLs** use the path style (`localhost:4566/<account>/<region>/<repo>`), because Docker Desktop's containerd image store pushes over plain HTTP only to `localhost`. Floci points the cluster's containerd at the same registry, so pods pull the same URL.
- **EKS logins** need a real IAM key: Floci refuses its public `test/test` key for them (it would grant cluster-admin). The infra stage creates a `devops-ai-deployer` user with an access entry; the kubeconfig and the app stage sign in as it. The kubeconfig and the state files hold that key and the database password, so they're git-ignored.
- **No AWS CLI?** Use k3s's own admin kubeconfig instead: `docker cp floci-aws-eks-devops-ai:/etc/rancher/k3s/k3s.yaml k3s.yaml`, then replace `https://127.0.0.1:6443` in it with the `cluster_endpoint` output.

What's emulated, not real: security groups and routes are recorded but not enforced, IAM policies aren't enforced, and there's no cost or AWS limit. It shows the Terraform works and the pieces connect; it doesn't prove it on AWS. To use Ollama from the cluster, `-var llm_provider=ollama` (whether pods reach your host's Ollama through Floci's DNS isn't tested).

CI runs `terraform fmt -check` and `terraform validate` on both stages (no Floci needed).

</details>

<details>
<summary><b>⛵ Step 12: Helm chart</b></summary>

Steps 10 and 11 describe the same app twice: plain YAML for kind, Terraform resources for Floci's EKS. Step 12 replaces both with one chart, `12-Helm/devops-ai`, and a values file per environment.

| File | What |
|---|---|
| `devops-ai/values.yaml` | The defaults: image, LLM, database, resources, probes |
| `values-kind.yaml` | Postgres in the cluster, the image loaded into kind, NodePort 30082 |
| `values-floci.yaml` | No Postgres (RDS), the image from Floci's ECR, ClusterIP |
| `floci/` | Terraform that prepares Floci's EKS for ArgoCD (step 13): the namespace, the RDS URL and OpenRouter Secrets, a ServiceAccount login for ArgoCD, and the ArgoCD cluster secret on kind |

The chart renders: the app Deployment and Service, a ConfigMap (LLM settings), a Secret for `DATABASE_URL` and one for the OpenRouter key, the ingest Job, and with `postgres.enabled` a pgvector StatefulSet with its volume.

**On kind** (the cluster from step 10; if step 10's manifests are still applied, `kubectl delete namespace devops-ai` first). The chart deploys the step 14 image by default (`appVersion`):

```powershell
docker build -f 14-Platform/Dockerfile -t devops-ai-app:14 .
kind load docker-image devops-ai-app:14 --name devops-ai
helm upgrade --install devops-ai 12-Helm/devops-ai -n devops-ai --create-namespace `
  -f 12-Helm/values-kind.yaml --set-string llm.openrouterApiKey=<your key> `
  --wait --wait-for-jobs --timeout 10m
```

The chat is at http://127.0.0.1:8082/ui. `--wait --wait-for-jobs` returns only once the runbooks are loaded and the app is ready.

**On Floci's EKS** the chart is deployed by ArgoCD (step 13), like on kind. Terraform only prepares the cluster (after step 11's infra stage, with kind and ArgoCD running; it replaces step 11's app stage, so `terraform destroy` that one first):

```powershell
$env:TF_VAR_openrouter_api_key = "<your key>"
terraform -chdir=12-Helm/floci init
terraform -chdir=12-Helm/floci apply   # Secrets, ArgoCD's login, registers floci-eks in ArgoCD
kubectl --kubeconfig 11-Terraform-Floci/infra/kubeconfig -n devops-ai port-forward svc/devops-ai 8083:8000
```

ArgoCD reaches Floci's EKS at its address on the `floci` Docker network (`floci_eks_api`, default `https://172.29.0.5:6443`, which the API certificate accepts); Terraform joins the kind node to that network. The image comes from GHCR, like on kind.

**Day 2** (kind by hand, before step 13; with ArgoCD a merge does it on both clusters):

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

</details>

<details>
<summary><b>🐙 Step 13: GitOps with ArgoCD</b></summary>

GitOps on two clusters: ArgoCD runs in kind, watches `main`, and makes **kind and Floci's EKS** match it. Nobody runs `helm upgrade` any more; a merge does.

```
merge to main ─► CI: tests ─► image to GHCR (sha-xxxxxxx) ─► CI commits that tag to 13-ArgoCD/values-argocd.yaml
                                                                              │
ArgoCD (in kind, polls main every ~3 min) ◄───────────────────────────────────┘ ─► helm-renders the chart ─► applies it
        ├─► kind            (devops-ai,       in-cluster)
        └─► Floci's EKS     (devops-ai-floci, over the floci Docker network)
```

CI never talks to ArgoCD or the clusters: it only commits to Git, and ArgoCD pulls. That's why a GitHub runner can deploy to clusters on a laptop.

| File | What |
|---|---|
| `root.yaml` | The one Application applied by hand ("app of apps"): it deploys everything in `apps/` |
| `apps/devops-ai.yaml` | The step 12 chart from `main`, with `values-kind.yaml` and `values-argocd.yaml`, auto-sync, prune and self-heal |
| `apps/prometheus.yaml` | Prometheus in the cluster (community chart, small): scrapes the app pods through their `prometheus.io/scrape` annotation |
| `apps/devops-ai-floci.yaml` | The same chart on Floci's EKS (cluster `floci-eks`, registered by `12-Helm/floci`), with `values-floci.yaml`, `values-argocd.yaml` and `values-argocd-floci.yaml` |
| `values-argocd.yaml` | The GHCR image and its tag (CI rewrites the tag), and the OpenRouter key from a Secret. Shared by both apps, so one tag commit updates both clusters |
| `values-argocd-floci.yaml` | Floci only: the RDS URL from the Secret Terraform creates |

Once (the kind cluster from step 10):

```powershell
kubectl create namespace argocd
kubectl apply -n argocd --server-side -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
kubectl -n argocd rollout status deployment argocd-server

# The key stays out of Git: ArgoCD's Application points at this Secret
kubectl create namespace devops-ai
kubectl -n devops-ai create secret generic openrouter --from-literal=OPENROUTER_API_KEY=<your key>

kubectl apply -n argocd -f 13-ArgoCD/root.yaml
```

The image is pulled from `ghcr.io/nvb20/devops-ai-app`, and GHCR packages start private: on GitHub open the package → Package settings → Change visibility → Public. (Or keep it private: create a `docker-registry` Secret named `ghcr` in `devops-ai` and uncomment `imagePullSecrets` in `values-argocd.yaml`.)

The ArgoCD UI: `kubectl -n argocd port-forward svc/argocd-server 8443:443`, then https://127.0.0.1:8443, user `admin`, password from `kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}"` (base64). The chat is at http://127.0.0.1:8082/ui as in step 12; ArgoCD shows it as a link on the `devops-ai` app and its Service (the chart's `service.annotations`, set in `values-kind.yaml`). Prometheus: `kubectl -n monitoring port-forward svc/prometheus-server 9091:80`.

What GitOps gives here:

- **Deploy = merge.** CI's `gitops` job commits `Deploy sha-xxxxxxx with ArgoCD [skip ci]` to `main` after each image push; ArgoCD rolls it out. `git log 13-ArgoCD/values-argocd.yaml` is the deploy history.
- **Rollback = revert.** `git revert` that commit and ArgoCD goes back to the previous image.
- **Self-heal.** `kubectl -n devops-ai scale deployment devops-ai --replicas=0` is undone within seconds: Git says 1.
- **The ingest Job** reruns only when its hash changes (step 12), which is what makes it safe here: ArgoCD renders the chart as revision 1 every time.

CI checks the Applications against ArgoCD's schema and renders the chart the way ArgoCD will.

</details>

<details>
<summary><b>🧩 Step 14: The full platform</b></summary>

Everything together, plus three things the earlier steps left out.

**1. Answers are reviewed against the runbooks.** After the agent answers, a `review` node asks the LLM to list every command or fact the runbook excerpts don't support. If there are any, a `revise` node gives the agent one rewrite with those notes (no new searches), and the rewrite is reviewed again:

```
classify ─► troubleshoot / knowledge ─► review ─┬─ supported ────────────────────► answer (passed)
                                                └─ not ─► revise ─► review ─┬─ supported ─► answer (revised)
                                                                            └─ not ───────► answer (flagged + the claims)
```

`/chat` and the stream return `review: {status, issues}`: `passed`, `revised`, `flagged`, `unchecked` (the reviewer's reply wasn't readable: the answer isn't held back) or `skipped` (a clarifying question, or no runbook cited). The chat shows it under each answer, with the unsupported claims when flagged.

**2. Alerts reach Discord with the fix.** Prometheus → Alertmanager → n8n (`DevOps AI alerts to Discord` workflow) → `POST /chat` with the alert → Discord:

```
🚨 PostgresTooManyConnections (warning): Postgres is using over 80% of its connections
Likely cause: ... Check: ... Fix: ... [database-connection-errors.md]
```

If the chatbot can't answer (it may be what's down), the alert still goes out, saying so.

Before posting, the "Summarize with Ollama" step asks Ollama on the host (`OLLAMA_BASE_URL`, `OLLAMA_MODEL`, same as the app) to shorten the alert and the advice to 5 bullet points. This is the one place a workflow calls Ollama itself. If Ollama is down or slow (2 min timeout), the full message goes out.

**3. More monitoring.** `postgres-exporter`, n8n's own `/metrics`, and Alertmanager are scraped. New alerts: Postgres down or near its connection limit, n8n down, over 20% of answers flagged. The dashboard has new rows for the review and for Postgres and n8n.

Run it (add `DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...` to `.env` first: Discord channel → Edit Channel → Integrations → Webhooks → New Webhook → Copy URL):

```powershell
docker compose -f docker-compose.yml -f 07-n8n-Ollama/compose.yml -f 09-Monitoring/compose.yml -f 14-Platform/compose.yml up -d --build
```

| URL | What |
|-----|------|
| http://127.0.0.1:8081/ui | The chat (answers now show their review) |
| http://127.0.0.1:5678 | n8n: the chat and alert workflows |
| http://127.0.0.1:9090/alerts | Prometheus alerts |
| http://127.0.0.1:9093 | Alertmanager |
| http://127.0.0.1:3000 | Grafana |

Try the alert path without breaking anything, by sending Alertmanager a made-up alert:

```powershell
$alert = '[{"labels":{"alertname":"PodCrashLooping","severity":"warning"},"annotations":{"summary":"pod payments-api keeps restarting (CrashLoopBackOff)"}}]'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:9093/api/v2/alerts -ContentType application/json -Body $alert
```

About 10 seconds later (Alertmanager's `group_wait`) the chatbot's answer from `kubernetes-crashloopbackoff.md` is in Discord, and the run is in n8n under Executions. Without `DISCORD_WEBHOOK_URL`, the run stops at "Discord configured?".

**Runbook gaps.** Each question no runbook answers is saved in Postgres (`unanswered_questions`, created by ingest and never emptied). `GET /gaps` lists them, most asked first: those are the runbooks to write next. Grafana's "Runbook coverage" row shows the % unanswered over time (24h and 7 days), so you see it drop as runbooks are added. "Clarify" and off-topic questions don't count. Saving never blocks an answer: if Postgres refuses, it's only logged.

**Fallback channel.** Alertmanager also posts every alert straight to a second Discord channel (raw alert, no AI, and "resolved" when it's fixed), so alerts still arrive when n8n is down. Add `DISCORD_FALLBACK_WEBHOOK_URL` to `.env`. Alertmanager can't read env vars in its config, so its entrypoint writes the URL to a file the config reads (`webhook_url_file`).

**Daily health report.** `14-Platform/n8n/devops-ai-daily-report.json` runs every day at 09:00 (Asia/Jerusalem). It reads the app's `/health` and Prometheus' firing alerts and posts ✅ "all systems OK" or ❌ with what's wrong to Discord. If the message doesn't come one morning, n8n itself is down. It's imported and published on n8n start; "Run now" in the editor runs it at once.

**n8n Assistant (optional).** n8n's built-in Assistant asks for a model and a code sandbox.
- Model: "Self-hosted or OpenAI-compatible endpoint", base URL `http://host.docker.internal:11434/v1`, API key `ollama`, a model you pulled (e.g. `qwen2.5:14b`).
- Sandbox: the compose file runs n8n's sandbox (`sandbox-certs`, `sandbox-api`, `sandbox-runner-1`, version `N8N_SANDBOX_VERSION`, default 1.14.0). Choose "n8n Sandbox", Service URL `http://sandbox-api:8080`, API key = `SANDBOX_API_KEYS` from `.env`.
- Add these random values to `.env` first: `SANDBOX_API_KEYS`, `SANDBOX_RUNNER_REGISTRATION_TOKEN`, `SANDBOX_RUNNER_API_KEYS`. The runner is privileged (Docker-in-Docker); no sandbox port is published.
- Watch out for the browser filling your n8n login into these forms.

**Where it runs.** A badge in the chat header shows where the app runs: 🐳 docker, ☸ kubernetes or 💻 local. Hover it for the host, the OS and, on Kubernetes, the pod. The app finds out by itself. Kubernetes sets `KUBERNETES_SERVICE_HOST` in every pod, and Docker creates `/.dockerenv`. Anything else counts as local, which includes uvicorn in a terminal. `APP_RUNTIME` changes the label, and the chart sets it from `runtimeLabel` (`kind` or `floci-eks`). The chart also passes the pod name through the Downward API. `/health` returns it as `runtime`, and `/metrics` has `devops_ai_runtime_info{kind,label}`.

The step 14 image is also what CI publishes and ArgoCD deploys (the chart's `appVersion` is 14).

Tests: `test_health.py` (runtime detection), `test_review.py` (passes, one rewrite, flagged after the rewrite, nothing to review, an unreadable verdict, the stream events), and the step 09 tests updated for the review step.

</details>

---

## 🖥️ Run a Step Locally

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
| http://127.0.0.1:8000/ui | 💬 Chat frontend |
| http://127.0.0.1:8000/docs | 📘 Swagger UI |
| http://127.0.0.1:8000 | 📡 API status (step 04: redirects to the chat) |
| http://127.0.0.1:8000/health | 🩺 Health check (step 02+) |
| http://127.0.0.1:8000/search?q=pod+crashing | 🔎 Which runbook chunks a question finds, no LLM (step 03) |

---

<div align="center">

**Built with ☕, 🐳 and 🤖 · from echo bot to a GitOps AI platform in 14 steps**

</div>
