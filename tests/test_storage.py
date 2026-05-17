import importlib
import json

import pytest


@pytest.fixture(autouse=True)
def tmp_data(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import backend.storage as storage_mod

    importlib.reload(storage_mod)
    return tmp_path


def test_load_jobs_empty():
    from backend.storage import load_jobs

    assert load_jobs() == {"jobs": [], "timezone": "America/New_York"}


def test_save_and_load_jobs(tmp_path):
    from backend.storage import load_jobs, save_jobs

    data = {"jobs": [{"id": "1", "tool": "claude"}], "timezone": "America/New_York"}
    save_jobs(data)

    assert load_jobs()["jobs"][0]["id"] == "1"
    assert json.loads((tmp_path / "jobs.json").read_text()) == data


def test_load_expiry_empty():
    from backend.storage import load_expiry

    assert load_expiry() == {}


def test_save_and_load_expiry(tmp_path):
    from backend.storage import load_expiry, save_expiry

    save_expiry("claude", "2026-05-15T01:20:00")
    save_expiry("codex", None)

    assert load_expiry() == {"claude": "2026-05-15T01:20:00", "codex": None}
    assert json.loads((tmp_path / "expiry.json").read_text()) == {
        "claude": "2026-05-15T01:20:00",
        "codex": None,
    }


def test_append_and_load_history():
    from backend.storage import append_history, load_history

    append_history(
        tool="claude",
        trigger_type="manual",
        job_id=None,
        scheduled_time=None,
        workspace="/tmp",
        status="started",
        error_message=None,
        estimated_end_time="2026-05-14T13:00:00",
        warmup_sent_at="2026-05-14T08:00:01",
        warmup_status="pending",
    )
    history = load_history()

    assert len(history) == 1
    assert history[0]["status"] == "started"
    assert history[0]["warmup_status"] == "pending"


def test_history_capped_at_100():
    from backend.storage import append_history, load_history

    for _ in range(110):
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

    assert len(load_history()) == 100
