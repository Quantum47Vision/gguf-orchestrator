"""
api/app.py — FastAPI application. All HTTP and WebSocket endpoints live here.

Endpoints:
  GET  /                        → serve frontend HTML
  GET  /api/status              → model + system status
  GET  /api/projects            → list projects
  POST /api/projects            → create project
  DELETE /api/projects/{id}     → delete project
  POST /api/projects/{id}/index → trigger re-indexing
  GET  /api/projects/{id}/files → file tree
  GET  /api/projects/{id}/conversation → chat history
  DELETE /api/projects/{id}/conversation → clear chat
  POST /api/apply               → apply accepted file diffs
  WS   /ws/chat                 → streaming chat WebSocket
"""


import json
import logging

from pathlib import Path


from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse, Response

from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

log = logging.getLogger(__name__)

# ── App setup ────────────────────────────────────────────────
app = FastAPI(
    title="GGUF Orchestrator",
    description="Local AI coding assistant powered by your GGUF models",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve frontend static files
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


BASE_DIR = Path(__file__).resolve().parent.parent  # api/ -> project root
FAVICON_PATH = BASE_DIR / "frontend" / "favicon.ico"

@app.get("/favicon.ico")
async def favicon():
    if FAVICON_PATH.exists():
        return FileResponse(FAVICON_PATH)
    return Response(status_code=204)


# ── Startup / Shutdown ───────────────────────────────────────
@app.on_event("startup")
async def startup():
    logging.basicConfig(level=logging.INFO)
    log.info("Starting GGUF Orchestrator...")

    from db.postgres import init_schema
    try:
        await init_schema()
        log.info("  ✓ Database ready")
    except Exception as e:
        log.error(f"  ✗ Database connection failed: {e}")
        log.error("    Check config.yaml → database section")

    from orchestrator.model_manager import manager
    try:
        await manager.startup()
        log.info("  ✓ Models ready")
    except Exception as e:
        log.error(f"  ✗ Model startup error: {e}")

    log.info("GGUF Orchestrator running at http://localhost:8000")


@app.on_event("shutdown")
async def shutdown():
    from orchestrator.model_manager import manager
    await manager.shutdown()
    from db.postgres import close_pool
    await close_pool()


# ── Frontend ─────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    index = FRONTEND_DIR / "index.html"

    if index.exists():
        return HTMLResponse(
            content=index.read_text(encoding="utf-8"),
            media_type="text/html; charset=utf-8"
        )

    return HTMLResponse(
        "<h1>Frontend not found. Place index.html in /frontend/</h1>",
        media_type="text/html; charset=utf-8"
    )


# ── Status ───────────────────────────────────────────────────
@app.get("/api/status")
async def get_status():
    from orchestrator.model_manager import manager
    return {
        "status": "running",
        "models": manager.status(),
        "version": "1.0.0",
    }


# ── Projects ─────────────────────────────────────────────────
class ProjectCreate(BaseModel):
    name: str
    root_path: str


@app.get("/api/projects")
async def list_projects():
    from db.postgres import get_projects
    return await get_projects()


@app.post("/api/projects")
async def create_project(body: ProjectCreate):
    from db.postgres import create_project
    if not Path(body.root_path).exists():
        raise HTTPException(400, f"Path does not exist: {body.root_path}")
    project = await create_project(body.name, body.root_path)
    return project


@app.delete("/api/projects/{project_id}")
async def delete_project(project_id: int):
    from db.postgres import delete_project
    await delete_project(project_id)
    return {"success": True}


# ── Indexing ─────────────────────────────────────────────────
_indexing_progress = {}  # project_id → {"current": n, "total": n, "file": "..."}


@app.post("/api/projects/{project_id}/index")
async def trigger_index(project_id: int, background_tasks: BackgroundTasks):
    from db.postgres import get_project
    project = await get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    async def run_index():
        from rag.pipeline import index_project

        def progress(current, total, file_name):
            _indexing_progress[project_id] = {
                "current": current,
                "total": total,
                "file": file_name,
                "running": True,
            }

        _indexing_progress[project_id] = {"current": 0, "total": 0, "file": "", "running": True}
        try:
            chunks = await index_project(project_id, project["root_path"], on_progress=progress)
            _indexing_progress[project_id] = {
                "current": 0, "total": 0, "file": "", "running": False,
                "done": True, "chunks": chunks
            }
        except Exception as e:
            _indexing_progress[project_id] = {"running": False, "error": str(e)}

    background_tasks.add_task(run_index)
    return {"message": "Indexing started", "project_id": project_id}


@app.get("/api/projects/{project_id}/index/progress")
async def index_progress(project_id: int):
    return _indexing_progress.get(project_id, {"running": False, "done": False})


# ── File Tree ─────────────────────────────────────────────────
@app.get("/api/projects/{project_id}/files")
async def get_file_tree(project_id: int):
    from db.postgres import get_project
    from config import _raw

    project = await get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    root = Path(project["root_path"])
    exclude_dirs = set(_raw["rag"].get("exclude_dirs", []))
    include_ext = set(_raw["rag"].get("include_extensions", []))

    def build_tree(path: Path, depth: int = 0) -> dict | None:
        if depth > 6:
            return None
        name = path.name
        if path.is_dir():
            if name in exclude_dirs or name.startswith("."):
                return None
            children = []
            try:
                for child in sorted(path.iterdir()):
                    node = build_tree(child, depth + 1)
                    if node:
                        children.append(node)
            except PermissionError:
                pass
            return {"name": name, "type": "dir", "children": children, "path": str(path)}
        else:
            if path.suffix not in include_ext:
                return None

            return {"name": name, "type": "file", "path": str(path.resolve()), "ext": path.suffix}
        

    tree = build_tree(root)
    return tree or {}


# ── Conversation ──────────────────────────────────────────────
@app.get("/api/projects/{project_id}/conversation")
async def get_conversation(project_id: int):
    from db.postgres import get_conversation
    return await get_conversation(project_id)


@app.delete("/api/projects/{project_id}/conversation")
async def clear_conversation(project_id: int):
    from db.postgres import clear_conversation
    await clear_conversation(project_id)
    return {"success": True}


# ── Apply Diffs ───────────────────────────────────────────────
class ApplyRequest(BaseModel):
    project_id: int
    changes: list   # list of {file_path, new_content, status}


@app.post("/api/apply")
async def apply_changes(body: ApplyRequest):
    from diff.engine import apply_all_changes
    from db.postgres import get_project

    project = await get_project(body.project_id)
    root = project["root_path"] if project else None

    results = apply_all_changes(body.changes, project_root=root)
    return {"results": results}


# ── File content reader ───────────────────────────────────────
@app.get("/api/file")
async def read_file(path: str):
    try:
        content = Path(path).read_text(encoding="utf-8", errors="replace")
        return {"path": path, "content": content}
    except Exception as e:
        raise HTTPException(400, str(e))


# ── WebSocket Chat ────────────────────────────────────────────
@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    await websocket.accept()
    log.info("WebSocket chat connected")

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({"type": "error", "message": "Invalid JSON"}))
                continue

            user_message = data.get("message", "").strip()
            project_id = data.get("project_id")
            conversation_history = data.get("history", [])

            if not user_message:
                continue

            # Save user message to DB
            if project_id:
                from db.postgres import save_message
                await save_message(project_id, "user", user_message)

            # Run the orchestration pipeline
            from orchestrator.engine import process_request
            assistant_text = ""

            async for event in process_request(user_message, project_id, conversation_history):
                await websocket.send_text(json.dumps(event))
                if event["type"] == "token":
                    assistant_text += event["content"]

            # Save assistant response to DB
            if project_id and assistant_text:
                from db.postgres import save_message
                model_used = "unknown"
                await save_message(project_id, "assistant", assistant_text, model_used)

    except WebSocketDisconnect:
        log.info("WebSocket chat disconnected")
    except Exception as e:
        log.exception("WebSocket error")
        try:
            await websocket.send_text(json.dumps({"type": "error", "message": str(e)}))
        except Exception:
            pass
