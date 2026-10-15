import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from openai import OpenAI
from pydantic import BaseModel

# Reads OPENROUTER_API_KEY and OPENROUTER_MODEL from the .env in the repo root
load_dotenv()

STATIC_DIR = Path(__file__).parent / "static"
MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free")

app = FastAPI(
    title="DevOps AI Chatbot",
    version="2.0.0",
)

# OpenRouter speaks the OpenAI API, so the OpenAI client works with a different base_url
client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
    timeout=60,
)


class ChatRequest(BaseModel):
    message: str


@app.get("/")
def root():
    return {"message": "DevOps AI Chatbot is running"}


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.post("/chat")
def chat(request: ChatRequest):
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "You are a helpful DevOps AI assistant."},
                {"role": "user", "content": request.message},
            ],
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    return {
        "user": request.message,
        "answer": response.choices[0].message.content,
        "model": response.model,
    }


@app.get("/ui", include_in_schema=False)
def ui():
    return FileResponse(STATIC_DIR / "index.html")
