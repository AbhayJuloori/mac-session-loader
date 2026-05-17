import json
from datetime import datetime, timedelta, timezone
from subprocess import CompletedProcess
from unittest.mock import MagicMock, patch


def test_is_running_true():
    with patch("backend.session.shutil.which", return_value="/usr/bin/tmux"), patch("subprocess.run") as mock_run:
        mock_run.return_value = CompletedProcess(["tmux"], 0)
        from backend.session import is_running

        assert is_running("claude-session") is True
        mock_run.assert_called_once_with(["tmux", "has-session", "-t", "claude-session"], capture_output=True)


def test_is_running_false():
    with patch("backend.session.shutil.which", return_value="/usr/bin/tmux"), patch("subprocess.run") as mock_run:
        mock_run.return_value = CompletedProcess(["tmux"], 1)
        from backend.session import is_running

        assert is_running("claude-session") is False


def test_get_logs_not_running():
    with patch("backend.session.is_running", return_value=False):
        from backend.session import get_logs

        assert get_logs("claude-session") == {"status": "not_running", "logs": ""}


def test_get_logs_tmux_missing():
    with patch("subprocess.run", side_effect=FileNotFoundError):
        from backend.session import get_logs

        assert get_logs("claude-session")["status"] == "not_running"


def test_get_logs_running():
    with patch("backend.session.is_running", return_value=True), patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="line1\nline2\n")
        from backend.session import get_logs

        result = get_logs("claude-session")
        assert result == {"status": "running", "logs": "line1\nline2"}


def test_get_session_start_time_none_when_not_running():
    with patch("backend.session.tmux_session_exists", return_value=False):
        from backend.session import get_session_start_time

        assert get_session_start_time("claude-session") is None


def test_get_session_start_time_from_first_pid():
    created = int(datetime(2026, 5, 14, 8, 15, 30).timestamp())
    with patch("backend.session.tmux_session_exists", return_value=True), patch("subprocess.run") as mock_run:
        mock_run.return_value = CompletedProcess(["tmux"], 0, stdout=f"{created}\n")
        from backend.session import get_session_start_time

        assert get_session_start_time("claude-session") == "2026-05-14T08:15:30"


def test_get_session_activity_time_reads_tmux_activity():
    activity = int(datetime(2026, 5, 14, 8, 20, 30).timestamp())
    with patch("backend.session.tmux_session_exists", return_value=True), patch("subprocess.run") as mock_run:
        mock_run.return_value = CompletedProcess(["tmux"], 0, stdout=f"{activity}\n")
        from backend.session import get_session_activity_time

        assert get_session_activity_time("claude-session") == datetime.fromtimestamp(activity)
        mock_run.assert_called_once_with(
            ["tmux", "display-message", "-p", "-t", "claude-session", "#{session_activity}"],
            capture_output=True,
            text=True,
        )


def test_kill_session_kills_existing_tmux_session():
    with patch("backend.session.tmux_session_exists", return_value=True), patch("subprocess.run") as mock_run:
        mock_run.return_value = CompletedProcess(["tmux"], 0)
        from backend.session import kill_session

        assert kill_session("claude-session") is True
        mock_run.assert_called_once_with(
            ["tmux", "kill-session", "-t", "claude-session"],
            capture_output=True,
        )


def test_kill_session_skips_missing_tmux_session():
    with patch("backend.session.tmux_session_exists", return_value=False), patch("subprocess.run") as mock_run:
        from backend.session import kill_session

        assert kill_session("claude-session") is False
        mock_run.assert_not_called()


def test_get_claude_rate_limit_expiry_reads_state_file(tmp_path):
    state_dir = tmp_path / ".claude"
    state_dir.mkdir()
    five_hour_reset = int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())
    seven_day_reset = int((datetime.now(timezone.utc) + timedelta(days=7)).timestamp())
    (state_dir / "rate-limit-state.json").write_text(
        json.dumps(
            {
                "captured_at": "2026-05-15T01:11:36-04:00",
                "rate_limits": {
                    "five_hour": {
                        "resets_at": five_hour_reset,
                        "remaining_percentage": 27,
                        "used_percentage": 73,
                    },
                    "seven_day": {
                        "resets_at": seven_day_reset,
                        "remaining_percentage": 82,
                    },
                },
            }
        )
    )

    with patch("backend.session.Path.home", return_value=tmp_path):
        from backend.session import get_claude_rate_limit_expiry

        assert get_claude_rate_limit_expiry() == {
            "expires_at": datetime.fromtimestamp(five_hour_reset, tz=timezone.utc).isoformat(),
            "remaining_pct": 27,
            "used_pct": 73,
            "captured_at": "2026-05-15T01:11:36-04:00",
            "seven_day_resets_at": datetime.fromtimestamp(seven_day_reset, tz=timezone.utc).isoformat(),
            "seven_day_remaining_pct": 82,
        }


