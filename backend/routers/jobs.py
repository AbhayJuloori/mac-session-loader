from __future__ import annotations

import os
import re
from datetime import date, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException

from backend.auth import verify_key
from backend.models import JobCreate, JobUpdate
from backend.scheduler import DEFAULT_TIMEZONE, DEFAULT_WARMUP, get_next_run
from backend.scheduler import register_job, unregister_job
from backend.storage import load_jobs, save_jobs


router = APIRouter()
TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def _timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(status_code=400, detail="Unknown timezone") from exc


def _validate_time(value: str) -> None:
    if not TIME_RE.match(value):
        raise HTTPException(status_code=400, detail="Time must use HH:MM format")


def _validate_job_shape(job: dict) -> None:
    _validate_time(job.get("time", ""))
    tzinfo = _timezone(job.get("timezone") or DEFAULT_TIMEZONE)
    if job["trigger"] == "once":
        if not job.get("date"):
            raise HTTPException(status_code=400, detail="Date is required for once trigger")
        try:
            date.fromisoformat(job["date"])
            run_at = datetime.fromisoformat(f"{job['date']}T{job['time']}:00").replace(tzinfo=tzinfo)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Date must use YYYY-MM-DD format") from exc
        if run_at <= datetime.now(tzinfo):
            raise HTTPException(status_code=400, detail="Scheduled time must be in the future")
    if job["trigger"] == "weekly":
        days = job.get("days")
        if not days:
            raise HTTPException(status_code=400, detail="Days required for weekly trigger")
        if any(day < 0 or day > 6 for day in days):
            raise HTTPException(status_code=400, detail="Days must be 0-6")


def _build_job(update: JobCreate, default_timezone: str) -> dict:
    now = datetime.now().isoformat()
    job = {
        "id": str(uuid4()),
        "tool": update.tool,
        "trigger": update.trigger,
        "time": update.time,
        "date": update.date,
        "days": update.days,
        "timezone": update.timezone or default_timezone,
        "enabled": update.enabled,
        "workspace": update.workspace or os.getenv("DEFAULT_WORKSPACE", "/Users/abhayjuloori/"),
        "warmup_prompt": update.warmup_prompt or DEFAULT_WARMUP,
        "created_at": now,
        "updated_at": now,
    }
    _validate_job_shape(job)
    if job["trigger"] != "once":
        job.pop("date", None)
    if job["trigger"] != "weekly":
        job.pop("days", None)
    return job


@router.get("/jobs", dependencies=[Depends(verify_key)])
async def list_jobs() -> list[dict]:
    return [{**job, "next_run": get_next_run(job["id"])} for job in load_jobs().get("jobs", [])]


@router.post("/jobs", dependencies=[Depends(verify_key)])
async def create_job(update: JobCreate) -> dict:
    data = load_jobs()
    job = _build_job(update, data.get("timezone", DEFAULT_TIMEZONE))
    data.setdefault("jobs", []).append(job)
    save_jobs(data)
    register_job(job)
    return {**job, "next_run": get_next_run(job["id"])}


@router.put("/jobs/{job_id}", dependencies=[Depends(verify_key)])
async def update_job(job_id: str, update: JobUpdate) -> dict:
    data = load_jobs()
    jobs = data.get("jobs", [])
    job = next((item for item in jobs if item["id"] == job_id), None)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    job.update(update.model_dump(exclude_none=True))
    _validate_job_shape(job)
    if job["trigger"] != "once":
        job.pop("date", None)
    if job["trigger"] != "weekly":
        job.pop("days", None)
    job["updated_at"] = datetime.now().isoformat()
    save_jobs(data)
    unregister_job(job_id)
    register_job(job)
    return {**job, "next_run": get_next_run(job_id)}


@router.delete("/jobs/{job_id}", dependencies=[Depends(verify_key)])
async def delete_job(job_id: str) -> dict:
    data = load_jobs()
    if not any(job["id"] == job_id for job in data.get("jobs", [])):
        raise HTTPException(status_code=404, detail="Job not found")
    unregister_job(job_id)
    data["jobs"] = [job for job in data.get("jobs", []) if job["id"] != job_id]
    save_jobs(data)
    return {"status": "ok"}


@router.patch("/jobs/{job_id}/enable", dependencies=[Depends(verify_key)])
async def enable_job(job_id: str) -> dict:
    return _set_enabled(job_id, True)


@router.patch("/jobs/{job_id}/disable", dependencies=[Depends(verify_key)])
async def disable_job(job_id: str) -> dict:
    return _set_enabled(job_id, False)


def _set_enabled(job_id: str, enabled: bool) -> dict:
    data = load_jobs()
    job = next((item for item in data.get("jobs", []) if item["id"] == job_id), None)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    job["enabled"] = enabled
    job["updated_at"] = datetime.now().isoformat()
    save_jobs(data)
    if enabled:
        register_job(job)
    else:
        unregister_job(job_id)
    return {**job, "next_run": get_next_run(job_id)}
