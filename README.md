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

The chat is at http://127.0.0.1:8081/ui (8081, so `uvicorn` on 8000 still works for the other steps). The image is built from `06-Deploy/Dockerfile`, with the repo root as the build context because it needs `knowledge-base/` too. `.dockerignore` sends it only the app, its tests and the runbooks. The embedding model is downloaded when the image is built. In Docker, Whisper runs on the CPU and downloads its model (~480 MB) on the first voice message.

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
- `test_retrieval.py`: 30 known questions, one per runbook, worded the way an engineer asks. Each must find its runbook as the **first** search result, through the real embedding model and database, with no LLM. It also checks that every runbook has a question, that "pods are pending and a node is NotReady" finds both runbooks, and that off-topic questions find nothing. Skipped when Postgres isn't reachable.

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
