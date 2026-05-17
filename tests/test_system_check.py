from unittest.mock import MagicMock, patch


def test_dep_present():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="/usr/bin/tmux\n")
        from backend.system_check import check_dep

        assert check_dep("tmux") is True


def test_dep_missing():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        from backend.system_check import check_dep

        assert check_dep("tmux") is False


def test_system_check_structure():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        from backend.system_check import get_system_check

        result = get_system_check()

    assert "deps" in result
    assert "tmux" in result["deps"]
    assert "ttyd" in result["deps"]
    assert "tailscale" in result["deps"]
    assert "claude" in result["deps"]
    assert "codex" in result["deps"]
    assert "warnings" in result
    assert "tailscale_active" in result


def test_sleep_check_ignores_disksleep():
    from backend.system_check import _sleep_enabled

    pmset_output = "   sleep              0\n   disksleep          10\n"
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=pmset_output)

        assert _sleep_enabled() is False


def test_sleep_check_catches_system_sleep():
    from backend.system_check import _sleep_enabled

    pmset_output = "   sleep              5\n   disksleep          10\n"
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=pmset_output)

        assert _sleep_enabled() is True
