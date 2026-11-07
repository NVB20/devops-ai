"""Checks the /chat/stream events and the agent loop with a fake LLM and a fake database (no network, no Postgres)."""
import json
from types import SimpleNamespace

import psycopg
import pytest
from fastapi.testclient import TestClient
from faster_whisper import decode_audio

from app import main

CHUNKS = {
    "pods pending": [{"source": "pod-pending.md", "text": "describe the pod", "similarity": 0.74}],
    "node NotReady": [{"source": "node-notready.md", "text": "check kubelet", "similarity": 0.69},
                      {"source": "disk-full.md", "text": "df -h", "similarity": 0.35}],
}


def chunk(content=None, reasoning=None, tool_calls=None):
    """One streamed piece of a reply, shaped like the OpenAI SDK's ChatCompletionChunk."""
    delta = SimpleNamespace(content=content, reasoning=reasoning, tool_calls=tool_calls)
    return SimpleNamespace(model="fake-model", choices=[SimpleNamespace(delta=delta)])


def tool_call(index, query):
    """A search request split in pieces, the way providers stream them."""
    args = json.dumps({"query": query})
    return [
        chunk(tool_calls=[SimpleNamespace(index=index, id=f"call{index}", function=SimpleNamespace(name="search_runbooks", arguments=""))]),
        chunk(tool_calls=[SimpleNamespace(index=index, id=None, function=SimpleNamespace(name=None, arguments=args[:5]))]),
        chunk(tool_calls=[SimpleNamespace(index=index, id=None, function=SimpleNamespace(name=None, arguments=args[5:]))]),
    ]


def fake_llm(route, turns, seen=None):
    """An OpenAI-like client. The classify prompt gets `route`. Each agent call plays the next entry of `turns`:
    a list of queries to search, or the final answer text. `seen` collects each agent call's arguments."""
    turns = list(turns)

    def create(model, messages, stream=False, **kwargs):
        if messages[0]["content"] == main.CLASSIFY_PROMPT:
            return SimpleNamespace(model="fake-model", choices=[SimpleNamespace(message=SimpleNamespace(content=route))])
        if seen is not None:
            seen.append({"messages": [dict(m) for m in messages], **kwargs})
        turn = turns.pop(0)
        if isinstance(turn, list):
            return iter([chunk(reasoning="I should search.")] + [c for i, q in enumerate(turn) for c in tool_call(i, q)])
        words = turn.split(" ")
        return iter(chunk(content=w + (" " if i < len(words) - 1 else "")) for i, w in enumerate(words))

    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def fake_search(query):
    return CHUNKS.get(query, [])


def stream(question):
    with TestClient(main.app) as client:
        response = client.post("/chat/stream", json={"message": question})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    return [json.loads(block.removeprefix("data: ")) for block in response.text.split("\n\n") if block]


def loop_events(events):
    """The agent loop's events, without the streamed text."""
    return [(e["type"], e.get("action")) for e in events if e["type"] in ("llm", "tool")]


@pytest.mark.parametrize("route, agent", [("troubleshooting", "troubleshoot"), ("knowledge", "knowledge")])
def test_agent_searches_twice_then_answers(monkeypatch, route, agent):
    answer = "Likely cause: no room [pod-pending.md] and kubelet down [node-notready.md]"
    monkeypatch.setattr(main, "client", fake_llm(route, [["pods pending"], ["node NotReady"], answer]))
    monkeypatch.setattr(main, "search", fake_search)

    events = stream("pods are pending and a node is NotReady")

    nodes = [(e["type"], e.get("node")) for e in events if e["type"] in ("start", "running", "step", "done")]
    assert nodes == [("start", None), ("running", "classify"), ("step", "classify"),
                     ("running", agent), ("step", agent), ("done", None)]
    assert loop_events(events) == [("llm", "search"), ("tool", None), ("llm", "search"), ("tool", None), ("llm", "answer")]

    llm = [e for e in events if e["type"] == "llm"]
    assert [e["turn"] for e in llm] == [1, 2, 3]
    assert llm[0]["queries"] == ["pods pending"] and llm[1]["queries"] == ["node NotReady"]
    assert all(e["agent"] == agent and isinstance(e["ms"], int) for e in llm)
    tools = [e for e in events if e["type"] == "tool"]
    assert tools[1]["chunks"] == [{"source": "node-notready.md", "similarity": 0.69}, {"source": "disk-full.md", "similarity": 0.35}]

    # The answer streams word by word, and the thinking arrives as its own events
    assert "".join(e["text"] for e in events if e["type"] == "token") == answer
    assert [e["turn"] for e in events if e["type"] == "reasoning"] == [1, 2]

    done = events[-1]
    assert done["answer"] == answer
    assert done["sources"] == ["node-notready.md", "pod-pending.md"]  # disk-full.md came back but isn't cited
    assert done["searches"] == 2 and done["clarify"] is False
    assert [e for e in events if e["type"] == "step"][-1]["searches"] == 2


def test_tool_results_go_back_to_the_llm(monkeypatch):
    seen = []
    monkeypatch.setattr(main, "client", fake_llm("troubleshooting", [["pods pending"], "done [pod-pending.md]"], seen))
    monkeypatch.setattr(main, "search", fake_search)

    stream("pods are pending")

    assert seen[0]["tools"] == [main.SEARCH_TOOL]
    assert seen[0]["messages"][0]["content"] == main.TROUBLESHOOT_PROMPT
    second = seen[1]["messages"]
    assert second[2]["tool_calls"][0]["function"] == {"name": "search_runbooks", "arguments": '{"query": "pods pending"}'}
    assert second[3] == {"role": "tool", "tool_call_id": "call0", "content": "[pod-pending.md]\ndescribe the pod"}


