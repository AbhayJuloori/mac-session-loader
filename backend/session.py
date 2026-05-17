from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import HTTPException


def _require_tmux() -> None:
    if shutil.which("tmux") is None:
        raise HTTPException(status_code=503, detail="tmux not installed; cannot manage sessions")


_IGNORED_PROCESS_TERMS = ("python", "uvicorn", "pytest", "pgrep", "session-loader")


def _tool_name(value: str) -> str:
    return value.removesuffix("-session")


def _matches_tool_process(tool: str, pid: int, command: str) -> bool:
    if pid == os.getpid():
        return False
    text = command.lower()
    if not text or _tool_name(tool).lower() not in text:
        return False
    return not any(term in text for term in _IGNORED_PROCESS_TERMS)


def _process_command(pid: int) -> str:
    try:
        result = subprocess.run(
            ["ps", "-o", "command=", "-p", str(pid)],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _pids_from_psutil(tool: str) -> Optional[list[int]]:
    try:
        import psutil
    except ImportError:
        return None

    try:
        pids = []
        for process in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                info = process.info
                command = " ".join([info.get("name") or "", *(info.get("cmdline") or [])])
                pid = int(info["pid"])
            except (psutil.AccessDenied, psutil.NoSuchProcess, TypeError, ValueError):
                continue
            if _matches_tool_process(tool, pid, command):
                pids.append(pid)
        return pids
    except Exception:
        return None


def get_process_pids(tool: str) -> list[int]:
    tool = _tool_name(tool)
    psutil_pids = _pids_from_psutil(tool)
    if psutil_pids is not None:
        return psutil_pids

    try:
        result = subprocess.run(
            ["pgrep", "-f", tool],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return []
    if result.returncode != 0:
        return []

    pids = []
    for line in result.stdout.splitlines():
        try:
            pid = int(line.strip())
        except ValueError:
            continue
        if _matches_tool_process(tool, pid, _process_command(pid)):
            pids.append(pid)
    return pids


def tmux_session_exists(name: str) -> bool:
    if shutil.which("tmux") is None:
        return False
    try:
        result = subprocess.run(
            ["tmux", "has-session", "-t", name],
            capture_output=True,
        )
    except FileNotFoundError:
        return False
    return result.returncode == 0


def get_session_pids(name: str) -> list[int]:
    if not tmux_session_exists(name):
        return []
    try:
        result = subprocess.run(
            ["tmux", "list-panes", "-t", name, "-F", "#{pane_pid}"],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return []
    if result.returncode != 0:
        return []
    pids = []
    for line in result.stdout.splitlines():
        try:
            pids.append(int(line.strip()))
        except ValueError:
            continue
    return pids


def is_running(name: str) -> bool:
    return tmux_session_exists(name)


def get_session_start_time(name: str) -> Optional[str]:
    if not tmux_session_exists(name):
        return None
    try:
        result = subprocess.run(
            ["tmux", "display-message", "-p", "-t", name, "#{session_created}"],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    try:
        return datetime.fromtimestamp(int(result.stdout.strip())).isoformat()
    except (TypeError, ValueError):
        return None


def get_session_activity_time(name: str) -> Optional[datetime]:
    if not tmux_session_exists(name):
        return None
    try:
        result = subprocess.run(
            ["tmux", "display-message", "-p", "-t", name, "#{session_activity}"],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    try:
        return datetime.fromtimestamp(int(result.stdout.strip()))
    except (TypeError, ValueError):
        return None


def kill_session(name: str) -> bool:
    if not tmux_session_exists(name):
        return False
    try:
        result = subprocess.run(
            ["tmux", "kill-session", "-t", name],
            capture_output=True,
        )
    except FileNotFoundError:
        return False
    return result.returncode == 0


def get_claude_rate_limit_expiry() -> dict | None:
    try:
        path = Path.home() / ".claude" / "rate-limit-state.json"
        with path.open() as file:
            data = json.load(file)
        five_hour = data["rate_limits"]["five_hour"]
        seven_day = data["rate_limits"]["seven_day"]
        resets_at = datetime.fromtimestamp(five_hour["resets_at"], tz=timezone.utc)
        if resets_at <= datetime.now(tz=timezone.utc):
            return None
        return {
            "expires_at": resets_at.isoformat(),
            "remaining_pct": five_hour["remaining_percentage"],
            "used_pct": five_hour["used_percentage"],
            "captured_at": data["captured_at"],
            "seven_day_resets_at": datetime.fromtimestamp(seven_day["resets_at"], tz=timezone.utc).isoformat(),
            "seven_day_remaining_pct": seven_day["remaining_percentage"],
        }
    except Exception:
        return None


def get_logs(name: str, lines: int = 50) -> dict:
    if not is_running(name):
        return {"status": "not_running", "logs": ""}
    try:
        result = subprocess.run(
            ["tmux", "capture-pane", "-p", "-t", name],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return {"status": "not_running", "logs": ""}
    if result.returncode != 0:
        return {"status": "not_running", "logs": ""}
    return {"status": "running", "logs": "\n".join(result.stdout.splitlines()[-lines:])}


def _send_warmup(name: str, command: str, is_claude: bool, warmup_prompt: str) -> None:
    subprocess.run(
        ["tmux", "send-keys", "-t", name, command, "Enter"],
        capture_output=True,
    )
    if is_claude:
        time.sleep(13)
        subprocess.run(["tmux", "send-keys", "-t", name, "Enter"], capture_output=True)
        time.sleep(5)
    else:
        time.sleep(3)
    subprocess.run(
        ["tmux", "send-keys", "-t", name, warmup_prompt, "Enter"],
        capture_output=True,
    )


def _send_prompt(name: str, prompt: str) -> None:
    subprocess.run(
        ["tmux", "send-keys", "-t", name, prompt, "Enter"],
        capture_output=True,
    )


def send_warmup_async(name: str, command: str, is_claude: bool, warmup_prompt: str) -> None:
    _require_tmux()
    if not tmux_session_exists(name):
        raise HTTPException(status_code=404, detail=f"tmux session not found: {name}")
    threading.Thread(
        target=_send_warmup,
        args=(name, command, is_claude, warmup_prompt),
        daemon=True,
    ).start()


def send_prompt_async(name: str, prompt: str) -> None:
    _require_tmux()
    if not tmux_session_exists(name):
        raise HTTPException(status_code=404, detail=f"tmux session not found: {name}")
    threading.Thread(
        target=_send_prompt,
        args=(name, prompt),
        daemon=True,
    ).start()


def start_session(
    name: str,
    command: str,
    workspace: str,
    warmup_prompt: str,
    is_claude: bool,
) -> None:
    _require_tmux()
    if is_running(name):
        send_prompt_async(name, warmup_prompt)
        return
    subprocess.run(
        [
            "tmux",
            "new-session",
            "-d",
            "-s",
            name,
            "-x",
            "220",
            "-y",
            "50",
            "-e",
            "TERM=xterm-256color",
            "-c",
            workspace,
            "/bin/zsh",
        ],
        check=True,
    )
    send_warmup_async(name, command, is_claude, warmup_prompt)


def start_ttyd_if_available(tool: str, port: int, session_name: str) -> None:
    del tool
    if shutil.which("ttyd") is None:
        return
    pattern = f"ttyd.*-i 127.0.0.1.*-p {port}.*{session_name}"
    already = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True)
    if already.returncode == 0:
        return
    subprocess.Popen(
        [
            "ttyd",
            "-i",
            "127.0.0.1",
            "-p",
            str(port),
            "-W",
            "tmux",
            "new-session",
            "-A",
            "-s",
            session_name,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
