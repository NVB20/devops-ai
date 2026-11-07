"""Checks that ingest refuses to run without runbooks, before it touches the database (no Postgres needed)."""
import pytest

from app import ingest


def test_ingest_without_runbooks_exits_before_touching_the_database(monkeypatch, tmp_path):
    monkeypatch.setattr(ingest, "KB_DIR", tmp_path)  # an empty folder
    monkeypatch.setattr(ingest.psycopg, "connect", lambda *a, **k: pytest.fail("ingest connected to the database"))

    with pytest.raises(SystemExit, match="No runbooks"):
        ingest.main()
