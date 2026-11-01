import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastembed import TextEmbedding
from openai import OpenAI
from pgvector.psycopg import register_vector
from pydantic import BaseModel

from app.ingest import DATABASE_URL, EMBED_MODEL

# Reads OPENROUTER_API_KEY, OPENROUTER_MODEL and DATABASE_URL from the .env in the repo root
load_dotenv()

STATIC_DIR = Path(__file__).parent / "static"
MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free")
TOP_K = 5  # how many runbook chunks to give the LLM
MIN_SIMILARITY = 0.3  # below this, a chunk is not about the question

SYSTEM_PROMPT = """You are a DevOps assistant for our organization.
Answer ONLY using the runbook excerpts in CONTEXT. Never add commands that are not in them.
Be short: plain text, a few numbered steps with the exact commands. No tables, no headings.
Cite the runbook file for each step, like [disk-full.md].
If the context does not answer the question, say you couldn't find it in the runbooks. Do not guess."""

app = FastAPI(
    title="DevOps AI Chatbot",
    version="3.0.0",
)

# OpenRouter speaks the OpenAI API, so the OpenAI client works with a different base_url
client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
    timeout=60,
)

# Same model as ingest, so questions and chunks are comparable. Loaded once at startup.
embedder = TextEmbedding(EMBED_MODEL)


class ChatRequest(BaseModel):
    message: str


def search(question: str, k: int = TOP_K) -> list[dict]:
    """Return the k runbook chunks closest in meaning to the question."""
    vector = next(embedder.embed([question]))
    with psycopg.connect(DATABASE_URL) as conn:
        register_vector(conn)
        rows = conn.execute(
            """SELECT source, text, 1 - (embedding <=> %s) AS similarity
               FROM chunks ORDER BY embedding <=> %s LIMIT %s""",
            (vector, vector, k),
        ).fetchall()
    return [
        {"source": source, "text": text, "similarity": round(float(sim), 3)}
        for source, text, sim in rows
        if sim >= MIN_SIMILARITY
    ]


@app.get("/")
def root():
    return {"message": "DevOps AI Chatbot is running"}


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/search")
def search_endpoint(q: str):
    """See which chunks a question retrieves, without calling the LLM."""
    return search(q)


@app.post("/chat")
def chat(request: ChatRequest):
    try:
        chunks = search(request.message)
    except psycopg.Error as e:
        raise HTTPException(status_code=503, detail=f"Knowledge base unavailable: {e}")

    sources = sorted({c["source"] for c in chunks})
    if not chunks:
        return {
            "user": request.message,
            "answer": "I couldn't find anything about this in the runbooks.",
            "model": None,
            "sources": [],
        }

    context = "\n\n".join(f"[{c['source']}]\n{c['text']}" for c in chunks)
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"CONTEXT:\n{context}\n\nQUESTION: {request.message}"},
            ],
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    answer = response.choices[0].message.content
    # Show only the runbooks the answer actually cites; fall back to everything retrieved
    cited = [s for s in sources if s in answer]
    return {
        "user": request.message,
        "answer": answer,
        "model": response.model,
        "sources": cited or sources,
    }


@app.get("/ui", include_in_schema=False)
def ui():
    return FileResponse(STATIC_DIR / "index.html")
