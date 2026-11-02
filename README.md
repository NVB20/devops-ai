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

*Built step by step for the [DevOps Mentor–Mentee project](https://github.com/yehudasho/dinghy-mentor-mentee): from echo bot to containerized multi-agent AI.*

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
| **Infra** | Docker, Docker Compose, health checks, named volumes |
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

**Built with ☕, 🐳 and 🤖 · from echo bot to agentic AI in 6 steps**

</div>
