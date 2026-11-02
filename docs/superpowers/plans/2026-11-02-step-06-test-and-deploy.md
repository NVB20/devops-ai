# Step 06: Test and Deploy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove that known questions find the right runbook, make `/health` report when Postgres is down, and package the step 05 app in Docker so `docker compose up` starts the app and the database.

**Architecture:** `06-Deploy/` is a copy of `05-Agents/`. `/health` runs `SELECT count(*) FROM chunks` and returns 503 when that fails. A new `tests/test_retrieval.py` runs 30 known questions (one per runbook) through the real embedder and the real database, with no LLM, and checks that each question's runbook comes back first. It is skipped when Postgres isn't reachable. A `Dockerfile` builds the app image with the embedding model baked in. The root `docker-compose.yml` gains a one-shot `ingest` service and an `app` service that waits for it. The app's container healthcheck calls `/health`, so a database outage shows up in `docker compose ps`.

**Tech Stack:** FastAPI, psycopg 3, fastembed, pytest, Docker (Engine 29, Compose v5), `python:3.13-slim`, `pgvector/pgvector:pg17`.

## Global Constraints

- No new Python dependencies.
- `03-RAG/`, `04-LangGraph/` and `05-Agents/` stay as they are. `04-LangGraph/` and `05-Agents/` show as modified in `git status`, but only their line endings changed (`git diff --ignore-cr-at-eol` is empty). Don't stage them.
- Don't stage `Project AI - Knowledge Base.pdf` (untracked, not part of this step). Always `git add` explicit paths.
- The database, the `chunks` table and the chunking stay the same. In this step the app runs the same `ingest.py` inside Docker.
- Retrieval rule: a known question passes only if its runbook is the **first** result of `search()`. All 30 questions below were checked against the real database on 2026-11-02 (177 chunks): 30/30 rank 1.
- Ports: the database stays on `127.0.0.1:5435`. The app container listens on **`127.0.0.1:8081`**, so it doesn't clash with `uvicorn --reload` on 8000 when you work on a step locally (8080 is taken by another project's container on this machine).
- Inside Docker, Whisper runs on the CPU (`small` model, downloaded on the first `/transcribe`). The NVIDIA packages are installed on Windows only.
- App version: `6.0.0`.

## File map

| File | Change |
|---|---|
| `06-Deploy/` | copy of `05-Agents/app` and `05-Agents/tests`, without `venv/`, `__pycache__/` and `.pytest_cache/` |
| `06-Deploy/app/main.py` | `chunk_count()`, `/health` checks the database and returns 503 when it is down, version 6.0.0 |
| `06-Deploy/app/ingest.py` | `KB_DIR` can be overridden from the environment (the container keeps the runbooks at `/knowledge-base`) |
| `06-Deploy/app/requirements.txt` | Windows-only markers on the `nvidia-*` and `win32_setctime` lines |
| `06-Deploy/tests/test_health.py` | new: `/health` up and down, no Postgres needed |
| `06-Deploy/tests/test_retrieval.py` | new: 30 known questions → their runbook comes first, multi-runbook question, off-topic questions find nothing, real `/health` |
| `06-Deploy/Dockerfile` | new: app image, runs as a non-root user, embedding model downloaded at build time |
| `.dockerignore` | new, repo root (the build context): sends only `06-Deploy/app`, `06-Deploy/tests` and `knowledge-base` |
| `docker-compose.yml` | adds `ingest` (one-shot) and `app` (healthcheck on `/health`) services |
| `README.md` | step 06 row and section; steps 03–05 start only the database with `docker compose up -d db` |

---

### Task 1: Copy the step and set up its venv

**Files:** Create `06-Deploy/` (copy), modify `06-Deploy/app/main.py` (version)

- [ ] **Step 1: Copy** (Git Bash)

```bash
cd /c/Users/nivb4/OneDrive/Desktop/DevOps-Ai
mkdir 06-Deploy && cp -r 05-Agents/app 05-Agents/tests 06-Deploy/
rm -rf 06-Deploy/app/__pycache__ 06-Deploy/tests/__pycache__ 06-Deploy/.pytest_cache
```

