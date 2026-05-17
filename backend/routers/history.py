from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.auth import verify_key
from backend.storage import load_history


router = APIRouter()


@router.get("/history", dependencies=[Depends(verify_key)])
async def history() -> list[dict]:
    return list(reversed(load_history()))
