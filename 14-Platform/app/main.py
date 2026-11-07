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
from fastapi import FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastembed import TextEmbedding
from faster_whisper import WhisperModel
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from openai import OpenAI, OpenAIError
from pgvector.psycopg import register_vector
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from pydantic import BaseModel

from app.ingest import DATABASE_URL, EMBED_MODEL

# Reads LLM_PROVIDER, OPENROUTER_API_KEY, OPENROUTER_MODEL, OLLAMA_* and DATABASE_URL from the .env in the repo root
load_dotenv()

STATIC_DIR = Path(__file__).parent / "static"

# Which LLM answers: OpenRouter (cloud) or Ollama (a local model). Both speak the OpenAI API, so only the
# base_url, the key and the model name change. Any other value fails at startup instead of on the first question.
PROVIDER = os.getenv("LLM_PROVIDER", "openrouter").strip().lower()
PROVIDERS = {
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "api_key": os.getenv("OPENROUTER_API_KEY"),
        "model": os.getenv("OPENROUTER_MODEL", "openrouter/free"),
    },
    # Ollama on the host. From a container that's host.docker.internal (compose maps it on Linux too).
    "ollama": {
        "base_url": os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1"),
        "api_key": "ollama",  # Ollama ignores it, but the OpenAI client needs one
        "model": os.getenv("OLLAMA_MODEL", "llama3.2"),
    },
}
if PROVIDER not in PROVIDERS:
    raise RuntimeError(f"LLM_PROVIDER must be one of {', '.join(PROVIDERS)}, not {PROVIDER!r}")
MODEL = PROVIDERS[PROVIDER]["model"]
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

# ── Answer review (step 14) ── A second LLM call checks the answer against the runbook excerpts the agent
# found. Unsupported claims get one rewrite with the reviewer's notes; if the rewrite still fails, the answer
# goes out flagged, with the claims the runbooks don't back up.
REVIEW_PROMPT = """You check a DevOps assistant's answer against the runbook excerpts it was given.
List every command, step or fact in the answer that the excerpts do not support.
Fine, don't list them: placeholders like <pod>, wording and structure, citations like [disk-full.md],
and saying something is not in the runbooks.
Reply with JSON only, no other text:
{"supported": true}
or
{"supported": false, "unsupported": ["each unsupported claim, in a few words"]}"""

REVISE_PROMPT = """A reviewer checked your answer against the runbook excerpts below and found claims they don't support:
{issues}

Rewrite your answer using ONLY these excerpts: fix or drop the unsupported parts, keep the same format, and cite
the runbook file after each step. Do not search again. If the excerpts don't answer the question, say so.

Runbook excerpts:
{evidence}"""

MAX_ISSUES = 5  # the reviewer's list, as shown to the agent and the user

ROUTES = ("troubleshooting", "knowledge", "other")
OFF_TOPIC_ANSWER = "Sorry, I only help with DevOps questions about our systems and runbooks."

app = FastAPI(
    title="DevOps AI Chatbot",
    version="14.0.0",
)

# ── Metrics (step 09) ── Prometheus scrapes GET /metrics. Label values come from short fixed lists
# (routes, outcomes, kinds), never from the question, so the number of series stays small.
HTTP_REQUESTS = Counter("devops_ai_http_requests_total", "HTTP requests", ["method", "path", "status"])
HTTP_SECONDS = Histogram("devops_ai_http_request_duration_seconds", "HTTP request time, to the end of the response headers",
                         ["method", "path"])
QUESTIONS = Counter("devops_ai_questions_total", "Questions answered, by route and outcome "
                    "(answered, no_answer, clarify, off_topic, error)", ["endpoint", "route", "outcome"])
QUESTION_SECONDS = Histogram("devops_ai_question_duration_seconds", "Time to answer a question, LLM and searches included",
                             ["endpoint", "route"], buckets=(1, 2, 5, 10, 20, 30, 60, 120, 300))
LLM_SECONDS = Histogram("devops_ai_llm_call_duration_seconds", "One LLM call (classify, or one agent turn)",
                        ["provider", "kind"], buckets=(0.25, 0.5, 1, 2, 5, 10, 20, 40, 80, 160))
LLM_ERRORS = Counter("devops_ai_llm_errors_total", "LLM calls that failed", ["provider", "kind"])
SEARCHES = Counter("devops_ai_searches_total", "Runbook searches the agents ran", ["agent"])
SEARCH_SECONDS = Histogram("devops_ai_search_duration_seconds", "One runbook search: embed the query and ask pgvector",
                           buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5))
