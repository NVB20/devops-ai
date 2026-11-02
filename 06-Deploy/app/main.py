import json
import os
import re
import sysconfig
import time
from functools import cache
from glob import glob
from pathlib import Path
from typing import TypedDict

import av
import ctranslate2
import psycopg
from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastembed import TextEmbedding
from faster_whisper import WhisperModel
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from openai import OpenAI, OpenAIError
from pgvector.psycopg import register_vector
from pydantic import BaseModel

from app.ingest import DATABASE_URL, EMBED_MODEL

# Reads OPENROUTER_API_KEY, OPENROUTER_MODEL and DATABASE_URL from the .env in the repo root
load_dotenv()

STATIC_DIR = Path(__file__).parent / "static"
MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free")
TOP_K = 5  # how many runbook chunks to give the LLM
MIN_SIMILARITY = 0.3  # below this, a chunk is not about the question

# Speech to text runs locally, on the NVIDIA GPU when there is one (~0.3 s per pass), else on the CPU.
# On Windows the CUDA libraries come from the nvidia-* pip packages: tell Python where their DLLs are.
for dll_dir in glob(os.path.join(sysconfig.get_paths()["purelib"], "nvidia", "*", "bin")):
    os.add_dll_directory(dll_dir)
    os.environ["PATH"] = dll_dir + os.pathsep + os.environ["PATH"]
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE") or ("cuda" if ctranslate2.get_cuda_device_count() else "cpu")
GPU = WHISPER_DEVICE == "cuda"
# All multilingual (Hebrew too). The GPU runs the big model for everything; the CPU needs smaller ones to keep up.
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "large-v3-turbo" if GPU else "small")
WHISPER_LIVE_MODEL = os.getenv("WHISPER_LIVE_MODEL", WHISPER_MODEL if GPU else "base")  # the preview while you talk

MAX_SEARCHES = 3  # each agent may search the runbooks this many times, with its own wording

# The one tool both agents get. The LLM only asks for it; our code runs the search and sends back the result.
SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "search_runbooks",
        "description": "Search our DevOps runbooks by meaning. Returns the closest runbook excerpts, each tagged with its file name. "
                       "Use a short, specific query. Search again with different words if the results don't cover the question.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "What to look for, e.g. 'node NotReady'"}},
            "required": ["query"],
        },
    },
}

RULES = f"""Find the answer with the search_runbooks tool. You may search up to {MAX_SEARCHES} times: reword the query when the
results miss, and search separately for each distinct problem in the question.
Answer ONLY from the runbook excerpts the tool returned. Never add commands that are not in them.
Cite the runbook file after each step, like [disk-full.md].
Unless you are asking a clarifying question, always search at least once before you answer: you know nothing about
our runbooks until you have searched them.
Only after searching, if the runbooks don't cover it, say you couldn't find it in the runbooks. Do not guess.
Plain text: no tables, no headings, no bold."""

TROUBLESHOOT_PROMPT = f"""You are our on-call DevOps troubleshooting agent.
FIRST, before anything else, decide: does the question name WHAT is broken (a pod, a node, a disk, a certificate,
a pipeline, a database...)?
- No, like "something is broken" or "it doesn't work": do NOT search, searching can't tell you what they mean.
  Reply with ONE short clarifying question and nothing else, starting with "CLARIFY:".
- Yes, like "my pod keeps crashing": never ask for names or details. Search the runbooks and answer,
  keeping their placeholders, like <pod> and <namespace>.
Answer in exactly this shape:
Likely cause: one or two sentences
Check: the commands that confirm it
Fix: numbered steps with the exact commands
Escalate if: when to page someone, and who
{RULES}"""

KNOWLEDGE_PROMPT = f"""You are our DevOps knowledge agent: you explain how things work and how we do things.
Answer with a short explanation (two or three sentences), then "Steps:" and numbered steps with the exact commands.
When the question touches several runbooks, combine them into one answer.
{RULES}"""

CLARIFY = "CLARIFY:"

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
    version="6.0.0",
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
    """Loaded on the first /transcribe, not at startup: the first run downloads it (~1.6 GB for large-v3-turbo, ~480 MB for small)."""
    return WhisperModel(name, device=WHISPER_DEVICE, compute_type="float16" if GPU else "int8")


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


