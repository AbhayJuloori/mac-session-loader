from __future__ import annotations

import subprocess
from typing import Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.auth import verify_key
from backend.scheduler import TOOLS, scheduler
from backend.session import (
    get_claude_rate_limit_expiry,
    get_session_pids,
    get_session_start_time,
    is_running,
)
from backend.storage import load_expiry, load_jobs, save_expiry


router = APIRouter()


class ExpiryUpdate(BaseModel):
    expires_at: Optional[str] = None


def _next_session_for_tool(tool: str) -> Tuple[Optional[str], Optional[str]]:
    candidates = []
    for job in load_jobs().get("jobs", []):
        if job.get("tool") != tool or not job.get("enabled", True):
            continue
        aps_job = scheduler.get_job(job["id"])
        next_run_time = getattr(aps_job, "next_run_time", None)
        if next_run_time:
            candidates.append((next_run_time, job["id"]))
    if not candidates:
        return None, None
    next_run_time, job_id = min(candidates, key=lambda item: item[0])
    try:
        return next_run_time.strftime("%-I:%M %p %Z"), job_id
    except ValueError:
        return next_run_time.strftime("%I:%M %p %Z").lstrip("0"), job_id


@router.get("/status", dependencies=[Depends(verify_key)])
async def status() -> dict:
    result = {}
    expiry = load_expiry()
    for tool in TOOLS:
        session_name = f"{tool}-session"
        pids = get_session_pids(session_name)
        running = is_running(session_name)
        started_at = get_session_start_time(session_name) if running else None
        next_session, next_job_id = _next_session_for_tool(tool)
        rate_info = get_claude_rate_limit_expiry() if tool == "claude" else None
        expires_at = rate_info["expires_at"] if rate_info is not None else expiry.get(tool)
        tool_status = {
            "running": running,
            "pids": pids,
            "started_at": started_at,
            "estimated_ends_at": None,
            "expires_at": expires_at,
            "next_session": next_session,
            "next_job_id": next_job_id,
        }
        if rate_info is not None:
            tool_status.update(
                {
                    "remaining_pct": rate_info["remaining_pct"],
                    "used_pct": rate_info["used_pct"],
                    "captured_at": rate_info["captured_at"],
                    "seven_day_resets_at": rate_info["seven_day_resets_at"],
                    "seven_day_remaining_pct": rate_info["seven_day_remaining_pct"],
                }
            )
        result[tool] = tool_status
    return result


@router.post("/expiry/{tool}", dependencies=[Depends(verify_key)])
async def update_expiry(tool: str, update: ExpiryUpdate) -> dict:
    if tool not in TOOLS:
        raise HTTPException(status_code=400, detail="Unknown tool")
    save_expiry(tool, update.expires_at)
    return {"tool": tool, "expires_at": update.expires_at}


@router.get("/remote-status", dependencies=[Depends(verify_key)])
async def remote_status() -> dict:
    result = subprocess.run(
        ["pgrep", "-f", "claude remote-control"],
        capture_output=True,
        text=True,
    )
    pids = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return {"claude_remote_control": {"running": result.returncode == 0, "pids": pids}}
