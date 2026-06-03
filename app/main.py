"""
BugLens — AI Runtime Debugging Platform
FastAPI application entrypoint.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.sessions import router as sessions_router
from app.api.reports import router as reports_router
from app.core.config import settings
from app.core.logging import get_logger
from app.db.store import init_db

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

log = get_logger("buglens")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    log.info("BugLens API starting up…")
    log.info(f"Workspace: {settings.workspace_dir.resolve()}")
    log.info(f"Model: {settings.ollama_model} via {settings.ollama_host}")
    yield
    log.info("BugLens API shutting down.")


app = FastAPI(
    title="BugLens API",
    description="AI Runtime Debugging Platform — see bugs before your users do.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions_router)
app.include_router(reports_router)


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}


# Serve the vanilla frontend (index.html at /, app.js, styles.css)
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")