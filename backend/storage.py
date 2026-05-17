from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4


DEFAULT_JOBS: dict = {"jobs": [], "timezone": "America/New_York"}
_jobs_lock = threading.Lock()
_history_lock = threading.Lock()
_expiry_lock = threading.Lock()


def _base() -> Path:
    return Path(os.getenv("DATA_DIR", "."))


def _jobs_file() -> Path:
    return _base() / "jobs.json"


def _history_file() -> Path:
    return _base() / "history.json"


def _expiry_file() -> Path:
    return _base() / "expiry.json"


def _default_jobs() -> dict:
    return {"jobs": [], "timezone": DEFAULT_JOBS["timezone"]}


def _read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return default


def _atomic_write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, path)


def load_jobs() -> dict:
    with _jobs_lock:
        data = _read_json(_jobs_file(), _default_jobs())
        if not isinstance(data, dict):
            return _default_jobs()
        data.setdefault("jobs", [])
        data.setdefault("timezone", DEFAULT_JOBS["timezone"])
        return data


def save_jobs(data: dict) -> None:
    with _jobs_lock:
        _atomic_write_json(_jobs_file(), data)


def load_expiry() -> dict:
    with _expiry_lock:
        data = _read_json(_expiry_file(), {})
        return data if isinstance(data, dict) else {}


def save_expiry(tool: str, iso_str_or_null: Optional[str]) -> None:
    with _expiry_lock:
        data = _read_json(_expiry_file(), {})
        if not isinstance(data, dict):
            data = {}
        data[tool] = iso_str_or_null
        _atomic_write_json(_expiry_file(), data)


def load_history() -> list[dict]:
    with _history_lock:
        data = _read_json(_history_file(), [])
        return data if isinstance(data, list) else []


def append_history(
    *,
    tool: str,
    trigger_type: str,
    job_id: Optional[str],
    scheduled_time: Optional[str],
    workspace: str,
    status: str,
    error_message: Optional[str],
    estimated_end_time: str,
    warmup_sent_at: Optional[str] = None,
    warmup_status: Optional[str] = None,
) -> dict:
    with _history_lock:
        history = _read_json(_history_file(), [])
        if not isinstance(history, list):
            history = []
        entry = {
            "id": str(uuid4()),
            "tool": tool,
            "trigger_type": trigger_type,
            "job_id": job_id,
            "scheduled_time": scheduled_time,
            "actual_start_time": datetime.now().isoformat(),
            "workspace": workspace,
            "status": status,
            "error_message": error_message,
            "estimated_end_time": estimated_end_time,
        }
        if warmup_sent_at is not None:
            entry["warmup_sent_at"] = warmup_sent_at
        if warmup_status is not None:
            entry["warmup_status"] = warmup_status
        history.append(entry)
        _atomic_write_json(_history_file(), history[-100:])
        return entry