def test_vague_question_gets_a_clarifying_question(monkeypatch):
    monkeypatch.setattr(main, "client", fake_llm("troubleshooting", ["CLARIFY: Which service is broken?"]))
    monkeypatch.setattr(main, "search", fake_search)

    events = stream("something is broken")

    assert loop_events(events) == [("llm", "clarify")]
    done = events[-1]
    assert done["answer"] == "Which service is broken?"
    assert done["clarify"] is True and done["sources"] == [] and done["searches"] == 0


def test_search_limit_forces_an_answer(monkeypatch):
    seen = []
    turns = [["a"], ["b"], ["c"], "best I can do"]
    monkeypatch.setattr(main, "client", fake_llm("knowledge", turns, seen))
    monkeypatch.setattr(main, "search", fake_search)

    events = stream("how do we deploy?")

    assert [e["action"] for e in events if e["type"] == "llm"] == ["search", "search", "search", "answer"]
    assert [e for e in events if e["type"] == "llm"][-1]["forced"] is True
    assert [s["tool_choice"] for s in seen] == ["auto", "auto", "auto", "none"]
    assert events[-1]["searches"] == main.MAX_SEARCHES


def test_off_topic_skips_the_agents(monkeypatch):
    monkeypatch.setattr(main, "client", fake_llm("other", []))

    events = stream("best pizza in town?")

    assert [(e["type"], e.get("node")) for e in events] == [
        ("start", None), ("running", "classify"), ("step", "classify"), ("running", "off_topic"), ("step", "off_topic"), ("done", None)]
    assert events[-1]["answer"] == main.OFF_TOPIC_ANSWER


def test_database_error_names_the_search(monkeypatch):
    def broken(query):
        raise psycopg.OperationalError("connection refused")

    monkeypatch.setattr(main, "client", fake_llm("troubleshooting", [["pods pending"]]))
    monkeypatch.setattr(main, "search", broken)

    events = stream("pods are pending")

    assert events[-1]["type"] == "error"
    assert events[-1]["node"] == "troubleshoot"
    assert events[-1]["part"] == "db"
    assert "connection refused" in events[-1]["detail"]


def test_chat_endpoint_returns_the_agent_answer(monkeypatch):
    monkeypatch.setattr(main, "client", fake_llm("knowledge", [["pods pending"], "Explained [pod-pending.md]"]))
    monkeypatch.setattr(main, "search", fake_search)

    with TestClient(main.app) as client:
        body = client.post("/chat", json={"message": "how do pods get scheduled?"}).json()
    assert body["answer"] == "Explained [pod-pending.md]"
    assert body["sources"] == ["pod-pending.md"]
    assert body["route"] == "knowledge" and [s["query"] for s in body["searches"]] == ["pods pending"]


def test_bad_tool_arguments_search_the_question():
    assert main.tool_query('{"query": "disk full"}', "q") == "disk full"
    assert main.tool_query("{not json", "the question") == "the question"
    assert main.tool_query('{"query": ""}', "the question") == "the question"


def test_clarifying_question_without_the_mark():
    assert main.is_clarifying("CLARIFY: Which service?")
    # Models sometimes drop the mark: a question that cites no runbook still counts
    assert main.is_clarifying("What exactly is broken? For example, a pod, a pipeline, or something else?")
    assert not main.is_clarifying("Likely cause: disk full [disk-full.md]. Want me to check more?")
    assert not main.is_clarifying("I couldn't find it in the runbooks.")


def fake_whisper(calls):
    """A Whisper stand-in that records which model and language each call used."""
    def model(name):
        def transcribe(audio, language=None, **kwargs):
            assert audio.read() == b"fake audio"
            calls.append((name, language))
            segments = [SimpleNamespace(text=" my pod"), SimpleNamespace(text=" keeps crashing ")]
            return iter(segments), SimpleNamespace(language=language or "en")
        return SimpleNamespace(transcribe=transcribe)
    return model


def test_transcribe_joins_whisper_segments(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "whisper", fake_whisper(calls))

    with TestClient(main.app) as client:
        response = client.post("/transcribe", files={"audio": ("speech", b"fake audio", "audio/webm")})
    assert response.status_code == 200
    assert response.json() == {"text": "my pod keeps crashing", "language": "en"}
    assert calls == [(main.WHISPER_MODEL, None)]


def test_live_transcribe_uses_the_fast_model_and_given_language(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "whisper", fake_whisper(calls))

    with TestClient(main.app) as client:
        response = client.post("/transcribe", files={"audio": ("speech", b"fake audio", "audio/webm")},
                               data={"live": "true", "language": "he"})
    assert response.json()["language"] == "he"
    assert calls == [(main.WHISPER_LIVE_MODEL, "he")]


def test_transcribe_rejects_unreadable_audio(monkeypatch):
    # Decode like the real model does, without downloading it
    monkeypatch.setattr(main, "whisper", lambda name: SimpleNamespace(transcribe=lambda audio, **kwargs: decode_audio(audio)))

    with TestClient(main.app) as client:
        response = client.post("/transcribe", files={"audio": ("speech", b"not audio at all", "audio/webm")})
    assert response.status_code == 400


def test_root_redirects_to_ui():
    with TestClient(main.app) as client:
        response = client.get("/", follow_redirects=False)
    assert response.status_code in (302, 307)
    assert response.headers["location"] == "/ui"
