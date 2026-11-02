"""Known questions must find the right runbook. Uses the real embedding model and the real database, with no LLM.
Needs Postgres with the runbooks loaded (docker compose up -d); skipped when Postgres isn't reachable."""
import psycopg
import pytest
from fastapi.testclient import TestClient

from app import main
from app.ingest import KB_DIR

# (question, the runbook that must come back first). Worded the way an engineer asks, not like the runbook titles.
KNOWN = [
    ("the build pipeline fails on the test stage", "cicd-pipeline-failing.md"),
    ("I think an attacker got into one of our servers", "compromised-host-response.md"),
    ("trivy found critical CVEs in our docker image", "container-image-vulnerabilities.md"),
    ("how do I restore the database from last night's backup?", "database-backup-and-restore.md"),
    ("the app says too many connections to postgres", "database-connection-errors.md"),
    ("npm audit reports a vulnerable package", "dependency-vulnerabilities.md"),
    ("how do we roll back a bad release?", "deploy-and-rollback.md"),
    ("what security gates does our pipeline have?", "devsecops-pipeline-security-gates.md"),
    ("no space left on device", "disk-full.md"),
    ("pods can't resolve service names", "dns-resolution-failures.md"),
    ("my container exits right after it starts", "docker-container-restarting.md"),
    ("helm says another operation is in progress", "helm-upgrade-failed.md"),
    ("the server is slow and the CPU is at 100%", "high-cpu-memory.md"),
    ("who do I page for a sev1 outage?", "incident-escalation.md"),
    ("users get a 502 bad gateway", "ingress-502-504-errors.md"),
    ("my pod keeps crashing and restarting", "kubernetes-crashloopbackoff.md"),
    ("the pod can't pull its image", "kubernetes-imagepullbackoff.md"),
    ("traffic between two namespaces is blocked", "kubernetes-network-policies.md"),
    ("a node is NotReady", "kubernetes-node-notready.md"),
    ("pods are stuck pending", "kubernetes-pod-pending.md"),
    ("my pod is rejected because it runs as root", "kubernetes-pod-security.md"),
    ("kubectl says forbidden, I can't list pods", "kubernetes-rbac-access.md"),
    ("someone pushed an AWS key to github", "leaked-secret-response.md"),
    ("messages are piling up in the queue", "rabbitmq-queue-backlog.md"),
    ("redis OOM command not allowed", "redis-memory-and-connection-issues.md"),
    ("semgrep blocks my pull request", "sast-findings.md"),
    ("how do I rotate the database password?", "secret-rotation.md"),
    ("what services make up our platform?", "service-overview.md"),
    ("the browser says the certificate has expired", "ssl-certificate-expired.md"),
    ("terraform apply fails with error acquiring the state lock", "terraform-state-lock-and-drift.md"),
]


@pytest.fixture(scope="module", autouse=True)
def database():
    try:
        count = main.chunk_count()
    except psycopg.Error as e:
        pytest.skip(f"Postgres not reachable, start it with docker compose up -d: {e}")
    assert count, "the chunks table is empty: run python -m app.ingest"


@pytest.mark.parametrize("question, runbook", KNOWN)
def test_known_question_finds_its_runbook_first(question, runbook):
    found = [c["source"] for c in main.search(question)]
    assert found and found[0] == runbook, f"got {found}"


def test_every_runbook_has_a_known_question():
    # A new runbook needs a question here too
    assert {runbook for _, runbook in KNOWN} == {f.name for f in KB_DIR.glob("*.md")}


def test_question_about_two_problems_finds_both_runbooks():
    found = {c["source"] for c in main.search("pods are pending and a node is NotReady")}
    assert {"kubernetes-pod-pending.md", "kubernetes-node-notready.md"} <= found


@pytest.mark.parametrize("question", ["best pizza in town?", "what is the capital of France?"])
def test_off_topic_question_finds_nothing(question):
    assert main.search(question) == []


def test_health_with_the_real_database():
    with TestClient(main.app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["chunks"] > 0