- [ ] **Step 2: Bump the version** in `06-Deploy/app/main.py`:

```python
app = FastAPI(
    title="DevOps AI Chatbot",
    version="6.0.0",
)
```

- [ ] **Step 3: venv** (each step has its own, as the README says)

```powershell
cd 06-Deploy
python -m venv venv
venv\Scripts\python -m pip install -r app/requirements.txt
```

- [ ] **Step 4: Baseline.** Run `venv\Scripts\python -m pytest tests -q` from `06-Deploy`. Expected: `14 passed` (the copied step 05 tests).

- [ ] **Step 5: Commit**

```bash
git add 06-Deploy/app 06-Deploy/tests
git commit -m "Step 06: start from a copy of step 05"
```

---

### Task 2: `/health` reports when the database is down

**Files:** Modify `06-Deploy/app/main.py`, Create `06-Deploy/tests/test_health.py`

**Interfaces:**
- Produces: `main.chunk_count() -> int`, which raises `psycopg.Error` when Postgres is unreachable or the `chunks` table is missing. Task 3 uses it to decide whether to skip.
- Produces: `GET /health` → `200 {"status": "healthy", "database": "up", "chunks": <int>}` or `503 {"status": "unhealthy", "database": "down", "detail": "<psycopg error>"}`. Task 4's container healthcheck depends on the status code.

- [ ] **Step 1: Write the failing tests**: create `06-Deploy/tests/test_health.py`

```python
"""Checks that /health reports the database. The "down" test makes a real connection attempt to a host that cannot exist, so no Postgres is needed."""
from fastapi.testclient import TestClient

from app import main


def test_health_reports_the_database_is_up(monkeypatch):
    monkeypatch.setattr(main, "chunk_count", lambda: 177)

    with TestClient(main.app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "database": "up", "chunks": 177}


def test_health_reports_the_database_is_down(monkeypatch):
    # .invalid never resolves (RFC 6761): psycopg fails at once, as in Docker when the db container is gone
    monkeypatch.setattr(main, "DATABASE_URL", "postgresql://devops:devops@db.invalid/knowledge")

    with TestClient(main.app) as client:
        response = client.get("/health")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unhealthy" and body["database"] == "down"
    assert "db.invalid" in body["detail"]  # psycopg's message names the server it couldn't reach
```

- [ ] **Step 2: Run them to see them fail**

Run (from `06-Deploy`): `venv\Scripts\python -m pytest tests/test_health.py -v`
Expected: both FAIL. The first fails with `AttributeError: ... has no attribute 'chunk_count'`, the second with `assert 200 == 503`.

- [ ] **Step 3: Implement.** In `06-Deploy/app/main.py`, add `JSONResponse` to the responses import:

```python
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
```

Add `chunk_count()` right after `nearest_chunks()`:

```python
def chunk_count() -> int:
    """How many runbook chunks are loaded. Raises psycopg.Error when Postgres is down or ingest never ran."""
    # A short timeout: a health check that hangs is worse than one that says "down"
    with psycopg.connect(DATABASE_URL, connect_timeout=3) as conn:
        return conn.execute("SELECT count(*) FROM chunks").fetchone()[0]
```

Replace the `/health` endpoint:

```python
@app.get("/health")
def health():
    """Healthy only when the knowledge base answers. 503 otherwise, so Docker and load balancers see it."""
    try:
        chunks = chunk_count()
    except psycopg.Error as e:
        return JSONResponse(status_code=503, content={"status": "unhealthy", "database": "down", "detail": str(e)})
    return {"status": "healthy", "database": "up", "chunks": chunks}
```

- [ ] **Step 4: Run all the tests**

