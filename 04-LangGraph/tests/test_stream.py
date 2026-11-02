"""Checks the /chat/stream event sequence with a fake LLM and a fake database (no network, no Postgres)."""
import json
from types import SimpleNamespace

import psycopg
import pytest
from fastapi.testclient import TestClient
from faster_whisper import decode_audio

from app import main

CHUNKS = [
    {"source": "a.md", "text": "step one", "similarity": 0.71},
    {"source": "b.md", "text": "step two", "similarity": 0.42},
]


def piece(content=None, reasoning=None):
    """One streamed piece of a reply, shaped like the OpenAI SDK's ChatCompletionChunk."""
    delta = SimpleNamespace(content=content, reasoning=reasoning)
    return SimpleNamespace(model="fake-model", choices=[SimpleNamespace(delta=delta)])


def fake_llm(route):
    """An OpenAI-like client: answers the classify prompt with `route`; the answer call streams
    a thought, then a padded answer a few characters at a time."""
    def create(model, messages, **kwargs):
        if messages[0]["content"] == main.CLASSIFY_PROMPT:
            return SimpleNamespace(model="fake-model", choices=[SimpleNamespace(message=SimpleNamespace(content=route))])
        assert kwargs["stream"] is True
        return iter([piece(reasoning="Use a.md."), piece("\n\n1. do"), piece(" it"), piece(" [a.md]\n")])
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def stream(question):
    with TestClient(main.app) as client:
        response = client.post("/chat/stream", json={"message": question})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    return [json.loads(block.removeprefix("data: ")) for block in response.text.split("\n\n") if block]


def without_text(events):
    """The node events, without the streamed answer text."""
    return [e for e in events if e["type"] not in ("token", "reasoning")]


@pytest.mark.parametrize(
    "route, answer_node",
    [("troubleshooting", "troubleshoot"), ("knowledge", "knowledge"), ("other", "off_topic")],
)
def test_event_sequence(monkeypatch, route, answer_node):
    monkeypatch.setattr(main, "client", fake_llm(route))
    monkeypatch.setattr(main, "nearest_chunks", lambda vector, k=main.TOP_K: CHUNKS)

    events = without_text(stream("my pod keeps crashing"))

    nodes = ["classify"] + ([] if route == "other" else ["retrieve"]) + [answer_node]
    expected = [("start", None)]
    for node in nodes:
        expected += [("running", node), ("step", node)]
    expected.append(("done", None))
    assert [(e["type"], e.get("node")) for e in events] == expected

    steps = {e["node"]: e for e in events if e["type"] == "step"}
    assert all(isinstance(e["ms"], int) for e in steps.values())
    assert steps["classify"]["route"] == route

    done = events[-1]
    assert done["route"] == route
    if route == "other":
        assert done["answer"] == main.OFF_TOPIC_ANSWER
        assert done["sources"] == []
    else:
        retrieve = steps["retrieve"]
        assert retrieve["chunks"] == [{"source": "a.md", "similarity": 0.71}, {"source": "b.md", "similarity": 0.42}]
        assert isinstance(retrieve["embed_ms"], int) and isinstance(retrieve["search_ms"], int)
        assert steps[answer_node]["model"] == "fake-model"
        assert done["answer"] == "1. do it [a.md]"
        assert done["sources"] == ["a.md"]


def test_answer_streams_word_by_word(monkeypatch):
    monkeypatch.setattr(main, "client", fake_llm("knowledge"))
    monkeypatch.setattr(main, "nearest_chunks", lambda vector, k=main.TOP_K: CHUNKS)

    events = stream("how do we deploy?")

    tokens = [e for e in events if e["type"] == "token"]
    assert "".join(e["text"] for e in tokens) == "\n\n1. do it [a.md]\n"
    assert all(e["node"] == "knowledge" for e in tokens)
    assert [e["text"] for e in events if e["type"] == "reasoning"] == ["Use a.md."]
    # The text arrives while the answer node runs: after it starts, before its step event
    types = [(e["type"], e.get("node")) for e in events]
    assert types.index(("running", "knowledge")) < events.index(tokens[0]) < types.index(("step", "knowledge"))


def test_database_error_names_the_running_node(monkeypatch):
    def broken(vector, k=main.TOP_K):
        raise psycopg.OperationalError("connection refused")

    monkeypatch.setattr(main, "client", fake_llm("troubleshooting"))
    monkeypatch.setattr(main, "nearest_chunks", broken)

    events = stream("my pod keeps crashing")

    assert events[-1]["type"] == "error"
    assert events[-1]["node"] == "retrieve"
    assert events[-1]["part"] == "search"
    assert "connection refused" in events[-1]["detail"]


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
