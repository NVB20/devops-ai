"""Checks that /health reports the database. The "down" test makes a real connection attempt to a host that cannot exist, so no Postgres is needed."""
from fastapi.testclient import TestClient

from app import main


def test_health_reports_the_database_is_up(monkeypatch):
    monkeypatch.setattr(main, "chunk_count", lambda: 177)

    with TestClient(main.app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "database": "up", "chunks": 177,
                               "llm": {"provider": main.PROVIDER, "model": main.MODEL}, "runtime": main.RUNTIME}


def test_runtime_detection(monkeypatch):
    for name in ("KUBERNETES_SERVICE_HOST", "APP_RUNTIME", "POD_NAME", "POD_NAMESPACE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(main.os.path, "exists", lambda path: False)
    assert main.detect_runtime()["kind"] == "local"

    monkeypatch.setattr(main.os.path, "exists", lambda path: path == "/.dockerenv")
    assert main.detect_runtime()["kind"] == "docker"

    # Kubernetes wins over /.dockerenv; APP_RUNTIME only changes the label
    monkeypatch.setenv("KUBERNETES_SERVICE_HOST", "10.96.0.1")
    monkeypatch.setenv("APP_RUNTIME", "kind")
    monkeypatch.setenv("POD_NAMESPACE", "devops-ai")
    monkeypatch.setenv("POD_NAME", "devops-ai-abc")
    rt = main.detect_runtime()
    assert (rt["kind"], rt["label"], rt["pod"]) == ("kubernetes", "kind", "devops-ai/devops-ai-abc")


def test_health_reports_the_database_is_down(monkeypatch):
    # .invalid never resolves (RFC 6761): psycopg fails at once, as in Docker when the db container is gone
    monkeypatch.setattr(main, "DATABASE_URL", "postgresql://devops:devops@db.invalid/knowledge")

    with TestClient(main.app) as client:
        response = client.get("/health")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unhealthy" and body["database"] == "down"
    assert "db.invalid" in body["detail"]  # psycopg's message names the server it couldn't reach
