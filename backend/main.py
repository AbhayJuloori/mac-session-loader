from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from backend.routers.history import router as history_router
from backend.routers.jobs import router as jobs_router
from backend.routers.run import router as run_router
from backend.routers.status import router as status_router
from backend.routers.system import router as system_router
from backend.scheduler import init_scheduler, scheduler
from backend.session import start_ttyd_if_available


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_scheduler()
    start_ttyd_if_available("claude", 7681, "claude-session")
    start_ttyd_if_available("codex", 7682, "codex-session")
    yield
    if scheduler.running:
        scheduler.shutdown(wait=False)


app = FastAPI(title="Mac Session Loader", lifespan=lifespan)
app.include_router(run_router)
app.include_router(status_router)
app.include_router(jobs_router)
app.include_router(history_router)
app.include_router(system_router)
app.mount("/static", StaticFiles(directory="frontend"), name="static")


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    return HTMLResponse(Path("frontend/index.html").read_text())
