import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SESSION_LOADER_KEY", "test-key")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import backend.main as main_mod

    importlib.reload(main_mod)
    return TestClient(main_mod.app)


def test_history_empty(client):
    response = client.get("/history", headers={"x-api-key": "test-key"})

    assert response.status_code == 200
    assert response.json() == []


def test_history_newest_first(client):
    from backend.storage import append_history

    append_history(
        tool="claude",
        trigger_type="manual",
        job_id=None,
        scheduled_time=None,
        workspace="/tmp",
        status="started",
        error_message=None,
        estimated_end_time="2026-05-14T13:00:00",
    )
    append_history(
        tool="codex",
        trigger_type="manual",
        job_id=None,
        scheduled_time=None,
        workspace="/tmp",
        status="started",
        error_message=None,
        estimated_end_time="2026-05-14T13:00:00",
    )

    response = client.get("/history", headers={"x-api-key": "test-key"})

    assert response.status_code == 200
    assert [entry["tool"] for entry in response.json()] == ["codex", "claude"]


def test_system_check_returns_deps(client):
    response = client.get("/system-check", headers={"x-api-key": "test-key"})

    assert response.status_code == 200
    assert "deps" in response.json()
    assert "warnings" in response.json()
