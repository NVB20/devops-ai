# Example play button: fast and guided demo (step 05 UI)

Date: 2026-11-02
Scope: `05-Agents/app/static/index.html`, `README.md`

## Goal

Let anyone watch the RAG flow at work with OpenRouter by playing an example question, at any time
(not only on the empty chat), in one of two modes:

- **Fast**: the example is sent like a typed message.
- **Guided**: the same real run, but paced so each step can be followed, with a caption that explains it.

No backend change: `/chat/stream` already sends everything the captions need (route, model, search
queries, chunks with similarity, timings).

## The button

- A ▶ button in the input bar, next to the mic, always visible. Label/title: "Play an example".
- Clicking it opens a small popover above the input bar:
  - A two-option switch at the top: **Fast** / **Guided**. Default: **Guided**. The last choice is kept
    in `localStorage` (wrapped in try/catch; falls back to Guided).
  - The examples, one per row, each with a muted tag naming what it shows:

    | Example | Tag |
    |---|---|
    | My pod keeps going into CrashLoopBackOff | troubleshooting · searches |
    | How do we rotate database credentials? | knowledge |
    | Pods are pending and a node is NotReady | troubleshooting · several searches |
    | Something is broken | clarifying question |
    | What's the best pizza in town? | off-topic · no agent |

- Clicking an example closes the popover and plays it. Escape or a click outside closes it.
- The existing empty-chat example buttons stay and keep sending at normal speed.

## Fast mode

Calls the existing `ask(text)`. Nothing else changes.

## Guided mode

Calls `ask(text, { guided: true })`. The run is real (same `/chat/stream` request). Inside the
`for await` event loop, after an event is applied and rendered, guided mode waits before reading
the next event. Events that arrive meanwhile stay in the response stream buffer, so none are lost.

Pause lengths reuse the `replay()` timings: 1300 ms after `running`, 25 ms after `token` / `reasoning`,
450 ms after anything else. An event that changes the caption waits 1800 ms instead (whichever is
longer), so the caption can be read. With `prefers-reduced-motion`, pauses are halved; captions are unchanged.

### Captions

A caption strip at the top of the architecture panel, shown only while the selected trace is a guided
run. It holds one line, replaced on each caption-worthy event; earlier captions are not kept (the step
log already lists every step). Text comes from the event data:

| Event | Caption |
|---|---|
| `start` | Your question goes to FastAPI `POST /chat/stream` |
| `running classify` | classify: one quick OpenRouter call picks troubleshooting, knowledge or off-topic |
| `step classify` | Routed to **{route}** |
| `running troubleshoot` / `knowledge` | The {agent name} sends your question to OpenRouter along with a `search_runbooks` tool |
| `running off_topic` | Not a DevOps question: a fixed reply, no OpenRouter answer, no search |
| `llm`, action `search` | OpenRouter ({model}) chose to search: “{query}”[, “{query}”] |
| `tool` | search_runbooks embedded “{query}” and pgvector returned {n} chunks. Best match: `{source}` ({similarity}) — or “no chunk above 0.3” when empty |
| `llm`, action `answer` | OpenRouter has enough context and is writing the answer from those excerpts |
| `llm`, action `clarify` | OpenRouter needs more detail and asks you a clarifying question |
| `done` | Done: cites {sources or “no runbook”} · {n} searches · {total time} |
| `error` | Error in {OpenRouter / the knowledge base / the server}: {detail} |

`token` and `reasoning` events never change the caption.

### While a guided run plays

- The ▶ button and the send button are disabled until the run ends (send already is during any run).
- Selecting an earlier message shows that message's trace; the guided run keeps going in the
  background and its caption strip hides. Selecting the guided message again shows the current caption.
- The Replay button keeps working on finished messages as before.

## Errors

Same handling as today: the bot row shows `Error: ...`, the diagram marks the failed part (`llm` or
`db`), and the caption shows the error line above.

## Testing

- No backend change, so the existing `05-Agents/tests` stay as they are and must still pass.
- Manual check with the app running against OpenRouter: play every example in both modes; confirm
  guided captions match the table, the popover closes on Escape / outside click, the buttons are
  disabled during a guided run, the mode choice survives a reload, and an error (stop the DB) shows
  the db error caption.

## README

One line under step 05: the ▶ button plays an example, Fast or Guided.
