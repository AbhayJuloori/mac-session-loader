import importlib

import pytest
from fastapi import HTTPException


def test_valid_key_passes(monkeypatch):
    monkeypatch.setenv("SESSION_LOADER_KEY", "secret")
    import backend.auth as auth_mod

    importlib.reload(auth_mod)
    auth_mod.verify_key("secret")


def test_invalid_key_raises_401(monkeypatch):
    monkeypatch.setenv("SESSION_LOADER_KEY", "secret")
    import backend.auth as auth_mod

    importlib.reload(auth_mod)
    with pytest.raises(HTTPException) as exc:
        auth_mod.verify_key("wrong")
    assert exc.value.status_code == 401


def test_missing_key_raises_401(monkeypatch):
    monkeypatch.setenv("SESSION_LOADER_KEY", "secret")
    import backend.auth as auth_mod

    importlib.reload(auth_mod)
    with pytest.raises(HTTPException) as exc:
        auth_mod.verify_key(None)
    assert exc.value.status_code == 401


def test_missing_env_raises_500(monkeypatch):
    monkeypatch.delenv("SESSION_LOADER_KEY", raising=False)
    import backend.auth as auth_mod

    importlib.reload(auth_mod)
    with pytest.raises(HTTPException) as exc:
        auth_mod.verify_key("anything")
    assert exc.value.status_code == 500
