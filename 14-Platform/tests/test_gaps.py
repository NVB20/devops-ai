"""Unanswered questions: saved only when no runbook matched, never at the cost of the answer, listed by /gaps.
The fake LLM and search come from test_stream. The last test needs Postgres and is skipped without it."""
import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import main
from app.ingest import SCHEMA
from tests.test_stream import fake_llm, fake_search


def ask(path: str, question: str):
    with TestClient(main.app) as client:
        return client.post(path, json={"message": question})


def test_only_unanswered_questions_are_saved(monkeypatch):
    saved = []
    monkeypatch.setattr(main, "save_unanswered", lambda question, route: saved.append((question, route)))
    monkeypatch.setattr(main, "search", fake_search)

    monkeypatch.setattr(main, "client", fake_llm("troubleshooting", [["pods pending"], "describe it [pod-pending.md]"]))
    ask("/chat", "pods are pending")
    monkeypatch.setattr(main, "client", fake_llm("troubleshooting", ["CLARIFY: Which service?"]))
    ask("/chat", "something is broken")
    monkeypatch.setattr(main, "client", fake_llm("other", []))
    ask("/chat", "best pizza in town?")
    monkeypatch.setattr(main, "client", fake_llm("knowledge", [["nothing like this"], "I couldn't find it in the runbooks."]))
    ask("/chat", "how do we bake bread?")
    monkeypatch.setattr(main, "client", fake_llm("knowledge", [["nothing like this"], "I couldn't find it in the runbooks."]))
    ask("/chat/stream", "  how do we bake bread?  ")

    # Answered, clarify and off-topic aren't gaps; the stream endpoint saves too
    assert saved == [("how do we bake bread?", "knowledge"), ("  how do we bake bread?  ", "knowledge")]


def test_a_database_error_never_breaks_the_answer(monkeypatch):
    def db_down(question, route):
        raise psycopg.OperationalError("connection refused")

    monkeypatch.setattr(main, "save_unanswered", db_down)
    monkeypatch.setattr(main, "search", fake_search)
    monkeypatch.setattr(main, "client", fake_llm("knowledge", [["nothing like this"], "I couldn't find it in the runbooks."]))

    response = ask("/chat", "how do we bake bread?")
    assert response.status_code == 200
    assert response.json()["sources"] == []


def test_gaps_endpoint(monkeypatch):
    asked = []
    gaps = [{"question": "how do we bake bread?", "times": 3, "last_asked": "2026-11-08T01:30:00+00:00", "route": "knowledge"}]
    monkeypatch.setattr(main, "unanswered_gaps", lambda limit: asked.append(limit) or gaps)

    with TestClient(main.app) as client:
        assert client.get("/gaps").json() == gaps
        client.get("/gaps", params={"limit": 100000})
    assert asked == [50, 500]  # default, and capped


def test_gaps_endpoint_when_the_database_is_down(monkeypatch):
    monkeypatch.setattr(main, "DATABASE_URL", "postgresql://devops:devops@db.invalid/knowledge")
    with TestClient(main.app) as client:
        response = client.get("/gaps")
    assert response.status_code == 503


@pytest.mark.real_db
def test_gaps_groups_the_same_question_on_real_postgres():
    marker = uuid.uuid4().hex[:8]  # only this test's rows, so a real list in the database is left alone
    try:
        with psycopg.connect(main.DATABASE_URL, connect_timeout=3) as conn:
            conn.execute(SCHEMA)
    except psycopg.Error as e:
        pytest.skip(f"Postgres not reachable, start it with docker compose up -d db: {e}")
    try:
        for question in [f"Kafka lag {marker}", f"  kafka LAG {marker} ", f"vault sealed {marker}"]:
            main.save_unanswered(question, "troubleshooting")
        mine = [g for g in main.unanswered_gaps(500) if marker in g["question"]]
        assert [(g["question"].strip().lower(), g["times"]) for g in mine] == [
            (f"kafka lag {marker}", 2), (f"vault sealed {marker}", 1)]
    finally:
        with psycopg.connect(main.DATABASE_URL) as conn:
            conn.execute("DELETE FROM unanswered_questions WHERE question LIKE %s", (f"%{marker}%",))
