import json
import os
import time
from functools import cache
from pathlib import Path
from typing import TypedDict

import av
import psycopg
from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from fastembed import TextEmbedding
from faster_whisper import WhisperModel
from langgraph.graph import END, START, StateGraph
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
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")  # speech to text, runs locally on the CPU; multilingual (Hebrew too)
WHISPER_LIVE_MODEL = os.getenv("WHISPER_LIVE_MODEL", "base")  # the live preview while you talk: ~3x faster, a bit rougher

SYSTEM_PROMPT = """You are a DevOps assistant for our organization.
Answer ONLY using the runbook excerpts in CONTEXT. Never add commands that are not in them.
Be short: plain text, a few numbered steps with the exact commands. No tables, no headings.
Cite the runbook file for each step, like [disk-full.md].
If the context does not answer the question, say you couldn't find it in the runbooks. Do not guess."""

CLASSIFY_PROMPT = """Classify the user's question. Reply with exactly ONE word:
troubleshooting - something is broken, failing, slow or erroring and they want it fixed
knowledge - how something works, how we do something, a procedure or a best practice
other - not about DevOps, infrastructure, security or our systems

Examples:
"my pod keeps crashing" -> troubleshooting
"how do we deploy?" -> knowledge
"best pizza in town?" -> other"""

ROUTES = ("troubleshooting", "knowledge", "other")
OFF_TOPIC_ANSWER = "Sorry, I only help with DevOps questions about our systems and runbooks."

app = FastAPI(
    title="DevOps AI Chatbot",
    version="4.0.0",
)

# OpenRouter speaks the OpenAI API, so the OpenAI client works with a different base_url
client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
    timeout=60,
)

# Same model as ingest, so questions and chunks are comparable. Loaded once at startup.
embedder = TextEmbedding(EMBED_MODEL)


@cache
def whisper(name: str) -> WhisperModel:
    """Loaded on the first /transcribe, not at startup: the first run downloads it (~480 MB for small, ~145 MB for base)."""
    return WhisperModel(name, device="cpu", compute_type="int8")


class ChatRequest(BaseModel):
    message: str


def search(question: str, k: int = TOP_K) -> list[dict]:
    """Return the k runbook chunks closest in meaning to the question."""
    return nearest_chunks(next(embedder.embed([question])), k)


def nearest_chunks(vector, k: int = TOP_K) -> list[dict]:
    """The database half of search(): the k chunks whose embeddings are closest to vector."""
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


def answer_from_chunks(question: str, chunks: list[dict]) -> dict:
    """The step 03 answer: ask the LLM using only the retrieved chunks, return answer + cited sources."""
    sources = sorted({c["source"] for c in chunks})
    if not chunks:
        return {"answer": "I couldn't find anything about this in the runbooks.", "model": None, "sources": []}

    context = "\n\n".join(f"[{c['source']}]\n{c['text']}" for c in chunks)
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"CONTEXT:\n{context}\n\nQUESTION: {question}"},
        ],
    )
    answer = (response.choices[0].message.content or "").strip()
    # Show only the runbooks the answer actually cites; fall back to everything retrieved
    cited = [s for s in sources if s in answer]
    return {"answer": answer, "model": response.model, "sources": cited or sources}


def ms_since(start: float, end: float | None = None) -> int:
    return round(((end or time.perf_counter()) - start) * 1000)


# ── The graph ──
# The state is the "box" that travels through the graph. Each node reads it and returns the keys it changes.
class State(TypedDict, total=False):
    question: str
    route: str
    chunks: list[dict]
    timings: dict
    answer: str
    sources: list[str]
    model: str | None


def classify(state: State) -> dict:
    """One short LLM call: which kind of question is this?"""
    response = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": CLASSIFY_PROMPT},
            {"role": "user", "content": state["question"]},
        ],
    )
    word = (response.choices[0].message.content or "").strip().lower().strip(".'\"`*")
    return {"route": word if word in ROUTES else "knowledge"}


def off_topic(state: State) -> dict:
    return {"answer": OFF_TOPIC_ANSWER, "sources": [], "model": None}


def retrieve(state: State) -> dict:
    # Same as search(), but timed in two parts so the UI can show the embedding and the database separately
    started = time.perf_counter()
    vector = next(embedder.embed([state["question"]]))
    embedded = time.perf_counter()
    chunks = nearest_chunks(vector)
    return {"chunks": chunks, "timings": {"embed_ms": ms_since(started, embedded), "search_ms": ms_since(embedded)}}


def troubleshoot(state: State) -> dict:
    # Same answer code as knowledge for now; the next step turns this into a real troubleshooting agent
    return answer_from_chunks(state["question"], state["chunks"])


def knowledge(state: State) -> dict:
    return answer_from_chunks(state["question"], state["chunks"])


