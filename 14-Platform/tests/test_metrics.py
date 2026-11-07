"""Checks /metrics: what each kind of question adds, with the fake LLM and database from test_stream (no network, no Postgres)."""
import psycopg
from fastapi.testclient import TestClient
from prometheus_client.parser import text_string_to_metric_families

from app import main
from tests.test_stream import fake_llm, fake_search


def scrape() -> dict:
    """The current samples, as {(name, frozenset(labels)): value}."""
    with TestClient(main.app) as client:
        response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    return {(s.name, frozenset(s.labels.items())): s.value
            for family in text_string_to_metric_families(response.text) for s in family.samples}


def delta(before: dict, after: dict, name: str, **labels) -> float:
    key = (name, frozenset(labels.items()))
    return after.get(key, 0) - before.get(key, 0)


def ask(path: str, question: str):
    with TestClient(main.app) as client:
        return client.post(path, json={"message": question})


def test_an_answered_question(monkeypatch):
    monkeypatch.setattr(main, "client", fake_llm("troubleshooting", [["pods pending"], "describe it [pod-pending.md]"]))
    monkeypatch.setattr(main, "search", fake_search)
    before = scrape()

    assert ask("/chat", "pods are pending").status_code == 200

    after = scrape()
    assert delta(before, after, "devops_ai_questions_total", endpoint="chat", route="troubleshooting", outcome="answered") == 1
    assert delta(before, after, "devops_ai_question_duration_seconds_count", endpoint="chat", route="troubleshooting") == 1
    assert delta(before, after, "devops_ai_searches_total", agent="troubleshoot") == 1
    # One classify call and two agent turns (search, then answer)
    assert delta(before, after, "devops_ai_llm_call_duration_seconds_count", provider=main.PROVIDER, kind="classify") == 1
    assert delta(before, after, "devops_ai_llm_call_duration_seconds_count", provider=main.PROVIDER, kind="agent") == 2
    # The best chunk had similarity 0.74: it lands in the 0.8 bucket, not the 0.7 one
    assert delta(before, after, "devops_ai_search_top_similarity_bucket", le="0.7") == 0
    assert delta(before, after, "devops_ai_search_top_similarity_bucket", le="0.8") == 1
    assert delta(before, after, "devops_ai_http_requests_total", method="POST", path="/chat", status="200") == 1


def test_stream_outcomes(monkeypatch):
    monkeypatch.setattr(main, "search", fake_search)
    before = scrape()

    monkeypatch.setattr(main, "client", fake_llm("other", []))
    ask("/chat/stream", "best pizza in town?")
    monkeypatch.setattr(main, "client", fake_llm("troubleshooting", ["CLARIFY: Which service?"]))
    ask("/chat/stream", "something is broken")
    monkeypatch.setattr(main, "client", fake_llm("knowledge", [["nothing like this"], "I couldn't find it in the runbooks."]))
    ask("/chat/stream", "how do we bake bread?")

    after = scrape()
    assert delta(before, after, "devops_ai_questions_total", endpoint="stream", route="other", outcome="off_topic") == 1
    assert delta(before, after, "devops_ai_questions_total", endpoint="stream", route="troubleshooting", outcome="clarify") == 1
    assert delta(before, after, "devops_ai_questions_total", endpoint="stream", route="knowledge", outcome="no_answer") == 1
    # A search that found nothing counts as similarity 0
    assert delta(before, after, "devops_ai_search_top_similarity_bucket", le="0.0") == 1


def test_errors_are_counted(monkeypatch):
    def db_down(query):
        raise psycopg.OperationalError("connection refused")

    monkeypatch.setattr(main, "client", fake_llm("troubleshooting", [["pods pending"]]))
    monkeypatch.setattr(main, "search", db_down)
    before = scrape()

    assert ask("/chat", "pods are pending").status_code == 503

    after = scrape()
    assert delta(before, after, "devops_ai_questions_total", endpoint="chat", route="unknown", outcome="error") == 1
    assert delta(before, after, "devops_ai_http_requests_total", method="POST", path="/chat", status="503") == 1


def test_the_search_url_is_one_series(monkeypatch):
    """/search?q=... must count under /search, not one series per question."""
    monkeypatch.setattr(main, "search", fake_search)
    before = scrape()

    with TestClient(main.app) as client:
        client.get("/search", params={"q": "pods pending"})
        client.get("/search", params={"q": "node NotReady"})

    after = scrape()
    assert delta(before, after, "devops_ai_http_requests_total", method="GET", path="/search", status="200") == 2
    assert not any(name == "devops_ai_http_requests_total" and "q=" in dict(labels)["path"] for name, labels in after)


def test_health_sets_the_chunk_gauge(monkeypatch):
    monkeypatch.setattr(main, "chunk_count", lambda: 177)
    with TestClient(main.app) as client:
        client.get("/health")
    assert scrape()[("devops_ai_kb_chunks", frozenset())] == 177
