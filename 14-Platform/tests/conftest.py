import pytest

from app import main


@pytest.fixture(autouse=True)
def no_real_unanswered_rows(request, monkeypatch):
    """Tests ask questions no runbook answers: don't write them into a real database's /gaps list.
    Tests marked real_db use the real save on purpose (and clean up after themselves)."""
    if not request.node.get_closest_marker("real_db"):
        monkeypatch.setattr(main, "save_unanswered", lambda question, route: None)


def pytest_configure(config):
    config.addinivalue_line("markers", "real_db: uses the real Postgres, skipped when it isn't reachable")