builder = StateGraph(State)
builder.add_node("classify", classify)
builder.add_node("off_topic", off_topic)
builder.add_node("retrieve", retrieve)
builder.add_node("troubleshoot", troubleshoot)
builder.add_node("knowledge", knowledge)

builder.add_edge(START, "classify")
# After classify: "other" stops early, everything else goes to retrieve
builder.add_conditional_edges(
    "classify",
    lambda state: "off_topic" if state["route"] == "other" else "retrieve",
    ["off_topic", "retrieve"],
)
# After retrieve: pick the answer node that matches the route
builder.add_conditional_edges(
    "retrieve",
    lambda state: state["route"],
    {"troubleshooting": "troubleshoot", "knowledge": "knowledge"},
)
builder.add_edge("off_topic", END)
builder.add_edge("troubleshoot", END)
builder.add_edge("knowledge", END)

graph = builder.compile()


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/ui")


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/search")
def search_endpoint(q: str):
    """See which chunks a question retrieves, without calling the LLM."""
    return search(q)


@app.get("/graph", include_in_schema=False)
def graph_diagram():
    """The graph as a Mermaid diagram; paste it into https://mermaid.live to see it."""
    return {"mermaid": graph.get_graph().draw_mermaid()}


@app.post("/chat")
def chat(request: ChatRequest):
    try:
        result = graph.invoke({"question": request.message})
    except psycopg.Error as e:
        raise HTTPException(status_code=503, detail=f"Knowledge base unavailable: {e}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    return {
        "user": request.message,
        "answer": result["answer"],
        "model": result["model"],
        "sources": result["sources"],
        "route": result["route"],
    }


def step_summary(node: str, result: dict) -> dict:
    """The part of a node's result the UI shows for that step (chunk text stays on the server)."""
    if node == "classify":
        return {"route": result["route"]}
    if node == "retrieve":
        chunks = [{"source": c["source"], "similarity": c["similarity"]} for c in result["chunks"]]
        return {**result["timings"], "chunks": chunks}
    return {"model": result.get("model")}


def sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


@app.post("/chat/stream")
def chat_stream(request: ChatRequest):
    """Like /chat, but sends a Server-Sent Event as each graph node starts and finishes, so the UI can draw the path."""

    def events():
        started = time.perf_counter()
        node_started = {}  # task id -> start time
        node = None  # the node running right now
        state = {}
        yield sse({"type": "start"})
        try:
            # "tasks" mode yields one dict when a node starts (has "input") and one when it ends (has "error")
            for task in graph.stream({"question": request.message}, stream_mode="tasks"):
                if "input" in task:
                    node = task["name"]
                    node_started[task["id"]] = time.perf_counter()
                    yield sse({"type": "running", "node": node})
                elif task["error"] is None:
                    state.update(task["result"])
                    ms = ms_since(node_started.pop(task["id"]))
                    yield sse({"type": "step", "node": task["name"], "ms": ms, **step_summary(task["name"], task["result"])})
                # a failed node: the stream raises its error right after this
        except psycopg.Error as e:
            # Only retrieve talks to Postgres, and by then the embedding is done: name the part that failed
            yield sse({"type": "error", "node": node, "part": "search", "detail": f"Knowledge base unavailable: {e}"})
            return
        except Exception as e:
            yield sse({"type": "error", "node": node, "detail": str(e)})
            return

        yield sse({
            "type": "done",
            "answer": state["answer"],
            "sources": state["sources"],
            "route": state["route"],
            "model": state["model"],
            "ms": ms_since(started),
        })

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.post("/transcribe")
def transcribe(audio: UploadFile, live: bool = Form(False), language: str | None = Form(None)):
    """Speech to text with Whisper on this server. The UI posts its recording (webm/ogg/mp4/wav) and gets the text back.

    live: the preview while still talking, done with the faster model.
    language: e.g. "he" or "en". Without it Whisper detects it, which costs about as much as the transcription itself,
    so the UI sends back the language of its first pass."""
    model = whisper(WHISPER_LIVE_MODEL if live else WHISPER_MODEL)
    try:
        # vad_filter drops the silent parts, so Whisper doesn't invent words for them
        segments, info = model.transcribe(
            audio.file, language=language, beam_size=1, vad_filter=True,
            without_timestamps=True, condition_on_previous_text=False,
        )
        text = " ".join(s.text.strip() for s in segments)
    except av.error.FFmpegError as e:
        raise HTTPException(status_code=400, detail=f"Could not read the audio: {e}")
    except ValueError as e:  # an unknown language code
        raise HTTPException(status_code=400, detail=str(e))
    return {"text": text, "language": info.language}


@app.get("/ui", include_in_schema=False)
def ui():
    return FileResponse(STATIC_DIR / "index.html")
