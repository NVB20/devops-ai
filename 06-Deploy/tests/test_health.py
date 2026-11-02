"""Checks that /health reports the database. The "down" test makes a real connection attempt to a host that cannot exist, so no Postgres is needed."""
from fastapi.testclient import TestClient

from app import main


def test_health_reports_the_database_is_up(monkeypatch):
    monkeypatch.setattr(main, "chunk_count", lambda: 177)

    with TestClient(main.app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "database": "up", "chunks": 177}


def test_health_reports_the_database_is_down(monkeypatch):
    # .invalid never resolves (RFC 6761): psycopg fails at once, as in Docker when the db container is gone
    monkeypatch.setattr(main, "DATABASE_URL", "postgresql://devops:devops@db.invalid/knowledge")

    with TestClient(main.app) as client:
        response = client.get("/health")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unhealthy" and body["database"] == "down"
    assert "db.invalid" in body["detail"]  # psycopg's message names the server it couldn't reach
