from backend.models import HistoryEntry, Job, JobCreate, JobUpdate, StatusResult


def test_job_defaults():
    job = Job(
        id="abc",
        tool="claude",
        trigger="daily",
        time="08:00",
        timezone="America/New_York",
        workspace="/Users/abhayjuloori/",
        warmup_prompt="Reply READY only.",
        enabled=True,
        created_at="2026-05-14T00:00:00",
        updated_at="2026-05-14T00:00:00",
    )

    assert job.enabled is True
    assert job.warmup_prompt == "Reply READY only."


def test_history_entry_warmup_fields_optional():
    entry = HistoryEntry(
        id="xyz",
        tool="claude",
        trigger_type="manual",
        actual_start_time="2026-05-14T08:00:00",
        workspace="/Users/abhayjuloori/",
        status="started",
        estimated_end_time="2026-05-14T13:00:00",
    )

    assert entry.status == "started"
    assert entry.error_message is None
    assert entry.warmup_sent_at is None
    assert entry.warmup_status is None


def test_history_entry_supports_warmed_existing_status():
    entry = HistoryEntry(
        id="xyz",
        tool="claude",
        trigger_type="scheduled",
        actual_start_time="2026-05-14T08:00:00",
        workspace="/Users/abhayjuloori/",
        status="warmed_existing",
        estimated_end_time="2026-05-14T13:00:00",
        warmup_status="pending",
    )

    assert entry.status == "warmed_existing"
    assert entry.warmup_status == "pending"


def test_create_update_and_status_models():
    assert JobCreate(tool="codex", trigger="daily", time="09:00").enabled is True
    assert JobUpdate(time="10:00").time == "10:00"
    assert StatusResult(running=False).started_at is None
    assert StatusResult(running=False).pids == []
