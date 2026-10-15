# DevOps AI

My work on the [DevOps Mentor–Mentee project](https://github.com/yehudasho/dinghy-mentor-mentee), one folder per step.

| Step | Folder | Status |
|------|--------|--------|
| 01 | [01-chatbot](./01-chatbot) – Python FastAPI chatbot | ✅ |
| 02 | 02-AI-AgentTools – LLM via OpenRouter | ⏳ |

## Run step 01 (Git Bash)

```bash
cd 01-chatbot
python -m venv venv
source venv/Scripts/activate
python -m pip install -r app/requirements.txt
uvicorn app.main:app --reload
```

| URL | What |
|-----|------|
| http://127.0.0.1:8000 | API status |
| http://127.0.0.1:8000/ui | Chat frontend |
| http://127.0.0.1:8000/docs | Swagger UI |
