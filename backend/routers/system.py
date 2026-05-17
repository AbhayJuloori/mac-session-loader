from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.auth import verify_key
from backend.system_check import get_system_check


router = APIRouter()


@router.get("/system-check", dependencies=[Depends(verify_key)])
async def system_check() -> dict:
    return get_system_check()
