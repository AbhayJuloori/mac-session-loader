from __future__ import annotations

import os
from typing import Optional

from fastapi import Header, HTTPException


def verify_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    key = os.getenv("SESSION_LOADER_KEY")
    if not key:
        raise HTTPException(status_code=500, detail="SESSION_LOADER_KEY not set")
    if not x_api_key or x_api_key != key:
        raise HTTPException(status_code=401, detail="Unauthorized")
