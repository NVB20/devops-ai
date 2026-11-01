# DevOps AI

My work on the [DevOps Mentor–Mentee project](https://github.com/yehudasho/dinghy-mentor-mentee), one folder per step.

| Step | Folder | Status |
|------|--------|--------|
| 01 | [01-chatbot](./01-chatbot) – Python FastAPI echo chatbot | ✅ |
| 02 | [02-AI-AgentTools](./02-AI-AgentTools) – AI answers via OpenRouter | ✅ |
| 03 | [03-RAG](./03-RAG) – answers from our runbooks (RAG with Postgres + pgvector), with sources | ✅ |

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
docker compose up -d      # start (first run creates the DB and enables the vector extension)
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
| http://127.0.0.1:8000 | API status |
| http://127.0.0.1:8000/health | Health check (step 02+) |
| http://127.0.0.1:8000/search?q=pod+crashing | Which runbook chunks a question finds, no LLM (step 03) |
