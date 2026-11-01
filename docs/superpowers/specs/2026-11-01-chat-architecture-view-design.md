# Chat + live architecture view (step 04 UI)

Date: 2026-11-01
Scope: `04-LangGraph/app/main.py`, `04-LangGraph/app/static/index.html`

## Goal

Replace the single-column bubble chat with a two-column page: chat on the left, a live
architecture diagram on the right that shows each message moving through the app
(Chat UI → FastAPI → LangGraph classify → embed → pgvector search → troubleshoot/knowledge LLM → answer).

## Layout and style

- Full-viewport two columns: chat ~45%, architecture ~55%. Under 900px width they stack (chat first).
- Flat: no chat bubbles, no shadows, no gradients, 1px borders, 4px radius max, one accent color.
- Chat messages are full-width rows: a small uppercase label (`YOU` / `BOT`), the text, a thin divider.
  Bot rows end with one muted meta line: `route · sources · model · total time`.
- Colors are CSS tokens on `:root` with a `prefers-color-scheme: dark` variant.

## Architecture panel

Diagram nodes (HTML elements + SVG connector lines), top to bottom:

1. Chat UI (browser)
2. FastAPI `POST /chat/stream`
3. `classify` (LLM via OpenRouter)
4. Branch: `off_topic` (route `other`) or `retrieve`
5. `retrieve` shown as two sub-nodes: `embed` (all-MiniLM-L6-v2, local) and `pgvector search` (Postgres)
6. Branch: `troubleshoot` (LLM) or `knowledge` (LLM)
7. Answer → back to Chat UI

Node states: `idle` (grey), `running` (accent outline, subtle pulse), `done` (solid accent),
`skipped` (dimmed), `error` (red). Edges on the taken path are highlighted.

Below the diagram, a step log for the selected message, one line per step, filled live:

```
classify     → troubleshooting                                   820 ms
embed        → 384-dim vector                                     35 ms
search       → 5 chunks · top kubernetes-crashloopbackoff.md 0.71 110 ms
troubleshoot → dots-studio/dots-3-note-preview:free             2.1 s
```

Clicking an earlier bot message re-renders its stored trace on the right.
Before any message, the diagram is shown idle.

## Backend

- New `POST /chat/stream` (body `{"message": str}`) returning `text/event-stream`.
  Runs `graph.stream({"question": ...}, stream_mode="tasks")`, which reports each node's start
  and result, timing each node.
  Events (each `data:` is JSON):
  - `{"type": "start"}` when the request is accepted
  - `{"type": "running", "node": "classify"}` when a node starts
  - `{"type": "step", "node": "classify", "ms": 820, "route": "troubleshooting"}`
  - `{"type": "step", "node": "retrieve", "ms": 145, "embed_ms": 35, "search_ms": 110,
     "chunks": [{"source": "...", "similarity": 0.71}, ...]}` (no chunk text)
  - `{"type": "step", "node": "troubleshoot" | "knowledge" | "off_topic", "ms": 2100, "model": "..."}`
  - `{"type": "done", "answer": "...", "sources": [...], "route": "...", "model": "...", "ms": 3065}`
  - `{"type": "error", "node": "<node that was running>", "detail": "..."}` then the stream ends.
    Database errors add `"part": "search"` so only the pgvector box turns red.
- The graph shape is unchanged. `search()` records `embed_ms` and `search_ms`; `retrieve` puts them in state.
- The answer text is `.strip()`ed.
- `POST /chat` stays (same response shape). `GET /` redirects to `/ui`.

## Errors

- DB failure → `error` event with node `retrieve`; the pgvector node turns red.
- LLM failure → `error` event with the LLM node that was running.
- Network/stream drop in the browser → the running node turns red, chat shows "Connection lost".

## Testing

- Python script that posts one troubleshooting, one knowledge and one off-topic question to
  `/chat/stream` and checks event order and fields.
- Drive the UI in a browser, screenshot light and dark, confirm nodes light up and the log fills.

## Out of scope

Real specialized agents per route, auth, persisting chat history across reloads.
