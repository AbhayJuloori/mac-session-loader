from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Optional

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.date import DateTrigger
except ImportError:
    class _FallbackJob:
        def __init__(self, func, trigger, args, job_id):
            self.func = func
            self.trigger = trigger
            self.args = tuple(args)
            self.id = job_id
            self.next_run_time = getattr(trigger, "run_date", None)

    class BackgroundScheduler:
        def __init__(self):
            self.running = False
            self._jobs = {}

        def start(self):
            self.running = True

        def shutdown(self, wait=True):
            del wait
            self.running = False

        def add_job(self, func, trigger, args, id, replace_existing=True):
            del replace_existing
            self._jobs[id] = _FallbackJob(func, trigger, args, id)

        def get_job(self, job_id):
            return self._jobs.get(job_id)

        def remove_job(self, job_id):
            self._jobs.pop(job_id, None)

    class CronTrigger:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.run_date = None

    class DateTrigger:
        def __init__(self, run_date, timezone):
            del timezone
            self.run_date = run_date

from backend.session import get_session_activity_time, is_running, kill_session, send_prompt_async, start_session
from backend.storage import append_history, load_jobs, save_expiry, save_jobs


scheduler = BackgroundScheduler()
TOOLS = ("claude", "codex")
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
CLEANUP_JOB_ID = "session-cleanup"
DEFAULT_WARMUP = "Reply READY only."
DEFAULT_WORKSPACE = os.getenv("DEFAULT_WORKSPACE", "/Users/abhayjuloori/")
DEFAULT_TIMEZONE = os.getenv("DEFAULT_TIMEZONE", "America/New_York")

_COMMANDS = {
    "claude": os.getenv("CLAUDE_COMMAND", "claude"),
    "codex": os.getenv("CODEX_COMMAND", "codex"),
}


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _idle_timeout_hours() -> float:
    return _float_env("SESSION_IDLE_TIMEOUT_HOURS", 6.0)


def _cleanup_interval_minutes() -> int:
    return _int_env("SESSION_CLEANUP_INTERVAL_MINUTES", 10)


def _run_job(job_id: str, tool: str, workspace: str, warmup_prompt: str) -> None:
    session_name = f"{tool}-session"
    estimated_end = (datetime.utcnow() + timedelta(hours=5)).isoformat()

    warmup_status = None
    warmup_sent_at = None
    try:
        if is_running(session_name):
            send_prompt_async(
                name=session_name,
                prompt=warmup_prompt,
            )
            status = "warmed_existing"
        else:
            start_session(
                name=session_name,
                command=_COMMANDS[tool],
                workspace=workspace,
                warmup_prompt=warmup_prompt,
                is_claude=(tool == "claude"),
            )
            status = "started"
        error = None
        warmup_status = "pending"
        warmup_sent_at = datetime.now().isoformat()
        save_expiry(tool, estimated_end)
    except Exception as exc:
        status = "failed"
        error = str(exc)
        warmup_status = "failed"

    append_history(
        tool=tool,
        trigger_type="scheduled",
        job_id=job_id,
        scheduled_time=None,
        workspace=workspace,
        status=status,
        error_message=error,
        estimated_end_time=estimated_end,
        warmup_sent_at=warmup_sent_at,
        warmup_status=warmup_status,
    )
    _disable_once_job_if_needed(job_id)


def _disable_once_job_if_needed(job_id: str) -> None:
    data = load_jobs()
    changed = False
    for job in data.get("jobs", []):
        if job.get("id") == job_id and job.get("trigger") == "once":
            job["enabled"] = False
            job["completed_at"] = datetime.now().isoformat()
            job["updated_at"] = datetime.now().isoformat()
            changed = True
            break
    if changed:
        save_jobs(data)


def cleanup_idle_sessions(now: Optional[datetime] = None) -> list[str]:
    timeout_hours = _idle_timeout_hours()
    if timeout_hours <= 0:
        return []

    cutoff = (now or datetime.now()) - timedelta(hours=timeout_hours)
    closed = []
    for tool in TOOLS:
        session_name = f"{tool}-session"
        activity_time = get_session_activity_time(session_name)
        if activity_time is None or activity_time > cutoff:
            continue
        if kill_session(session_name):
            save_expiry(tool, None)
            closed.append(session_name)
    return closed


def register_cleanup_job() -> None:
    timeout_hours = _idle_timeout_hours()
    interval_minutes = _cleanup_interval_minutes()
    if timeout_hours <= 0 or interval_minutes <= 0:
        unregister_job(CLEANUP_JOB_ID)
        return
    scheduler.add_job(
        cleanup_idle_sessions,
        trigger=CronTrigger(minute=f"*/{interval_minutes}", timezone=DEFAULT_TIMEZONE),
        args=[],
        id=CLEANUP_JOB_ID,
        replace_existing=True,
    )


def register_job(job: dict) -> None:
    unregister_job(job["id"])
    if not job.get("enabled", True):
        return

    hour, minute = [int(part) for part in job["time"].split(":")]
    timezone = job.get("timezone", DEFAULT_TIMEZONE)
    if job["trigger"] == "once":
        trigger = DateTrigger(
            run_date=datetime.fromisoformat(f"{job['date']}T{job['time']}:00"),
            timezone=timezone,
        )
    elif job["trigger"] == "daily":
        trigger = CronTrigger(hour=hour, minute=minute, timezone=timezone)
    elif job["trigger"] == "weekly":
        trigger = CronTrigger(
            day_of_week=",".join(DAYS[day] for day in job["days"]),
            hour=hour,
            minute=minute,
            timezone=timezone,
        )
    else:
        raise ValueError(f"Unknown trigger: {job['trigger']}")

    scheduler.add_job(
        _run_job,
        trigger=trigger,
        args=[
            job["id"],
            job["tool"],
            job.get("workspace") or DEFAULT_WORKSPACE,
            job.get("warmup_prompt") or DEFAULT_WARMUP,
        ],
        id=job["id"],
        replace_existing=True,
    )


def unregister_job(job_id: str) -> None:
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)


def init_scheduler() -> None:
    if not scheduler.running:
        scheduler.start()
    register_cleanup_job()
    for job in load_jobs().get("jobs", []):
        register_job(job)


def get_next_run(job_id: str) -> Optional[str]:
    job = scheduler.get_job(job_id)
    next_run_time = getattr(job, "next_run_time", None)
    if not next_run_time:
        return None
    try:
        return next_run_time.strftime("%-I:%M %p %Z")
    except ValueError:
        return next_run_time.strftime("%I:%M %p %Z").lstrip("0")
