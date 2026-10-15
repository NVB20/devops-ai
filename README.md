# DevOps AI

My work on the [DevOps Mentor–Mentee project](https://github.com/yehudasho/dinghy-mentor-mentee), one folder per step.

| Step | Folder | Status |
|------|--------|--------|
| 01 | [01-chatbot](./01-chatbot) – Python FastAPI echo chatbot | ✅ |
| 02 | [02-AI-AgentTools](./02-AI-AgentTools) – AI answers via OpenRouter | ✅ |
| 03 | 03-WebAPI-interface – API + Python tests | ⏳ |

## Setup (once)

Create a `.env` file in the repo root (it's git-ignored):

```
OPENROUTER_API_KEY=your_api_key_here
OPENROUTER_MODEL=openrouter/free
```

Get a key at https://openrouter.ai/workspaces/default/keys. `openrouter/free` picks a free model, so it costs nothing.

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
| http://127.0.0.1:8000/health | Health check (step 02) |
