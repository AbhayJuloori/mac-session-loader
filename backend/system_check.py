from __future__ import annotations

import json
import subprocess


def check_dep(binary: str) -> bool:
    try:
        result = subprocess.run(["which", binary], capture_output=True, text=True)
    except FileNotFoundError:
        return False
    return result.returncode == 0


def _sleep_enabled() -> bool:
    try:
        result = subprocess.run(["pmset", "-g", "live"], capture_output=True, text=True)
    except FileNotFoundError:
        return False
    for line in result.stdout.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[0] == "sleep":
            try:
                return int(parts[1]) > 0
            except ValueError:
                return False
    return False


def _on_battery() -> bool:
    try:
        result = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True)
    except FileNotFoundError:
        return False
    return "Battery Power" in result.stdout


def _tailscale_active() -> bool:
    if not check_dep("tailscale"):
        return False
    result = subprocess.run(["tailscale", "status", "--json"], capture_output=True, text=True)
    if result.returncode != 0:
        return False
    try:
        return json.loads(result.stdout).get("BackendState") == "Running"
    except json.JSONDecodeError:
        return False


def get_system_check() -> dict:
    deps = {
        "tmux": check_dep("tmux"),
        "ttyd": check_dep("ttyd"),
        "tailscale": check_dep("tailscale"),
        "claude": check_dep("claude"),
        "codex": check_dep("codex"),
    }
    warnings = []
    if not deps["tmux"]:
        warnings.append("tmux not installed; session management unavailable")
    if not deps["ttyd"]:
        warnings.append("ttyd not installed; browser terminal fallback unavailable")
    if not deps["claude"]:
        warnings.append("claude CLI not found; Claude sessions unavailable")
    if not deps["codex"]:
        warnings.append("codex CLI not found; Codex CLI sessions unavailable")
    if _on_battery():
        warnings.append("Mac is on battery; plug in to prevent sleep during scheduled starts")
    if _sleep_enabled():
        warnings.append("Mac sleep is enabled; scheduled starts may be missed")

    return {
        "deps": deps,
        "warnings": warnings,
        "tailscale_active": _tailscale_active(),
    }