def chunk_count() -> int:
    """How many runbook chunks are loaded. Raises psycopg.Error when Postgres is down or ingest never ran."""
    # A short timeout: a health check that hangs is worse than one that says "down"
    with psycopg.connect(DATABASE_URL, connect_timeout=3) as conn:
        return conn.execute("SELECT count(*) FROM chunks").fetchone()[0]


def search_runbooks(query: str) -> list[dict]:
    """The agents' tool: the step 03 search() under the name the LLM sees."""
    return search(query)


def tool_result(chunks: list[dict]) -> str:
    """What the LLM gets back from a search: the excerpts, each tagged with its runbook file."""
    if not chunks:
        return "No runbook excerpt matched. Try different words."
    return "\n\n".join(f"[{c['source']}]\n{c['text']}" for c in chunks)


def tool_query(arguments: str, question: str) -> str:
    """The query out of a tool call's JSON arguments. Small models sometimes send broken JSON: search the question then."""
    try:
        query = json.loads(arguments or "{}").get("query")
    except (json.JSONDecodeError, AttributeError):
        query = None
    return query if isinstance(query, str) and query.strip() else question


def is_clarifying(answer: str) -> bool:
    """A clarifying question: marked with CLARIFY:, or (models forget the mark) a question that cites no runbook."""
    if answer.startswith(CLARIFY):
        return True
    return answer.endswith("?") and not re.search(r"\[[\w.-]+\.md\]", answer)


def ms_since(start: float, end: float | None = None) -> int:
    return round(((end or time.perf_counter()) - start) * 1000)


def llm_turn(messages: list[dict], final: bool, on_text) -> dict:
    """One streamed LLM call. on_text(kind, text) gets each piece as it arrives: "token" for the reply,
    "reasoning" for the model's thinking (only some models send it). final: no more searches allowed."""
    stream = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        tools=[SEARCH_TOOL],
        tool_choice="none" if final else "auto",
        stream=True,
        extra_body={"include_reasoning": True},  # OpenRouter: send the thinking of models that have it
    )
    text, calls, model = "", {}, None
    for chunk in stream:
        model = chunk.model or model
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        if reasoning := getattr(delta, "reasoning", None):  # an OpenRouter field, not in the OpenAI types
            on_text("reasoning", reasoning)
        if delta.content:
            text += delta.content
            on_text("token", delta.content)
        # A tool call arrives in pieces too: the id and name first, then its JSON arguments a few characters at a time
        for piece in delta.tool_calls or []:
            call = calls.setdefault(piece.index or 0, {"id": "", "name": "", "arguments": ""})
            call["id"] = piece.id or call["id"]
            if piece.function:
                call["name"] += piece.function.name or ""
                call["arguments"] += piece.function.arguments or ""
    return {"text": text, "calls": list(calls.values()), "model": model}


def run_agent(agent: str, prompt: str, question: str) -> dict:
    """The agent loop: ask the LLM, run the searches it asks for, hand back the results, ask again,
    until it answers or has used its MAX_SEARCHES. Each step is also sent to the UI as a custom stream event."""
    write = get_stream_writer()
    messages = [{"role": "system", "content": prompt}, {"role": "user", "content": question}]
    seen = set()  # every runbook a search returned
    searches, model = [], None  # searches: {"query", "chunks", "ms"} for each search run

    for turn in range(1, MAX_SEARCHES + 2):
        final = len(searches) >= MAX_SEARCHES
        started = time.perf_counter()
        reply = llm_turn(messages, final, lambda kind, text: write({"type": kind, "agent": agent, "turn": turn, "text": text}))
        model = reply["model"] or model
        calls = [] if final else reply["calls"]
        queries = [tool_query(c["arguments"], question) for c in calls]
        if not calls:
            answer = reply["text"].strip() or "I couldn't find anything about this in the runbooks."
            clarify = is_clarifying(answer)
            write({"type": "llm", "agent": agent, "turn": turn, "ms": ms_since(started), "model": model,
                   "action": "clarify" if clarify else "answer", "forced": final})
            break
        write({"type": "llm", "agent": agent, "turn": turn, "ms": ms_since(started), "model": model,
               "action": "search", "queries": queries})

        messages.append({
            "role": "assistant", "content": reply["text"] or None,
            "tool_calls": [{"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": c["arguments"]}}
                           for c in calls],
        })
        for call, query in zip(calls, queries):
            # Every tool call needs a reply, even the ones past the limit
            if len(searches) >= MAX_SEARCHES:
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": "Search limit reached. Answer now."})
                continue
            started = time.perf_counter()
            chunks = search_runbooks(query)
            seen.update(c["source"] for c in chunks)
            searches.append({"query": query, "ms": ms_since(started),
                             "chunks": [{"source": c["source"], "similarity": c["similarity"]} for c in chunks]})
            write({"type": "tool", "agent": agent, "turn": turn, **searches[-1]})
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": tool_result(chunks)})

    if clarify:
        return {"answer": answer.removeprefix(CLARIFY).strip(), "sources": [], "model": model,
                "searches": searches, "clarify": True}
    # Only the runbooks the answer cites, so "couldn't find it" doesn't list the runbooks it rejected
    cited = [s for s in sorted(seen) if s in answer]
    return {"answer": answer, "sources": cited, "model": model, "searches": searches, "clarify": False}


