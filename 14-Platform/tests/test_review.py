"""Step 14: the review node checks each answer against the runbook excerpts the agent found, and gives a failed
answer one rewrite with the reviewer's notes. Fake LLM and database from test_stream (no network, no Postgres)."""
import json

from fastapi.testclient import TestClient

from app import main
from tests.test_stream import fake_llm, fake_search, stream

ANSWER = "Likely cause: no room [pod-pending.md]. Fix: kubectl delete node --all [pod-pending.md]"
FIXED = "Likely cause: no room [pod-pending.md]. Fix: describe the pod [pod-pending.md]"
UNSUPPORTED = json.dumps({"supported": False, "unsupported": ["kubectl delete node --all"]})


def ask(question="pods are pending"):
    with TestClient(main.app) as client:
        return client.post("/chat", json={"message": question}).json()


def test_a_supported_answer_passes(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "client", fake_llm("troubleshooting", [["pods pending"], ANSWER], calls=calls))
    monkeypatch.setattr(main, "search", fake_search)

    body = ask()

    assert body["answer"] == ANSWER and body["review"] == {"status": "passed", "issues": []}
    review = [c for c in calls if isinstance(c, tuple)]
    assert len(review) == 1 and review[0][0] == "review"
    # The reviewer sees the excerpt the search returned and the answer
    assert "[pod-pending.md]\ndescribe the pod" in review[0][1] and ANSWER in review[0][1]


def test_an_unsupported_answer_is_rewritten_once(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "client", fake_llm("troubleshooting", [["pods pending"], ANSWER],
                                                 reviews=[UNSUPPORTED], rewrites=[FIXED], calls=calls))
    monkeypatch.setattr(main, "search", fake_search)

    body = ask()

    assert body["answer"] == FIXED
    assert body["review"] == {"status": "revised", "issues": []}
    assert body["sources"] == ["pod-pending.md"]
    assert [c if isinstance(c, str) else c[0] for c in calls] == ["classify", "agent", "agent", "review", "rewrite", "review"]
    # The rewrite gets the reviewer's notes and the excerpts, and no tools
    rewrite = next(c[1] for c in calls if isinstance(c, tuple) and c[0] == "rewrite")
    assert "- kubectl delete node --all" in rewrite and "[pod-pending.md]\ndescribe the pod" in rewrite


def test_a_rewrite_that_still_fails_is_flagged(monkeypatch):
    monkeypatch.setattr(main, "client", fake_llm("troubleshooting", [["pods pending"], ANSWER],
                                                 reviews=[UNSUPPORTED, UNSUPPORTED], rewrites=[ANSWER]))
    monkeypatch.setattr(main, "search", fake_search)

    body = ask()

    # Only one rewrite: the answer goes out with what the runbooks don't support
    assert body["answer"] == ANSWER
    assert body["review"] == {"status": "flagged", "issues": ["kubectl delete node --all"]}


def test_nothing_to_review(monkeypatch):
    """A clarifying question, and an answer that cites no runbook, aren't reviewed."""
    monkeypatch.setattr(main, "search", fake_search)
    for route, turns in [("troubleshooting", ["CLARIFY: Which service?"]),
                         ("knowledge", [["nothing like this"], "I couldn't find it in the runbooks."])]:
        calls = []
        monkeypatch.setattr(main, "client", fake_llm(route, turns, calls=calls))
        assert ask("?")["review"] == {"status": "skipped", "issues": []}
        assert not any(isinstance(c, tuple) for c in calls)


def test_an_unreadable_verdict_does_not_block_the_answer(monkeypatch):
    monkeypatch.setattr(main, "client", fake_llm("troubleshooting", [["pods pending"], ANSWER], reviews=["Looks good to me!"]))
    monkeypatch.setattr(main, "search", fake_search)

    body = ask()

    assert body["answer"] == ANSWER and body["review"] == {"status": "unchecked", "issues": []}


def test_review_replies():
    assert main.review_reply('{"supported": true}') == {"supported": True, "issues": []}
    # Models wrap the JSON in text or code fences
    assert main.review_reply('Sure:\n```json\n{"supported": false, "unsupported": ["rm -rf /"]}\n```') == {
        "supported": False, "issues": ["rm -rf /"]}
    # "Not supported" with nothing listed gives the agent nothing to fix
    assert main.review_reply('{"supported": false, "unsupported": []}') == {"supported": True, "issues": []}
    assert main.review_reply('{"supported": false, "unsupported": ["a", "b", "c", "d", "e", "f"]}')["issues"] == ["a", "b", "c", "d", "e"]
    assert main.review_reply("no json here") is None
    assert main.review_reply('{"supported": "yes"}') is None


def test_the_stream_reports_the_review(monkeypatch):
    monkeypatch.setattr(main, "client", fake_llm("troubleshooting", [["pods pending"], ANSWER],
                                                 reviews=[UNSUPPORTED], rewrites=[FIXED]))
    monkeypatch.setattr(main, "search", fake_search)

    events = stream("pods are pending")

    steps = [(e["node"], e.get("review", {}).get("status")) for e in events if e["type"] == "step"]
    assert steps == [("classify", None), ("troubleshoot", None), ("review", "retry"), ("revise", None), ("review", "revised")]
    assert events[-1]["type"] == "done" and events[-1]["answer"] == FIXED and events[-1]["review"]["status"] == "revised"
