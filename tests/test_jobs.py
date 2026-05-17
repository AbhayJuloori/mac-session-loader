import importlib
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


HEADERS = {"x-api-key": "test-key"}
DAILY_JOB = {
    "tool": "claude",
    "trigger": "daily",
    "time": "08:00",
    "timezone": "America/New_York",
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SESSION_LOADER_KEY", "test-key")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DEFAULT_WORKSPACE", "/tmp")
    import backend.main as main_mod

    importlib.reload(main_mod)
    return TestClient(main_mod.app)


def test_create_daily_job(client):
    with patch("backend.routers.jobs.register_job"):
        response = client.post("/jobs", json=DAILY_JOB, headers=HEADERS)

    assert response.status_code == 200
    data = response.json()
    assert data["tool"] == "claude"
    assert data["trigger"] == "daily"
    assert data["enabled"] is True
    assert data["warmup_prompt"] == "Reply READY only."
    assert "id" in data


def test_create_weekly_job(client):
    with patch("backend.routers.jobs.register_job"):
        response = client.post(
            "/jobs",
            json={**DAILY_JOB, "trigger": "weekly", "days": [0, 2, 4]},
            headers=HEADERS,
        )

    assert response.status_code == 200
    assert response.json()["days"] == [0, 2, 4]


def test_create_once_job(client):
    with patch("backend.routers.jobs.register_job"):
        response = client.post(
            "/jobs",
            json={**DAILY_JOB, "trigger": "once", "date": "2026-12-01"},
            headers=HEADERS,
        )

    assert response.status_code == 200
    assert response.json()["date"] == "2026-12-01"


def test_get_jobs_empty(client):
    response = client.get("/jobs", headers=HEADERS)

    assert response.status_code == 200
    assert response.json() == []


def test_delete_job(client):
    with patch("backend.routers.jobs.register_job"), patch("backend.routers.jobs.unregister_job"):
        job_id = client.post("/jobs", json=DAILY_JOB, headers=HEADERS).json()["id"]
        response = client.delete(f"/jobs/{job_id}", headers=HEADERS)

    assert response.status_code == 200
    assert client.get("/jobs", headers=HEADERS).json() == []


def test_enable_disable_job(client):
    with patch("backend.routers.jobs.register_job"), patch("backend.routers.jobs.unregister_job"):
        job_id = client.post("/jobs", json=DAILY_JOB, headers=HEADERS).json()["id"]
        disabled = client.patch(f"/jobs/{job_id}/disable", headers=HEADERS)
        enabled = client.patch(f"/jobs/{job_id}/enable", headers=HEADERS)

    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False
    assert enabled.status_code == 200
    assert enabled.json()["enabled"] is True


def test_edit_job_time(client):
    with patch("backend.routers.jobs.register_job"), patch("backend.routers.jobs.unregister_job"):
        job_id = client.post("/jobs", json=DAILY_JOB, headers=HEADERS).json()["id"]
        response = client.put(f"/jobs/{job_id}", json={"time": "09:30"}, headers=HEADERS)

    assert response.status_code == 200
    assert response.json()["time"] == "09:30"


def test_create_missing_date_for_once(client):
    with patch("backend.routers.jobs.register_job"):
        response = client.post(
            "/jobs",
            json={**DAILY_JOB, "trigger": "once"},
            headers=HEADERS,
        )

    assert response.status_code == 400


def test_create_once_past_date_rejected(client):
    with patch("backend.routers.jobs.register_job"):
        response = client.post(
            "/jobs",
            json={**DAILY_JOB, "trigger": "once", "date": "2020-01-01"},
            headers=HEADERS,
        )

    assert response.status_code == 400
    assert "future" in response.json()["detail"].lower()


def test_edit_daily_to_weekly_without_days_rejected(client):
    with patch("backend.routers.jobs.register_job"), patch("backend.routers.jobs.unregister_job"):
        job_id = client.post("/jobs", json=DAILY_JOB, headers=HEADERS).json()["id"]
        response = client.put(f"/jobs/{job_id}", json={"trigger": "weekly"}, headers=HEADERS)

    assert response.status_code == 400
    assert "days" in response.json()["detail"].lower()