def test_get_claude_rate_limit_expiry_missing_file_returns_none(tmp_path):
    with patch("backend.session.Path.home", return_value=tmp_path):
        from backend.session import get_claude_rate_limit_expiry

        assert get_claude_rate_limit_expiry() is None


def test_start_session_tmux_command(monkeypatch):
    calls = []
    monkeypatch.setattr("backend.session.shutil.which", lambda binary: "/usr/bin/tmux")
    monkeypatch.setattr("backend.session.is_running", lambda name: False)
    monkeypatch.setattr("backend.session.threading.Thread", lambda **kwargs: MagicMock(start=lambda: calls.append(("thread", kwargs))))

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return CompletedProcess(cmd, 0)

    monkeypatch.setattr("backend.session.subprocess.run", fake_run)
    from backend.session import start_session

    start_session("codex-session", "codex", "/tmp", "Reply READY only.", False)

    assert calls[0][0] == [
        "tmux",
        "new-session",
        "-d",
        "-s",
        "codex-session",
        "-x",
        "220",
        "-y",
        "50",
        "-e",
        "TERM=xterm-256color",
        "-c",
        "/tmp",
        "/bin/zsh",
    ]
    assert calls[-1] == (
        "thread",
        {
            "target": start_session.__globals__["_send_warmup"],
            "args": ("codex-session", "codex", False, "Reply READY only."),
            "daemon": True,
        },
    )


def test_send_warmup_async_uses_existing_tmux_session(monkeypatch):
    calls = []
    monkeypatch.setattr("backend.session.shutil.which", lambda binary: "/usr/bin/tmux")
    monkeypatch.setattr("backend.session.tmux_session_exists", lambda name: True)
    monkeypatch.setattr("backend.session.threading.Thread", lambda **kwargs: MagicMock(start=lambda: calls.append(("thread", kwargs))))

    from backend.session import send_warmup_async

    send_warmup_async("claude-session", "claude", True, "Hi")

    assert calls == [
        (
            "thread",
            {
                "target": send_warmup_async.__globals__["_send_warmup"],
                "args": ("claude-session", "claude", True, "Hi"),
                "daemon": True,
            },
        )
    ]


def test_send_prompt_async_only_sends_prompt(monkeypatch):
    calls = []
    monkeypatch.setattr("backend.session.shutil.which", lambda binary: "/usr/bin/tmux")
    monkeypatch.setattr("backend.session.tmux_session_exists", lambda name: True)
    monkeypatch.setattr("backend.session.threading.Thread", lambda **kwargs: MagicMock(start=lambda: calls.append(("thread", kwargs))))

    from backend.session import send_prompt_async

    send_prompt_async("claude-session", "Start x process")

    assert calls == [
        (
            "thread",
            {
                "target": send_prompt_async.__globals__["_send_prompt"],
                "args": ("claude-session", "Start x process"),
                "daemon": True,
            },
        )
    ]


def test_start_ttyd_binds_localhost(monkeypatch):
    calls = []
    monkeypatch.setattr("backend.session.shutil.which", lambda binary: "/usr/bin/ttyd")
    monkeypatch.setattr(
        "backend.session.subprocess.run",
        lambda cmd, **kwargs: CompletedProcess(cmd, 1, stdout=""),
    )
    monkeypatch.setattr("backend.session.subprocess.Popen", lambda *args, **kwargs: calls.append((args, kwargs)))
    from backend.session import start_ttyd_if_available

    start_ttyd_if_available("claude", 7681, "claude-session")

    assert calls[0][0][0][:5] == ["ttyd", "-i", "127.0.0.1", "-p", "7681"]