REVIEWS = Counter("devops_ai_reviews_total", "Answer reviews by result (passed, revised, flagged, unchecked)", ["result"])
SEARCH_TOP_SIMILARITY = Histogram("devops_ai_search_top_similarity", "Similarity of the best chunk a search found (0 when none)",
                                  buckets=(0, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1))
KB_CHUNKS = Gauge("devops_ai_kb_chunks", "Runbook chunks in the knowledge base, as /health last saw it (-1: database down)")


def outcome(result: dict) -> str:
    """What happened to a question, for the metrics."""
    if result.get("route") == "other":
        return "off_topic"
    if result.get("clarify"):
        return "clarify"
    return "answered" if result.get("sources") else "no_answer"


def record_question(endpoint: str, result: dict, started: float, failed: bool = False):
    route = result.get("route") or "unknown"
    QUESTIONS.labels(endpoint, route, "error" if failed else outcome(result)).inc()
    QUESTION_SECONDS.labels(endpoint, route).observe(time.perf_counter() - started)


@app.middleware("http")
async def http_metrics(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    # The route's template ("/chat"), never the raw URL: /search?q=... would make a new series per question
    route = request.scope.get("route")
    path = getattr(route, "path", "unmatched")
    if path != "/metrics":
        HTTP_REQUESTS.labels(request.method, path, str(response.status_code)).inc()
        HTTP_SECONDS.labels(request.method, path).observe(time.perf_counter() - started)
    return response

# OpenRouter and Ollama both speak the OpenAI API, so the OpenAI client works with a different base_url.
# A local model on the CPU is slower than OpenRouter: give it longer.
client = OpenAI(
    api_key=PROVIDERS[PROVIDER]["api_key"],
    base_url=PROVIDERS[PROVIDER]["base_url"],
    timeout=float(os.getenv("LLM_TIMEOUT", 180 if PROVIDER == "ollama" else 60)),
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
    # Short timeouts on the connect and the query: a health check that hangs is worse than one that says "down"
    with psycopg.connect(DATABASE_URL, connect_timeout=3, options="-c statement_timeout=3000") as conn:
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
    started = time.perf_counter()
    try:
        text, calls, model = stream_reply(messages, final, on_text)
    except Exception:
        LLM_ERRORS.labels(PROVIDER, "agent").inc()
        raise
    finally:
        LLM_SECONDS.labels(PROVIDER, "agent").observe(time.perf_counter() - started)
    return {"text": text, "calls": list(calls.values()), "model": model}


def stream_reply(messages: list[dict], final: bool, on_text) -> tuple[str, dict, str | None]:
    """llm_turn() without the metrics: the call itself and the reading of its stream."""
    stream = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        tools=[SEARCH_TOOL],
        tool_choice="none" if final else "auto",
        stream=True,
        # OpenRouter only: send the thinking of models that have it
        extra_body={"include_reasoning": True} if PROVIDER == "openrouter" else None,
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
    return text, calls, model


def run_agent(agent: str, prompt: str, question: str) -> dict:
    """The agent loop: ask the LLM, run the searches it asks for, hand back the results, ask again,
    until it answers or has used its MAX_SEARCHES. Each step is also sent to the UI as a custom stream event."""
    write = get_stream_writer()
    messages = [{"role": "system", "content": prompt}, {"role": "user", "content": question}]
    seen = set()  # every runbook a search returned
    evidence = {}  # every excerpt a search returned, for the review: (source, text) -> excerpt
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
            SEARCHES.labels(agent).inc()
            SEARCH_SECONDS.observe(time.perf_counter() - started)
            SEARCH_TOP_SIMILARITY.observe(max((c["similarity"] for c in chunks), default=0))
            seen.update(c["source"] for c in chunks)
            evidence.update({(c["source"], c["text"]): {"source": c["source"], "text": c["text"]} for c in chunks})
            searches.append({"query": query, "ms": ms_since(started),
                             "chunks": [{"source": c["source"], "similarity": c["similarity"]} for c in chunks]})
            write({"type": "tool", "agent": agent, "turn": turn, **searches[-1]})
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": tool_result(chunks)})

    if clarify:
        return {"answer": answer.removeprefix(CLARIFY).strip(), "sources": [], "model": model,
                "searches": searches, "clarify": True, "evidence": []}
    return {"answer": answer, "sources": cited_sources(answer, seen), "model": model, "searches": searches,
            "clarify": False, "evidence": list(evidence.values())}


def cited_sources(answer: str, found) -> list[str]:
    """Only the runbooks the answer cites, so "couldn't find it" doesn't list the runbooks it rejected."""
    return [s for s in sorted(found) if s in answer]


def review_reply(text: str) -> dict | None:
    """The reviewer's JSON verdict, or None when it isn't readable (small models add text around it)."""
    start, end = text.find("{"), text.rfind("}")
    try:
        verdict = json.loads(text[start:end + 1]) if start >= 0 else None
    except json.JSONDecodeError:
        return None
    if not isinstance(verdict, dict) or not isinstance(verdict.get("supported"), bool):
        return None
    issues = verdict.get("unsupported") if isinstance(verdict.get("unsupported"), list) else []
    issues = [str(i).strip() for i in issues if str(i).strip()][:MAX_ISSUES]
    # "supported: false" with nothing listed gives the agent nothing to fix: treat it as supported
    return {"supported": verdict["supported"] or not issues, "issues": issues if not verdict["supported"] else []}


def plain_llm_call(kind: str, messages: list[dict]) -> str:
    """One non-streamed LLM call without tools (review and rewrite), with the step 09 metrics."""
    started = time.perf_counter()
    try:
        response = client.chat.completions.create(model=MODEL, temperature=0, messages=messages)
    except Exception:
        LLM_ERRORS.labels(PROVIDER, kind).inc()
        raise
    finally:
        LLM_SECONDS.labels(PROVIDER, kind).observe(time.perf_counter() - started)
    return (response.choices[0].message.content or "").strip()


def excerpts(evidence: list[dict]) -> str:
    return "\n\n".join(f"[{e['source']}]\n{e['text']}" for e in evidence)


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
    evidence: list[dict]  # the excerpts the agent's searches returned: {"source", "text"}
    review: dict  # {"status": passed | revised | flagged | unchecked | skipped | retry, "issues": [...]}


def classify(state: State) -> dict:
    """One short LLM call: which kind of question is this?"""
    started = time.perf_counter()
    try:
        response = client.chat.completions.create(
            model=MODEL,
            temperature=0,
            messages=[
                {"role": "system", "content": CLASSIFY_PROMPT},
                {"role": "user", "content": state["question"]},
            ],
        )
    except Exception:
        LLM_ERRORS.labels(PROVIDER, "classify").inc()
        raise
    finally:
        LLM_SECONDS.labels(PROVIDER, "classify").observe(time.perf_counter() - started)
    word = (response.choices[0].message.content or "").strip().lower().strip(".'\"`*")
    return {"route": word if word in ROUTES else "knowledge"}


def off_topic(state: State) -> dict:
    return {"answer": OFF_TOPIC_ANSWER, "sources": [], "model": None, "searches": [], "clarify": False,
            "review": {"status": "skipped", "issues": []}}


def troubleshoot(state: State) -> dict:
    return run_agent("troubleshoot", TROUBLESHOOT_PROMPT, state["question"])


def knowledge(state: State) -> dict:
    return run_agent("knowledge", KNOWLEDGE_PROMPT, state["question"])


def review(state: State) -> dict:
    """Checks the answer against the excerpts the agent found. Nothing to check, and nothing reviewed:
    a clarifying question, or an answer that cites no runbook (it says the runbooks don't cover it)."""
    revised = state.get("review", {}).get("status") == "retry"
    if state.get("clarify") or not state.get("sources") or not state.get("evidence"):
        # A rewrite that now says the runbooks don't cover it still counts as revised
        status = "revised" if revised else "skipped"
        if revised:
            REVIEWS.labels(status).inc()
        return {"review": {"status": status, "issues": []}}
    reply = plain_llm_call("review", [
        {"role": "system", "content": REVIEW_PROMPT},
        {"role": "user", "content": f"Runbook excerpts:\n{excerpts(state['evidence'])}\n\nAnswer:\n{state['answer']}"},
    ])
    verdict = review_reply(reply)
    if verdict is None:  # an unreadable verdict doesn't block the answer: it goes out unchecked
        status, issues = "unchecked", []
    elif verdict["supported"]:
        status, issues = ("revised" if revised else "passed"), []
    else:
        status, issues = ("flagged" if revised else "retry"), verdict["issues"]
    if status != "retry":
        REVIEWS.labels(status).inc()
    return {"review": {"status": status, "issues": issues}}


def revise(state: State) -> dict:
    """The one rewrite: the agent's own prompt, its first answer, and the reviewer's notes. No more searches."""
    prompt = TROUBLESHOOT_PROMPT if state["route"] == "troubleshooting" else KNOWLEDGE_PROMPT
    notes = "\n".join(f"- {issue}" for issue in state["review"]["issues"])
    answer = plain_llm_call("revise", [
        {"role": "system", "content": prompt},
        {"role": "user", "content": state["question"]},
        {"role": "assistant", "content": state["answer"]},
        {"role": "user", "content": REVISE_PROMPT.format(issues=notes, evidence=excerpts(state["evidence"]))},
    ]) or state["answer"]
    return {"answer": answer, "sources": cited_sources(answer, {e["source"] for e in state["evidence"]})}


def after_review(state: State) -> str:
    return "revise" if state["review"]["status"] == "retry" else END


builder = StateGraph(State)
builder.add_node("classify", classify)
builder.add_node("off_topic", off_topic)
builder.add_node("troubleshoot", troubleshoot)
builder.add_node("knowledge", knowledge)
builder.add_node("review", review)
builder.add_node("revise", revise)

builder.add_edge(START, "classify")
# classify goes straight to the agent for its route; each agent does its own searching
builder.add_conditional_edges(
    "classify",
    lambda state: state["route"],
    {"other": "off_topic", "troubleshooting": "troubleshoot", "knowledge": "knowledge"},
)
builder.add_edge("off_topic", END)
# Every agent answer is reviewed; a failed review gets one rewrite, which is reviewed again
builder.add_edge("troubleshoot", "review")
builder.add_edge("knowledge", "review")
builder.add_conditional_edges("review", after_review, {"revise": "revise", END: END})
builder.add_edge("revise", "review")

graph = builder.compile()


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/ui")


@app.get("/health")
def health():
    """Healthy only when the knowledge base answers. 503 otherwise, so Docker and load balancers see it.
    It also says which LLM answers, but doesn't call it: a slow or rate-limited LLM shouldn't restart the app."""
    llm = {"provider": PROVIDER, "model": MODEL}
    try:
        chunks = chunk_count()
    except psycopg.Error as e:
        KB_CHUNKS.set(-1)
        return JSONResponse(status_code=503, content={"status": "unhealthy", "database": "down", "detail": str(e), "llm": llm})
    KB_CHUNKS.set(chunks)
    return {"status": "healthy", "database": "up", "chunks": chunks, "llm": llm}


@app.get("/metrics", include_in_schema=False)
def metrics():
    """What Prometheus scrapes."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


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
    started = time.perf_counter()
    try:
        result = graph.invoke({"question": request.message})
    except psycopg.Error as e:
        record_question("chat", {}, started, failed=True)
        raise HTTPException(status_code=503, detail=f"Knowledge base unavailable: {e}")
    except Exception as e:
        record_question("chat", {}, started, failed=True)
        raise HTTPException(status_code=502, detail=str(e))
    record_question("chat", result, started)

    return {
        "user": request.message,
        "answer": result["answer"],
        "model": result["model"],
        "sources": result["sources"],
        "route": result["route"],
        "searches": result.get("searches", []),
        "clarify": result.get("clarify", False),
        "review": result.get("review", {"status": "skipped", "issues": []}),
    }


def step_summary(node: str, result: dict) -> dict:
    """The part of a node's result the UI shows for that step."""
    if node == "classify":
        return {"route": result["route"]}
    if node == "review":
        return {"review": result["review"]}
    if node == "revise":
        return {"sources": result["sources"]}
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
            record_question("stream", state, started, failed=True)
            yield sse({"type": "error", "node": node, "part": "db", "detail": f"Knowledge base unavailable: {e}"})
            return
        except OpenAIError as e:
            record_question("stream", state, started, failed=True)
            yield sse({"type": "error", "node": node, "part": "llm", "detail": str(e)})
            return
        except Exception as e:
            record_question("stream", state, started, failed=True)
            yield sse({"type": "error", "node": node, "detail": str(e)})
            return

        record_question("stream", state, started)

        yield sse({
            "type": "done",
            "answer": state["answer"],
            "sources": state["sources"],
            "route": state["route"],
            "model": state["model"],
            "searches": len(state.get("searches", [])),
            "clarify": state.get("clarify", False),
            "review": state.get("review", {"status": "skipped", "issues": []}),
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
