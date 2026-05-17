import importlib
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SESSION_LOADER_KEY", "test-key")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DEFAULT_WORKSPACE", "/tmp")
    import backend.main as main_mod

    importlib.reload(main_mod)
    return TestClient(main_mod.app)


def test_run_starts_new_session(client):
    with patch("backend.routers.run.is_running", return_value=False), \
        patch("backend.routers.run.start_session") as mock_start, \
        patch("backend.routers.run.start_ttyd_if_available") as mock_ttyd, \
        patch("backend.routers.run.asyncio.sleep", new_callable=AsyncMock) as mock_sleep, \
        patch("backend.routers.run.append_history") as mock_history:
        response = client.post("/run/claude", headers={"x-api-key": "test-key"})

    assert response.status_code == 200
    assert response.json()["status"] == "started"
    mock_start.assert_called_once()
    mock_ttyd.assert_called_once_with("claude", 7681, "claude-session")
    mock_sleep.assert_awaited_once_with(1)
    mock_history.assert_called_once()
    assert mock_history.call_args.kwargs["warmup_status"] == "pending"


def test_run_skips_already_running(client):
    with patch("backend.routers.run.is_running", return_value=True), \
        patch("backend.routers.run.send_prompt_async") as mock_prompt, \
        patch("backend.routers.run.start_session") as mock_start, \
        patch("backend.routers.run.start_ttyd_if_available") as mock_ttyd, \
        patch("backend.routers.run.asyncio.sleep", new_callable=AsyncMock), \
        patch("backend.routers.run.append_history") as mock_history:
        response = client.post("/run/claude", headers={"x-api-key": "test-key"})

    assert response.status_code == 200
    assert response.json()["status"] == "warmed_existing"
    mock_prompt.assert_called_once_with(name="claude-session", prompt="Reply READY only.")
    mock_start.assert_not_called()
    mock_ttyd.assert_called_once_with("claude", 7681, "claude-session")
    mock_history.assert_called_once()
    assert mock_history.call_args.kwargs["status"] == "warmed_existing"
    assert mock_history.call_args.kwargs["warmup_status"] == "pending"


def test_run_unknown_tool(client):
    response = client.post("/run/unknown", headers={"x-api-key": "test-key"})

    assert response.status_code == 400


def test_run_requires_auth(client):
    response = client.post("/run/claude")

    assert response.status_code == 401