Run: `venv\Scripts\python -m pytest tests -q`
Expected: `16 passed`. (Not `127.0.0.1:1`: on Windows a closed local port runs into the 3 s `connect_timeout`, and the message then doesn't name the host.)

- [ ] **Step 5: Check it by hand against the real database** (Postgres running from the repo root's `docker compose up -d db`)

```powershell
venv\Scripts\uvicorn app.main:app --port 8000
# second terminal:
curl.exe -s -w " %{http_code}\n" http://127.0.0.1:8000/health
```

Expected: `{"status":"healthy","database":"up","chunks":177} 200`. Then run `docker stop devops-ai-db` from the repo root and repeat the curl. Expected: `{"status":"unhealthy","database":"down","detail":"connection timeout expired"} 503` (on Windows the stopped port times out instead of refusing). Run `docker start devops-ai-db` afterwards.

- [ ] **Step 6: Commit**

```bash
git add 06-Deploy/app/main.py 06-Deploy/tests/test_health.py
git commit -m "Step 06: /health checks the database and returns 503 when it is down"
```

---

### Task 3: Known questions find the right runbook

**Files:** Create `06-Deploy/tests/test_retrieval.py`

**Interfaces:**
- Consumes: `main.search(question) -> list[dict]` (each item has `source`, `text` and `similarity`; chunks below 0.3 are dropped). Also `main.chunk_count()` from Task 2 and `app.ingest.KB_DIR`.

These tests check what the app already does. There is nothing to implement, so the TDD "red" step is replaced by two other checks: the tests must pass against the real database, and they must be skipped, not failed, when the database is down.

- [ ] **Step 1: Write the tests**: create `06-Deploy/tests/test_retrieval.py`

```python
"""Known questions must find the right runbook. Uses the real embedding model and the real database, with no LLM.
Needs Postgres with the runbooks loaded (docker compose up -d); skipped when Postgres isn't reachable."""
import psycopg
import pytest
from fastapi.testclient import TestClient

from app import main
from app.ingest import KB_DIR

# (question, the runbook that must come back first). Worded the way an engineer asks, not like the runbook titles.
KNOWN = [
    ("the build pipeline fails on the test stage", "cicd-pipeline-failing.md"),
    ("I think an attacker got into one of our servers", "compromised-host-response.md"),
    ("trivy found critical CVEs in our docker image", "container-image-vulnerabilities.md"),
    ("how do I restore the database from last night's backup?", "database-backup-and-restore.md"),
    ("the app says too many connections to postgres", "database-connection-errors.md"),
    ("npm audit reports a vulnerable package", "dependency-vulnerabilities.md"),
    ("how do we roll back a bad release?", "deploy-and-rollback.md"),
    ("what security gates does our pipeline have?", "devsecops-pipeline-security-gates.md"),
    ("no space left on device", "disk-full.md"),
    ("pods can't resolve service names", "dns-resolution-failures.md"),
    ("my container exits right after it starts", "docker-container-restarting.md"),
    ("helm says another operation is in progress", "helm-upgrade-failed.md"),
    ("the server is slow and the CPU is at 100%", "high-cpu-memory.md"),
    ("who do I page for a sev1 outage?", "incident-escalation.md"),
    ("users get a 502 bad gateway", "ingress-502-504-errors.md"),
    ("my pod keeps crashing and restarting", "kubernetes-crashloopbackoff.md"),
    ("the pod can't pull its image", "kubernetes-imagepullbackoff.md"),
    ("traffic between two namespaces is blocked", "kubernetes-network-policies.md"),
    ("a node is NotReady", "kubernetes-node-notready.md"),
    ("pods are stuck pending", "kubernetes-pod-pending.md"),
    ("my pod is rejected because it runs as root", "kubernetes-pod-security.md"),
    ("kubectl says forbidden, I can't list pods", "kubernetes-rbac-access.md"),
    ("someone pushed an AWS key to github", "leaked-secret-response.md"),
    ("messages are piling up in the queue", "rabbitmq-queue-backlog.md"),
    ("redis OOM command not allowed", "redis-memory-and-connection-issues.md"),
    ("semgrep blocks my pull request", "sast-findings.md"),
    ("how do I rotate the database password?", "secret-rotation.md"),
    ("what services make up our platform?", "service-overview.md"),
    ("the browser says the certificate has expired", "ssl-certificate-expired.md"),
    ("terraform apply fails with error acquiring the state lock", "terraform-state-lock-and-drift.md"),
]


@pytest.fixture(scope="module", autouse=True)
def database():
    try:
        count = main.chunk_count()
    except psycopg.Error as e:
        pytest.skip(f"Postgres not reachable, start it with docker compose up -d: {e}")
    assert count, "the chunks table is empty: run python -m app.ingest"


@pytest.mark.parametrize("question, runbook", KNOWN)
def test_known_question_finds_its_runbook_first(question, runbook):
    found = [c["source"] for c in main.search(question)]
    assert found and found[0] == runbook, f"got {found}"


def test_every_runbook_has_a_known_question():
    # A new runbook needs a question here too
    assert {runbook for _, runbook in KNOWN} == {f.name for f in KB_DIR.glob("*.md")}


def test_question_about_two_problems_finds_both_runbooks():
    found = {c["source"] for c in main.search("pods are pending and a node is NotReady")}
    assert {"kubernetes-pod-pending.md", "kubernetes-node-notready.md"} <= found


@pytest.mark.parametrize("question", ["best pizza in town?", "what is the capital of France?"])
def test_off_topic_question_finds_nothing(question):
    assert main.search(question) == []


def test_health_with_the_real_database():
    with TestClient(main.app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["chunks"] > 0
```

- [ ] **Step 2: Run them against the real database** (Postgres running and ingested, which it already is from steps 03–05)

Run (from `06-Deploy`): `venv\Scripts\python -m pytest tests/test_retrieval.py -v`
Expected: `35 passed` (30 known questions, the runbook-coverage check, the two-problem question, 2 off-topic questions and the real `/health`).

If a known question fails, the message shows what came back, for example `got ['sast-findings.md', ...]`. Don't loosen the rule to "in the top 5". Reword the question so it asks what an engineer would ask about that runbook, then check it with `curl "http://127.0.0.1:8000/search?q=..."`.

- [ ] **Step 3: Check that it is skipped when the database is down**

```powershell
docker stop devops-ai-db          # from the repo root
venv\Scripts\python -m pytest tests -q -rs   # from 06-Deploy
docker start devops-ai-db
```

Expected: `16 passed, 35 skipped`, and the skip reason starts with `Postgres not reachable`. The fake-LLM tests and `test_health.py` don't need the database, so they still pass.

- [ ] **Step 4: Full suite with the database up**: `venv\Scripts\python -m pytest tests -q`. Expected: `51 passed`.

- [ ] **Step 5: Commit**

```bash
git add 06-Deploy/tests/test_retrieval.py
git commit -m "Step 06: test that 30 known questions find their runbook first"
```

---

### Task 4: Dockerfile, and `docker compose up` starts the app and the database

**Files:** Modify `06-Deploy/app/ingest.py`, `06-Deploy/app/requirements.txt` and `docker-compose.yml`. Create `06-Deploy/Dockerfile` and `.dockerignore`.

**Interfaces:**
- Consumes: `GET /health` status codes from Task 2 (the container healthcheck).
- Produces: image `devops-ai-app`, and compose services `db`, `ingest` and `app`. The app is at `http://127.0.0.1:8081`.

- [ ] **Step 1: Let the container say where the runbooks are.** In `06-Deploy/app/ingest.py`, replace the `KB_DIR` line:

```python
# The repo's knowledge-base/ folder; the Docker image keeps it at /knowledge-base and sets KB_DIR
KB_DIR = Path(os.getenv("KB_DIR") or Path(__file__).resolve().parents[2] / "knowledge-base")
```

Also fix the docstring's run line, which still says `03-RAG`: `Run from the 06-Deploy folder:  python -m app.ingest`.

- [ ] **Step 2: Install the GPU packages on Windows only.** In `06-Deploy/app/requirements.txt`, change these four lines (the container is Linux and runs Whisper on the CPU, and the CUDA wheels would add about 1.5 GB):

```
nvidia-cublas-cu12==12.9.2.10; sys_platform == "win32"
nvidia-cuda-nvrtc-cu12==12.9.86; sys_platform == "win32"
nvidia-cudnn-cu12==9.27.0.42; sys_platform == "win32"
win32_setctime==1.2.1; sys_platform == "win32"
```

`main.py` needs no change. Its DLL loop globs `site-packages/nvidia/*/bin`, which finds nothing on Linux, so `os.add_dll_directory` (Windows-only) is never called.

- [ ] **Step 3: Create `06-Deploy/Dockerfile`**

```dockerfile
# The step 06 chatbot. Built from the repo root (it needs knowledge-base/ too):
#   docker compose build      or      docker build -f 06-Deploy/Dockerfile .
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FASTEMBED_CACHE_PATH=/models \
    KB_DIR=/knowledge-base

WORKDIR /app

# Dependencies first: this layer is rebuilt only when requirements.txt changes
COPY 06-Deploy/app/requirements.txt app/requirements.txt
RUN pip install -r app/requirements.txt

# Not root. /models is the user's, so the embedding model can be downloaded into it.
RUN useradd --create-home chatbot && mkdir /models && chown chatbot /models
USER chatbot

# The embedding model (~90 MB) is downloaded now, once, instead of on every container start
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('sentence-transformers/all-MiniLM-L6-v2')"

COPY knowledge-base /knowledge-base
COPY 06-Deploy/app app
COPY 06-Deploy/tests tests

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 4: Create `.dockerignore` at the repo root.** The root is the build context, and without this file Docker would send every step's `venv/`, `.git` and `.env`.

```
# Send the build only what the image needs (the context is the repo root)
*
!06-Deploy/app
!06-Deploy/tests
!knowledge-base
**/__pycache__
**/*.pyc
```

- [ ] **Step 5: Add the `ingest` and `app` services to `docker-compose.yml`.** Replace the whole file:

```yaml
# The step 06 chatbot and its Postgres + pgvector knowledge base.
# Start all: docker compose up -d --build    Only the database (steps 03-05): docker compose up -d db
# Stop: docker compose down    Wipe data: docker compose down -v

# What the ingest and app services share: one image, and the database inside the compose network
x-chatbot: &chatbot
  build:
    context: .
    dockerfile: 06-Deploy/Dockerfile
  image: devops-ai-app
  environment:
    DATABASE_URL: postgresql://${POSTGRES_USER:-devops}:${POSTGRES_PASSWORD:-devops}@db:5432/${POSTGRES_DB:-knowledge}
    OPENROUTER_API_KEY: ${OPENROUTER_API_KEY}  # from the .env in the repo root
    OPENROUTER_MODEL: ${OPENROUTER_MODEL:-openrouter/free}

services:
  db:
    image: pgvector/pgvector:pg17
    container_name: devops-ai-db
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-devops}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-devops}
      POSTGRES_DB: ${POSTGRES_DB:-knowledge}
    ports:
      - "127.0.0.1:5435:5432" # 5432-5434 are taken on this machine
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./db/init.sql:/docker-entrypoint-initdb.d/init.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]
      interval: 5s
      timeout: 3s
      retries: 10
    restart: unless-stopped

  # Loads the runbooks into the chunks table, then exits. Safe to re-run: it empties the table first.
  ingest:
    <<: *chatbot
    command: ["python", "-m", "app.ingest"]
    depends_on:
      db:
        condition: service_healthy

  app:
    <<: *chatbot
    container_name: devops-ai-app
    ports:
      - "127.0.0.1:8081:8000" # not 8000, so uvicorn --reload on a step still works next to it
    depends_on:
      ingest:
        condition: service_completed_successfully
    # /health returns 503 when the database is down, and urlopen raises on it: the container shows as unhealthy
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5)"]
      interval: 10s
      timeout: 6s
      retries: 3
      start_period: 30s
    restart: unless-stopped

volumes:
  pgdata:
```

- [ ] **Step 6: Validate the file**

Run (repo root): `docker compose config --services`
Expected: `db`, `ingest` and `app`, in any order, with no warning. If it warns `The "OPENROUTER_API_KEY" variable is not set`, the `.env` file is missing from the repo root.

- [ ] **Step 7: Build and start**

```powershell
docker compose up -d --build
docker compose ps -a
```

Expected: `devops-ai-db` is `Up (healthy)`. The ingest container shows `Exited (0)`, and its log (`docker compose logs ingest`) ends with `Stored 177 chunks in the chunks table`. `devops-ai-app` is `Up (healthy)` within about 30 s. The first build downloads the dependencies, so it takes a few minutes. Later builds that change only the code take seconds.

- [ ] **Step 8: Check the running app**

```powershell
curl.exe -s http://127.0.0.1:8081/health
curl.exe -s "http://127.0.0.1:8081/search?q=no+space+left+on+device"
curl.exe -N -X POST http://127.0.0.1:8081/chat/stream -H "Content-Type: application/json" -d "{\"message\":\"disk is full\"}"
```

Expected: `{"status":"healthy","database":"up","chunks":177}`. The search's first result has `"source":"disk-full.md"`. The stream ends with a `done` event whose `sources` include `disk-full.md` (this uses 2–4 free-tier requests). Then open http://127.0.0.1:8081/ui and ask a question.

- [ ] **Step 9: Run the whole test suite inside the container, against the compose database**

```powershell
docker compose exec app python -m pytest tests -q -p no:cacheprovider
```

Expected: `51 passed`. `-p no:cacheprovider` stops pytest from trying to write `.pytest_cache` into `/app`, which belongs to root.

- [ ] **Step 10: Database down → unhealthy, back up → healthy**

```powershell
docker stop devops-ai-db
curl.exe -s -w " %{http_code}\n" http://127.0.0.1:8081/health
# wait ~30 s (3 failed checks, 10 s apart)
docker compose ps app
docker start devops-ai-db
# wait ~10 s
docker compose ps app
```

Expected: `{"status":"unhealthy","database":"down","detail":"... failed to resolve host 'db' ..."} 503`, or a `connection refused` detail. Then `devops-ai-app` shows `(unhealthy)`, and after the database starts again it shows `(healthy)`. The app container keeps running the whole time and needs no restart.

- [ ] **Step 11: Commit**

```bash
git add 06-Deploy/Dockerfile 06-Deploy/app/ingest.py 06-Deploy/app/requirements.txt .dockerignore docker-compose.yml
git commit -m "Step 06: Dockerfile, docker compose up starts the database, ingest and the app"
```

---

### Task 5: README

**Files:** Modify `README.md`

- [ ] **Step 1: Add the step row** to the table after step 05:

```markdown
| 06 | [06-Deploy](./06-Deploy) – tested retrieval, `/health` that checks the database, everything in Docker | ✅ |
```

- [ ] **Step 2: Steps 03–05 now start only the database.** In the "Knowledge base database" section, change the first command line to:

```powershell
docker compose up -d db   # only the database (steps 03-05; first run creates the DB and enables the vector extension)
```

Leave the other commands in that block as they are.

- [ ] **Step 3: Add a "Test and deploy (step 06)" section** after the step 05 section, before "Run a step (PowerShell)":

````markdown
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

The app container's healthcheck calls it, so `docker stop devops-ai-db` turns `devops-ai-app` unhealthy in about 30 s, and `docker start devops-ai-db` brings it back.

**Tests:**

```powershell
cd 06-Deploy
python -m pytest tests                                           # local venv
docker compose exec app python -m pytest tests -p no:cacheprovider   # inside the running container
```

- `test_stream.py`: the agent loop and `/chat/stream`, with a fake LLM and database (from step 05).
- `test_health.py`: `/health` up, and down (a real connection attempt to a host that can't exist).
- `test_retrieval.py`: 30 known questions, one per runbook, worded the way an engineer asks. Each must find its runbook as the **first** search result, through the real embedding model and database, with no LLM. It also checks that every runbook has a question, that "pods are pending and a node is NotReady" finds both runbooks, and that off-topic questions find nothing. Skipped when Postgres isn't reachable.
````

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "Step 06: README"
```

---

## Done when

- `cd 06-Deploy; venv\Scripts\python -m pytest tests -q` gives `51 passed` with the database up, and `16 passed, 35 skipped` with it stopped.
- `docker compose up -d --build` from a clean state (`docker compose down`) brings up `devops-ai-db` and `devops-ai-app` as healthy, with `ingest` `Exited (0)`.
- `curl http://127.0.0.1:8081/health` gives 200 with the chunk count, and 503 with `"database": "down"` after `docker stop devops-ai-db`.
- `docker compose exec app python -m pytest tests -q -p no:cacheprovider` gives `51 passed`.
- A question in http://127.0.0.1:8081/ui gets a cited answer.
