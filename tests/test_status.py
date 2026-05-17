import importlib
from subprocess import CompletedProcess
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SESSION_LOADER_KEY", "test-key")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import backend.main as main_mod

    importlib.reload(main_mod)
    return TestClient(main_mod.app)


def test_status_not_running(client):
    from backend.storage import save_expiry

    save_expiry("claude", "2026-05-15T01:20:00")

    with patch("backend.routers.status.is_running", return_value=False), \
        patch("backend.routers.status.get_claude_rate_limit_expiry", return_value=None), \
        patch("backend.routers.status.get_session_pids", return_value=[]), \
        patch("backend.routers.status.get_session_start_time", return_value=None):
        response = client.get("/status", headers={"x-api-key": "test-key"})

    assert response.status_code == 200
    data = response.json()
    assert data["claude"]["running"] is False
    assert data["claude"]["pids"] == []
    assert data["claude"]["started_at"] is None
    assert data["claude"]["estimated_ends_at"] is None
    assert data["claude"]["expires_at"] == "2026-05-15T01:20:00"


def test_status_running_has_no_estimated_end(client):
    started = "2026-05-14T19:07:00"
    with patch("backend.routers.status.is_running", return_value=True), \
        patch("backend.routers.status.get_claude_rate_limit_expiry", return_value=None), \
        patch("backend.routers.status.get_session_pids", return_value=[123, 456]), \
        patch("backend.routers.status.get_session_start_time", return_value=started):
        response = client.get("/status", headers={"x-api-key": "test-key"})

    assert response.status_code == 200
    data = response.json()
    assert data["claude"]["pids"] == [123, 456]
    assert data["claude"]["started_at"] == started
    assert data["claude"]["estimated_ends_at"] is None


def test_status_uses_claude_rate_limit_when_available(client):
    from backend.storage import save_expiry

    save_expiry("claude", "2026-05-15T01:20:00")
    rate_info = {
        "expires_at": "2026-05-15T05:10:00+00:00",
        "remaining_pct": 27,
        "used_pct": 73,
        "captured_at": "2026-05-15T01:11:36-04:00",
        "seven_day_resets_at": "2026-05-22T05:10:00+00:00",
        "seven_day_remaining_pct": 82,
    }

    with patch("backend.routers.status.is_running", return_value=False), \
        patch("backend.routers.status.get_claude_rate_limit_expiry", return_value=rate_info), \
        patch("backend.routers.status.get_session_pids", return_value=[]), \
        patch("backend.routers.status.get_session_start_time", return_value=None):
        response = client.get("/status", headers={"x-api-key": "test-key"})

    assert response.status_code == 200
    claude = response.json()["claude"]
    assert claude["expires_at"] == "2026-05-15T05:10:00+00:00"
    assert claude["remaining_pct"] == 27
    assert claude["used_pct"] == 73
    assert claude["captured_at"] == "2026-05-15T01:11:36-04:00"
    assert claude["seven_day_resets_at"] == "2026-05-22T05:10:00+00:00"
    assert claude["seven_day_remaining_pct"] == 82


def test_remote_status_uses_pgrep(client):
    with patch("backend.routers.status.subprocess.run") as mock_run:
        mock_run.return_value = CompletedProcess(["pgrep"], 0, stdout="123\n456\n")
        response = client.get("/remote-status", headers={"x-api-key": "test-key"})

    assert response.status_code == 200
    mock_run.assert_called_once_with(
        ["pgrep", "-f", "claude remote-control"],
        capture_output=True,
        text=True,
    )
    assert response.json()["claude_remote_control"] == {"running": True, "pids": ["123", "456"]}


def test_update_expiry_saves_value(client):
    from backend.storage import load_expiry

    response = client.post(
        "/expiry/claude",
        headers={"x-api-key": "test-key"},
        json={"expires_at": "2026-05-15T01:20:00"},
    )

    assert response.status_code == 200
    assert response.json() == {"tool": "claude", "expires_at": "2026-05-15T01:20:00"}
    assert load_expiry()["claude"] == "2026-05-15T01:20:00"


def test_update_expiry_clears_value(client):
    from backend.storage import load_expiry, save_expiry

    save_expiry("codex", "2026-05-15T01:20:00")

    response = client.post(
        "/expiry/codex",
        headers={"x-api-key": "test-key"},
        json={"expires_at": None},
    )

    assert response.status_code == 200
    assert response.json() == {"tool": "codex", "expires_at": None}
    assert load_expiry()["codex"] is None


def test_update_expiry_unknown_tool(client):
    response = client.post(
        "/expiry/unknown",
        headers={"x-api-key": "test-key"},
        json={"expires_at": "2026-05-15T01:20:00"},
    )

    assert response.status_code == 400


def test_update_expiry_requires_auth(client):
    response = client.post("/expiry/claude", json={"expires_at": None})

    assert response.status_code == 401
