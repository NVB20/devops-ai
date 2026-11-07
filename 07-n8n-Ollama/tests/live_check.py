"""Asks the real LLM and the real database the step 05 test questions and checks each answer's format.

Not a pytest file (it needs the network, the .env key and Postgres). Run from 05-Agents:
    venv\\Scripts\\python -m tests.live_check          all 8 questions (~25 LLM requests)
    venv\\Scripts\\python -m tests.live_check 7 8      only questions 7 and 8
"""
import re
import sys

from app import main

TROUBLESHOOT_PARTS = ["Likely cause:", "Check:", "Fix:", "Escalate if:"]

# (question, expected route, extra check or None)
QUESTIONS = [
    ("my pod keeps crashing", "troubleshooting", None),
    ("the disk is full on one of the servers", "troubleshooting", None),
    ("our SSL certificate expired", "troubleshooting", None),
    ("how do we deploy and roll back?", "knowledge", None),
    ("how do I rotate a secret?", "knowledge", None),
    ("what's the best pizza in town?", "other", None),
    ("something is broken", "troubleshooting", "clarify"),
    ("pods are pending and a node is NotReady", "troubleshooting", "both"),
]


def problems(result: dict, route: str, extra: str | None) -> list[str]:
    answer, found = result["answer"], []
    if result["route"] != route:
        found.append(f"route {result['route']}, expected {route}")
    if route == "other":
        return found
    if extra == "clarify":
        if result["searches"]:
            found.append("searched instead of asking")
        if answer.count("?") != 1:
            found.append("not exactly one clarifying question")
        return found
    if not re.search(r"\[[\w.-]+\.md\]", answer) or not result["sources"]:
        found.append("no runbook cited")
    if route == "troubleshooting":
        at = [answer.find(p) for p in TROUBLESHOOT_PARTS]
        if -1 in at or at != sorted(at):
            found.append("not Likely cause -> Check -> Fix -> Escalate if")
    if route == "knowledge" and "Steps:" not in answer:
        found.append("no Steps:")
    if extra == "both":
        missing = {"kubernetes-pod-pending.md", "kubernetes-node-notready.md"} - set(result["sources"])
        if missing:
            found.append(f"missing {', '.join(sorted(missing))}")
    return found


def main_(numbers: list[int]) -> int:
    picked = [QUESTIONS[n - 1] for n in numbers] or QUESTIONS
    failed = 0
    for question, route, extra in picked:
        try:
            result = main.graph.invoke({"question": question})
        except Exception as e:  # e.g. the free tier's daily limit: report it and go on
            failed += 1
            print("=" * 100)
            print(f"FAIL  {question}\n      !! {type(e).__name__}: {str(e)[:200]}")
            continue
        found = problems(result, route, extra)
        failed += bool(found)
        print("=" * 100)
        print(f"{'FAIL' if found else 'ok  '}  {question}  ->  {result['route']}  ({result['model']})")
        for s in result["searches"]:
            print(f"      search: {s['query']!r} -> {', '.join(sorted({c['source'] for c in s['chunks']})) or 'nothing'}")
        print(f"      sources: {result['sources']}")
        for p in found:
            print(f"      !! {p}")
        print(result["answer"])
    print("=" * 100)
    print(f"{len(picked) - failed}/{len(picked)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main_([int(n) for n in sys.argv[1:]]))