# ── The graph ──
# The state is the "box" that travels through the graph. Each node reads it and returns the keys it changes.
class State(TypedDict, total=False):
    question: str
    route: str
    answer: str
    sources: list[str]
    model: str | None
    searches: list[dict]  # each agent search: query, chunks found, ms
    clarify: bool


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
    return {"answer": OFF_TOPIC_ANSWER, "sources": [], "model": None, "searches": [], "clarify": False}


def troubleshoot(state: State) -> dict:
    return run_agent("troubleshoot", TROUBLESHOOT_PROMPT, state["question"])


def knowledge(state: State) -> dict:
    return run_agent("knowledge", KNOWLEDGE_PROMPT, state["question"])


builder = StateGraph(State)
builder.add_node("classify", classify)
builder.add_node("off_topic", off_topic)
builder.add_node("troubleshoot", troubleshoot)
builder.add_node("knowledge", knowledge)

builder.add_edge(START, "classify")
# classify goes straight to the agent for its route; each agent does its own searching
builder.add_conditional_edges(
    "classify",
    lambda state: state["route"],
    {"other": "off_topic", "troubleshooting": "troubleshoot", "knowledge": "knowledge"},
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
    """Healthy only when the knowledge base answers. 503 otherwise, so Docker and load balancers see it."""
    try:
        chunks = chunk_count()
    except psycopg.Error as e:
        return JSONResponse(status_code=503, content={"status": "unhealthy", "database": "down", "detail": str(e)})
    return {"status": "healthy", "database": "up", "chunks": chunks}


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
        "searches": result.get("searches", []),
        "clarify": result.get("clarify", False),
    }


def step_summary(node: str, result: dict) -> dict:
    """The part of a node's result the UI shows for that step."""
    if node == "classify":
        return {"route": result["route"]}
    return {"model": result.get("model"), "searches": len(result.get("searches", [])), "clarify": result.get("clarify", False)}


def sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


@app.post("/chat/stream")
def chat_stream(request: ChatRequest):
    """Like /chat, but sends a Server-Sent Event as each graph node starts and finishes, and as each agent
    talks to the LLM and searches, so the UI can draw the path and the agent loop."""

    def events():
        started = time.perf_counter()
        node_started = {}  # task id -> start time
        node = None  # the node running right now
        state = {}
        yield sse({"type": "start"})
        try:
            # "tasks" yields one dict when a node starts (has "input") and one when it ends (has "error");
            # "custom" yields what the agent loop writes: llm, tool, token and reasoning events
            for mode, item in graph.stream({"question": request.message}, stream_mode=["tasks", "custom"]):
                if mode == "custom":
                    yield sse(item)
                elif "input" in item:
                    node = item["name"]
                    node_started[item["id"]] = time.perf_counter()
                    yield sse({"type": "running", "node": node})
                elif item["error"] is None:
                    state.update(item["result"])
                    ms = ms_since(node_started.pop(item["id"]))
                    yield sse({"type": "step", "node": item["name"], "ms": ms, **step_summary(item["name"], item["result"])})
                # a failed node: the stream raises its error right after this
        except psycopg.Error as e:
            # Only search_runbooks talks to Postgres: name the part of the agent loop that failed
            yield sse({"type": "error", "node": node, "part": "db", "detail": f"Knowledge base unavailable: {e}"})
            return
        except OpenAIError as e:
            yield sse({"type": "error", "node": node, "part": "llm", "detail": str(e)})
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
            "searches": len(state.get("searches", [])),
            "clarify": state.get("clarify", False),
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
