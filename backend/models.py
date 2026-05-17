from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel


class JobCreate(BaseModel):
    tool: Literal["claude", "codex"]
    trigger: Literal["once", "daily", "weekly"]
    time: str
    date: Optional[str] = None
    days: Optional[list[int]] = None
    timezone: Optional[str] = None
    enabled: bool = True
    workspace: Optional[str] = None
    warmup_prompt: Optional[str] = None


class JobUpdate(BaseModel):
    trigger: Optional[Literal["once", "daily", "weekly"]] = None
    time: Optional[str] = None
    date: Optional[str] = None
    days: Optional[list[int]] = None
    timezone: Optional[str] = None
    enabled: Optional[bool] = None
    workspace: Optional[str] = None
    warmup_prompt: Optional[str] = None


class Job(BaseModel):
    id: str
    tool: Literal["claude", "codex"]
    trigger: Literal["once", "daily", "weekly"]
    time: str
    date: Optional[str] = None
    days: Optional[list[int]] = None
    timezone: str
    enabled: bool
    workspace: str
    warmup_prompt: str
    created_at: str
    updated_at: str


class HistoryEntry(BaseModel):
    """Session history.

    status="started" means the tmux session launched. It does not mean the
    warm-up prompt was delivered; warmup_status/warmup_sent_at track that
    optional delivery state separately.
    """

    id: str
    tool: Literal["claude", "codex"]
    trigger_type: Literal["manual", "scheduled"]
    job_id: Optional[str] = None
    scheduled_time: Optional[str] = None
    actual_start_time: str
    workspace: str
    status: Literal["started", "already_running", "warmed_existing", "failed"]
    error_message: Optional[str] = None
    warmup_sent_at: Optional[str] = None
    warmup_status: Optional[Literal["pending", "sent", "failed"]] = None
    estimated_end_time: str


class StatusResult(BaseModel):
    running: bool
    pids: list[int] = []
    started_at: Optional[str] = None
    estimated_ends_at: Optional[str] = None
    expires_at: Optional[str] = None
    next_session: Optional[str] = None
    next_job_id: Optional[str] = None
