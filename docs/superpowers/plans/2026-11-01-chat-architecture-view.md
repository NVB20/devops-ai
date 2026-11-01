# Chat + Live Architecture View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Two-column step 04 UI: flat chat on the left, live architecture diagram on the right, fed by a new streaming endpoint.

**Architecture:** `POST /chat/stream` runs the existing LangGraph graph with `stream_mode="tasks"` and turns each
node start/result into a Server-Sent Event. The page reads the stream with `fetch` and updates a per-message
trace object that drives the diagram's node states, the connector lines and the step log.

**Tech Stack:** FastAPI `StreamingResponse`, LangGraph 1.2 (`stream_mode="tasks"`), vanilla HTML/CSS/JS + inline SVG, pytest + FastAPI `TestClient`.

Spec: `docs/superpowers/specs/2026-11-01-chat-architecture-view-design.md`

## Global Constraints

- Flat style: no bubbles, no shadows, no gradients, 1px borders, radius ≤ 4px, one accent color.
- Colors are tokens on `:root` with a `prefers-color-scheme: dark` variant; `body` has an explicit background.
- `POST /chat` keeps its response shape. The graph's nodes and edges are unchanged.
- No new runtime dependencies. `pytest` is installed into the venv for tests only.

---

### Task 1: Streaming endpoint

**Files:**
- Modify: `04-LangGraph/app/main.py`
- Create: `04-LangGraph/tests/test_stream.py`

**Interfaces:**
- Produces: `POST /chat/stream` (body `{"message": str}`), `text/event-stream`, events in this order:
  `start` → (`running` node, `step` node)* → `done` | `error`.
  `step` fields: always `node`, `ms`; classify adds `route`; retrieve adds `embed_ms`, `search_ms`,
  `chunks: [{source, similarity}]`; troubleshoot/knowledge/off_topic add `model`.
  `done`: `answer`, `sources`, `route`, `model`, `ms`. `error`: `node`, `detail`.
- Produces: `nearest_chunks(vector, k=TOP_K) -> list[dict]` (DB half of `search()`), monkeypatchable in tests.

- [ ] **Step 1: Write the failing tests** (`tests/test_stream.py`): fake `main.client` (returns the route word for the
  classify prompt, `"\n\n1. do it [a.md]"` otherwise) and fake `main.nearest_chunks`. Parametrize the
  troubleshooting / knowledge / other questions and assert the exact event type+node sequence; assert retrieve
  carries chunk sources without text; assert `done.answer` is stripped; assert a `psycopg.OperationalError`
  from `nearest_chunks` yields a final `error` event with `node == "retrieve"`; assert `GET /` redirects to `/ui`.
- [ ] **Step 2: Run** `venv/Scripts/python.exe -m pytest tests -q` → FAIL (404 on `/chat/stream`).
- [ ] **Step 3: Implement** in `main.py`:
  - split `search()` into `embedder.embed` + `nearest_chunks()`; `retrieve` times both into `state["timings"]`;
  - `.strip()` the LLM answer in `answer_from_chunks`;
  - `step_summary(node, result)`, `sse(event)`, and `chat_stream()` iterating `graph.stream(..., stream_mode="tasks")`:
    a task dict with `"input"` is a start, one with `"error"` is a result; time between them per task id;
  - `GET /` returns `RedirectResponse("/ui")`.
- [ ] **Step 4: Run** the tests → PASS.

### Task 2: Two-column flat UI with live diagram

**Files:**
- Modify (rewrite): `04-LangGraph/app/static/index.html`

**Interfaces:**
- Consumes: the event stream from Task 1.
- Diagram node ids: `chat, api, classify, off_topic, embed, search, troubleshoot, knowledge, answer`.
  Graph node → diagram ids: `retrieve → [embed, search]`, every other graph node maps to itself.
- Trace object per bot message: `{question, nodes: {id: {state, detail}}, log: [{node, text, ms, extra}]}`;
  states `idle | running | done | skipped | error`.

- [ ] **Step 1:** Layout: CSS grid `45fr 55fr`, stacking under 900px; flat chat rows (`YOU`/`BOT` label, text, meta line).
- [ ] **Step 2:** Diagram: Chat UI → FastAPI → LangGraph box (classify; off_topic | embed → pgvector search;
  troubleshoot | knowledge) → Answer. SVG overlay draws elbow connectors from element rects, redrawn on resize.
- [ ] **Step 3:** Stream reader (`fetch` + `TextDecoderStream`, split on blank lines) and `apply(trace, event)`:
  classify step marks the untaken branch `skipped`; error/connection loss turns `running` nodes `error`.
- [ ] **Step 4:** Step log under the diagram; clicking a bot row re-renders its trace; idle diagram before any message.
- [ ] **Step 5: Verify** in a browser against the running server: one question per route, light and dark screenshots.

### Task 3: Docs

- [ ] Update the step 04 section of `README.md`: `/ui` layout, `POST /chat/stream` events, `pytest` command.
