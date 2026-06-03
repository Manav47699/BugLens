"""
Sessions API
POST /sessions          — upload ZIP and start a debug run (async)
GET  /sessions/{id}     — poll status + live log stream
DELETE /sessions/{id}   — cancel and clean up
"""

import asyncio
import shutil
from pathlib import Path

import aiofiles
from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.logging import get_logger
from app.models.session import Session, SessionStatus
from app.services.sandbox import Sandbox, SandboxError
from app.services.browser import BrowserAgent
from app.services.analyzer import Analyzer
from app.db import store

# Sessions are kept in memory for the lifetime of the process
# (status polling only — full data persisted to SQLite)
_sessions: dict[str, Session] = {}

router = APIRouter(prefix="/sessions", tags=["sessions"])
log = get_logger(__name__)


# ------------------------------------------------------------------
# POST /sessions — upload + start
# ------------------------------------------------------------------

@router.post("", status_code=202)
async def create_session(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="ZIP archive of the frontend project"),
):
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip files are accepted.")

    session = Session(filename=file.filename)
    _sessions[session.id] = session

    # Save the upload
    upload_dir = settings.workspace_dir / session.id / "_upload"
    upload_dir.mkdir(parents=True, exist_ok=True)
    zip_path = upload_dir / "project.zip"

    async with aiofiles.open(zip_path, "wb") as out:
        content = await file.read()
        await out.write(content)

    session.log(f"Received {file.filename} ({len(content):,} bytes)")
    background_tasks.add_task(_run_session, session.id, zip_path)

    return {"session_id": session.id, "status": session.status}


# ------------------------------------------------------------------
# GET /sessions/{id} — poll
# ------------------------------------------------------------------

@router.get("/{session_id}")
async def get_session(session_id: str):
    session = _get_or_404(session_id)
    return {
        "session_id": session.id,
        "status": session.status,
        "framework": session.framework,
        "filename": session.filename,
        "routes_discovered": session.routes_discovered,
        "routes_explored": session.routes_explored,
        "logs": [
            {"timestamp": e.timestamp.isoformat(), "level": e.level, "message": e.message}
            for e in session.logs
        ],
        "report_id": session.report_id,
        "error": session.error,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
    }


# ------------------------------------------------------------------
# DELETE /sessions/{id} — cancel + clean up
# ------------------------------------------------------------------

@router.delete("/{session_id}", status_code=204)
async def delete_session(session_id: str):
    session = _get_or_404(session_id)
    workspace = settings.workspace_dir / session_id
    if workspace.exists():
        shutil.rmtree(workspace, ignore_errors=True)
    _sessions.pop(session_id, None)


# ------------------------------------------------------------------
# Background task — the full pipeline
# ------------------------------------------------------------------

def _run_analysis_sync(analyzer, evidence_list, framework, routes_explored):
    """Run the async analyzer in a fresh event loop from a thread pool worker."""
    import asyncio as _asyncio
    loop = _asyncio.new_event_loop()
    try:
        return loop.run_until_complete(
            analyzer.analyze(evidence_list, framework, routes_explored)
        )
    finally:
        loop.close()


async def _run_session(session_id: str, zip_path: Path) -> None:
    session = _sessions.get(session_id)
    if not session:
        return

    sandbox = Sandbox(session)

    try:
        # Step 1 — Sandbox
        session.set_status(SessionStatus.SANDBOXING)
        base_url = await sandbox.setup(zip_path)

        # Step 2 — Explore + Capture
        session.set_status(SessionStatus.EXPLORING)
        screenshot_dir = settings.workspace_dir / session_id / "screenshots"
        agent = BrowserAgent(session, base_url, screenshot_dir)

        session.set_status(SessionStatus.CAPTURING)
        evidence_list = await agent.run()

        # Step 3 — Analyze
        session.set_status(SessionStatus.ANALYZING)
        analyzer = Analyzer(session)
        # _call_ollama is blocking — run in a fresh thread with its own event loop
        report = await asyncio.to_thread(
            _run_analysis_sync,
            analyzer, evidence_list, session.framework, session.routes_explored
        )

        # Persist report to SQLite
        store.save_report(report)

        session.report_id = report.id
        session.set_status(SessionStatus.DONE)
        session.log(
            f"Done. {len(report.bugs)} bug(s) found. "
            f"Top disaster score: {report.top_disaster_score:.1f}"
        )

    except SandboxError as exc:
        log.error(f"[{session_id}] Sandbox error: {exc}")
        session.error = str(exc)
        session.set_status(SessionStatus.FAILED)
        session.log(f"Failed (sandbox): {exc}", level="error")

    except Exception as exc:
        log.exception(f"[{session_id}] Unexpected error")
        session.error = str(exc)
        session.set_status(SessionStatus.FAILED)
        session.log(f"Failed: {exc}", level="error")

    finally:
        await sandbox.teardown()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _get_or_404(session_id: str) -> Session:
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    return session