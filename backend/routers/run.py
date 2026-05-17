from __future__ import annotations

import os
import asyncio
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException

from backend.auth import verify_key
from backend.scheduler import DEFAULT_WARMUP, DEFAULT_WORKSPACE, TOOLS, _COMMANDS
from backend.session import is_running, send_prompt_async, start_session, start_ttyd_if_available
from backend.storage import append_history, load_jobs, save_expiry


router = APIRouter()
TTYD_PORTS = {"claude": 7681, "codex": 7682}


def _default_job_value(tool: str, key: str, fallback: str) -> str:
    for job in load_jobs().get("jobs", []):
        if job.get("tool") == tool and job.get("enabled", True) and job.get(key):
            return job[key]
    return fallback


@router.post("/run/{tool}", dependencies=[Depends(verify_key)])
async def run_tool(tool: str) -> dict:
    if tool not in TOOLS:
        raise HTTPException(status_code=400, detail="Unknown tool")

    session_name = f"{tool}-session"
    workspace = _default_job_value(
        tool,
        "workspace",
        os.getenv("DEFAULT_WORKSPACE", DEFAULT_WORKSPACE),
    )
    warmup_prompt = _default_job_value(tool, "warmup_prompt", DEFAULT_WARMUP)
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
        start_ttyd_if_available(tool, TTYD_PORTS[tool], session_name)
        await asyncio.sleep(1)
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
        trigger_type="manual",
        job_id=None,
        scheduled_time=None,
        workspace=workspace,
        status=status,
        error_message=error,
        estimated_end_time=estimated_end,
        warmup_sent_at=warmup_sent_at,
        warmup_status=warmup_status,
    )
    return {"status": status, "tool": tool, "error": error}
