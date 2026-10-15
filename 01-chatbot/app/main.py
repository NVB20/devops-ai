from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(
    title="DevOps AI Chatbot",
    version="1.0.0",
)


class ChatRequest(BaseModel):
    message: str


@app.get("/")
def root():
    return {"message": "DevOps AI Chatbot is running"}


@app.post("/chat")
def chat(request: ChatRequest):
    return {
        "user": request.message,
        "answer": f"You said: {request.message}",
    }


@app.get("/ui", include_in_schema=False)
def ui():
    return FileResponse(STATIC_DIR / "index.html")
