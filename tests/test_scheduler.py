import importlib
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest


@pytest.fixture
def fresh_scheduler():
    import backend.scheduler as sched_mod

    sched_mod = importlib.reload(sched_mod)
    yield sched_mod
    if sched_mod.scheduler.running:
        sched_mod.scheduler.shutdown(wait=False)


def test_register_daily_job(fresh_scheduler):
    sched = fresh_scheduler
    sched.scheduler.start()
    sched.register_job(
        {
            "id": "test-daily",
            "tool": "claude",
            "trigger": "daily",
            "time": "08:00",
            "timezone": "America/New_York",
            "enabled": True,
            "workspace": "/tmp",
            "warmup_prompt": "Reply READY only.",
        }
    )

    assert sched.scheduler.get_job("test-daily") is not None


def test_disabled_job_not_registered(fresh_scheduler):
    sched = fresh_scheduler
    sched.scheduler.start()
    sched.register_job(
        {
            "id": "test-disabled",
            "tool": "claude",
            "trigger": "daily",
            "time": "08:00",
            "timezone": "America/New_York",
            "enabled": False,
            "workspace": "/tmp",
            "warmup_prompt": "Reply READY only.",
        }
    )

    assert sched.scheduler.get_job("test-disabled") is None


def test_unregister_job(fresh_scheduler):
    sched = fresh_scheduler
    sched.scheduler.start()
    job = {
        "id": "test-unreg",
        "tool": "codex",
        "trigger": "daily",
        "time": "09:00",
        "timezone": "America/New_York",
        "enabled": True,
        "workspace": "/tmp",
        "warmup_prompt": "Reply READY only.",
    }
    sched.register_job(job)
    sched.unregister_job("test-unreg")

    assert sched.scheduler.get_job("test-unreg") is None


def test_once_job_marked_disabled_after_fire(fresh_scheduler, tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import backend.storage as storage_mod

    importlib.reload(storage_mod)
    sched = fresh_scheduler
    job = {
        "id": "test-once",
        "tool": "claude",
        "trigger": "once",
        "date": "2026-12-01",
        "time": "08:00",
        "timezone": "America/New_York",
        "enabled": True,
        "workspace": "/tmp",
        "warmup_prompt": "Reply READY only.",
    }
    storage_mod.save_jobs({"jobs": [job], "timezone": "America/New_York"})

    with patch("backend.scheduler.is_running", return_value=False), patch("backend.scheduler.start_session"):
        sched._run_job("test-once", "claude", "/tmp", "Reply READY only.")

    updated = storage_mod.load_jobs()["jobs"][0]
    assert updated["enabled"] is False
    assert "completed_at" in updated


def test_scheduled_job_warms_existing_session(fresh_scheduler):
    sched = fresh_scheduler

    with patch("backend.scheduler.is_running", return_value=True), \
        patch("backend.scheduler.send_prompt_async") as mock_prompt, \
        patch("backend.scheduler.start_session") as mock_start, \
        patch("backend.scheduler.append_history") as mock_history, \
        patch("backend.scheduler.save_expiry"):
        sched._run_job("job-1", "claude", "/tmp", "Start x process")

    mock_prompt.assert_called_once_with(
        name="claude-session",
        prompt="Start x process",
    )
    mock_start.assert_not_called()
    mock_history.assert_called_once()
    assert mock_history.call_args.kwargs["status"] == "warmed_existing"
    assert mock_history.call_args.kwargs["warmup_status"] == "pending"


def test_once_job_disabled_after_warming_existing_session(fresh_scheduler, tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import backend.storage as storage_mod

    importlib.reload(storage_mod)
    sched = fresh_scheduler
    job = {
        "id": "test-once-existing",
        "tool": "claude",
        "trigger": "once",
        "date": "2026-12-01",
        "time": "08:00",
        "timezone": "America/New_York",
        "enabled": True,
        "workspace": "/tmp",
        "warmup_prompt": "Start x process",
    }
    storage_mod.save_jobs({"jobs": [job], "timezone": "America/New_York"})

    with patch("backend.scheduler.is_running", return_value=True), \
        patch("backend.scheduler.send_prompt_async"), \
        patch("backend.scheduler.save_expiry"):
        sched._run_job("test-once-existing", "claude", "/tmp", "Start x process")

    updated = storage_mod.load_jobs()["jobs"][0]
    assert updated["enabled"] is False
    assert "completed_at" in updated


def test_cleanup_idle_sessions_closes_old_sessions(fresh_scheduler, monkeypatch):
    sched = fresh_scheduler
    now = datetime(2026, 5, 14, 12, 0, 0)

    monkeypatch.setenv("SESSION_IDLE_TIMEOUT_HOURS", "6")
    with patch("backend.scheduler.get_session_activity_time") as mock_activity, \
        patch("backend.scheduler.kill_session", return_value=True) as mock_kill, \
        patch("backend.scheduler.save_expiry") as mock_expiry:
        mock_activity.side_effect = [
            now - timedelta(hours=7),
            now - timedelta(minutes=30),
        ]

        closed = sched.cleanup_idle_sessions(now=now)

    assert closed == ["claude-session"]
    mock_kill.assert_called_once_with("claude-session")
    mock_expiry.assert_called_once_with("claude", None)


def test_cleanup_idle_sessions_disabled_by_env(fresh_scheduler, monkeypatch):
    sched = fresh_scheduler
    monkeypatch.setenv("SESSION_IDLE_TIMEOUT_HOURS", "0")

    with patch("backend.scheduler.get_session_activity_time") as mock_activity, \
        patch("backend.scheduler.kill_session") as mock_kill:
        assert sched.cleanup_idle_sessions(now=datetime(2026, 5, 14, 12, 0, 0)) == []

    mock_activity.assert_not_called()
    mock_kill.assert_not_called()


def test_register_cleanup_job_adds_periodic_job(fresh_scheduler, monkeypatch):
    sched = fresh_scheduler
    sched.scheduler.start()
    monkeypatch.setenv("SESSION_IDLE_TIMEOUT_HOURS", "6")
    monkeypatch.setenv("SESSION_CLEANUP_INTERVAL_MINUTES", "10")

    sched.register_cleanup_job()

    assert sched.scheduler.get_job(sched.CLEANUP_JOB_ID) is not None


def test_weekly_job_registered(fresh_scheduler):
    sched = fresh_scheduler
    sched.scheduler.start()
    sched.register_job(
        {
            "id": "test-weekly",
            "tool": "claude",
            "trigger": "weekly",
            "time": "07:30",
            "days": [0, 2, 4],
            "timezone": "America/New_York",
            "enabled": True,
            "workspace": "/tmp",
            "warmup_prompt": "Reply READY only.",
        }
    )

    assert sched.scheduler.get_job("test-weekly") is not None


def test_get_next_run_formats_scheduler_time(monkeypatch, fresh_scheduler):
    class FakeJob:
        next_run_time = datetime(2026, 5, 5, 14, 30, tzinfo=timezone.utc)

    class FakeScheduler:
        running = False

        def get_job(self, job_id):
            return FakeJob()

    monkeypatch.setattr(fresh_scheduler, "scheduler", FakeScheduler())

    assert fresh_scheduler.get_next_run("job-1") == "2:30 PM UTC"
