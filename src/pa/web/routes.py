"""HTTP routes: index page, chat SSE, thread CRUD, vault tree, reminders,
tools catalog, profile, health."""

from __future__ import annotations

import asyncio
import dataclasses
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from pa import threads as threads_mod
from pa.agent import drop_conversation, ensure_thread, run_turn
from pa.config import settings
from pa.llm import get_llm, installed_model_names, model_installed
from pa.tool_gate import get_gate, group_for_tool
from pa.tools import registry as tools_registry
from pa.tools import reminders as reminders_tool
from pa.vault.conventions import PROFILE_FILE, SYSTEM_DIR
from pa.vault.manager import VaultNotMountedError, get_vault
from pa.vault.note import Note

_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = None


class RenameRequest(BaseModel):
    title: str


class CreateThreadRequest(BaseModel):
    title: str | None = None


class ReminderAddRequest(BaseModel):
    text: str


class ReminderPatchRequest(BaseModel):
    done: bool


class ToolTogglePayload(BaseModel):
    enabled: bool


class ProfileUpdate(BaseModel):
    name: str | None = None
    pronouns: str | None = None
    voice: str | None = None


def _require_mounted_vault():
    vault = get_vault()
    try:
        vault.ensure_mounted()
    except VaultNotMountedError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return vault


# ── Index + health ────────────────────────────────────────────────


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    vault = get_vault()
    boot = {
        "model": settings.chat_model,
        "embed_model": settings.embed_model,
        "vault_path": str(vault.root),
        "vault_mounted": vault.is_mounted(),
    }
    return templates.TemplateResponse(request, "index.html", {"boot": boot})


@router.get("/favicon.ico", include_in_schema=False)
async def favicon() -> FileResponse:
    return FileResponse(
        Path(__file__).parent / "static" / "favicon.svg",
        media_type="image/svg+xml",
    )


@router.get("/health")
async def health() -> dict:
    vault = get_vault()
    return {
        "vault_mounted": vault.is_mounted(),
        "vault_path": str(vault.root),
        "model": settings.chat_model,
        "embed_model": settings.embed_model,
    }


@router.get("/ollama/status")
async def ollama_status() -> JSONResponse:
    """Diagnostics for the local Ollama server.

    Returns the installed model list, currently-loaded models, and whether
    the configured chat/embed models are present. Useful to run from a curl
    or browser tab when chat seems hung.
    """
    llm = get_llm()
    payload: dict[str, Any] = {
        "host": llm.host,
        "chat_model": settings.chat_model,
        "embed_model": settings.embed_model,
        "reachable": False,
    }
    try:
        listed = await llm.list_models()
    except Exception as exc:  # noqa: BLE001
        payload["error"] = f"{type(exc).__name__}: {exc}"
        return JSONResponse(payload, status_code=503)

    payload["reachable"] = True
    names = set(installed_model_names(listed))
    payload["installed"] = sorted(names)
    payload["chat_model_present"] = model_installed(settings.chat_model, names)
    payload["embed_model_present"] = model_installed(settings.embed_model, names)

    try:
        running = await llm.running_models()
    except Exception as exc:  # noqa: BLE001
        payload["running_error"] = f"{type(exc).__name__}: {exc}"
        return JSONResponse(payload)
    payload["running"] = sorted(installed_model_names(running))
    return JSONResponse(payload)


# ── Chat (SSE) ────────────────────────────────────────────────────


@router.post("/chat")
async def chat(req: ChatRequest) -> StreamingResponse:
    _require_mounted_vault()
    conversation = ensure_thread(req.thread_id, req.message)
    thread_id = conversation.thread_id

    async def event_stream():
        yield f"data: {json.dumps({'kind': 'thread', 'text': thread_id})}\n\n"
        await asyncio.sleep(0)
        try:
            async for event in run_turn(conversation, req.message):
                payload: dict = {"kind": event.kind}
                if event.text is not None:
                    payload["text"] = event.text
                if event.tool is not None:
                    payload["tool"] = dataclasses.asdict(event.tool)
                yield f"data: {json.dumps(payload)}\n\n"
                await asyncio.sleep(0)
        except Exception as exc:  # noqa: BLE001
            yield f"data: {json.dumps({'kind': 'error', 'text': str(exc)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── Threads ───────────────────────────────────────────────────────


@router.get("/threads")
async def threads_list(limit: int | None = None) -> JSONResponse:
    vault = _require_mounted_vault()
    summaries = threads_mod.list_threads(vault, limit=limit)
    return JSONResponse({"threads": [s.to_dict() for s in summaries]})


@router.post("/threads")
async def thread_create(req: CreateThreadRequest | None = None) -> JSONResponse:
    vault = _require_mounted_vault()
    title = (req.title or "").strip() if req else ""
    thread = threads_mod.create_thread(vault, title=title or threads_mod.DEFAULT_TITLE)
    return JSONResponse({
        "id": thread.thread_id,
        "title": thread.title,
        "created": thread.created,
        "last_message_at": thread.last_message_at,
        "message_count": 0,
    })


@router.get("/threads/{thread_id}")
async def thread_detail(thread_id: str) -> JSONResponse:
    vault = _require_mounted_vault()
    try:
        thread = threads_mod.load_thread(vault, thread_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return JSONResponse(
        {
            "id": thread.thread_id,
            "title": thread.title,
            "created": thread.created,
            "updated": thread.updated,
            "last_message_at": thread.last_message_at,
            "messages": [m.to_dict() for m in thread.messages],
        }
    )


@router.patch("/threads/{thread_id}")
async def thread_rename(thread_id: str, req: RenameRequest) -> JSONResponse:
    vault = _require_mounted_vault()
    try:
        thread = threads_mod.rename_thread(vault, thread_id, req.title)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    drop_conversation(thread_id)
    return JSONResponse({"id": thread.thread_id, "title": thread.title})


@router.delete("/threads/{thread_id}")
async def thread_delete(thread_id: str) -> JSONResponse:
    vault = _require_mounted_vault()
    try:
        threads_mod.delete_thread(vault, thread_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    drop_conversation(thread_id)
    return JSONResponse({"ok": True})


# ── Vault ─────────────────────────────────────────────────────────


@router.get("/vault/tree")
async def vault_tree(directory: str = "") -> JSONResponse:
    vault = _require_mounted_vault()
    return JSONResponse({"directory": directory or "/", "entries": vault.list_directory(directory)})


@router.get("/vault/file")
async def vault_file(path: str) -> JSONResponse:
    vault = _require_mounted_vault()
    try:
        target = vault.resolve_inside(path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="not found")
    if SYSTEM_DIR in target.relative_to(vault.root).parts:
        raise HTTPException(status_code=403, detail="system files are not viewable")
    return JSONResponse({"path": path, "content": target.read_text(encoding="utf-8")})


# ── Tools (group toggles for backwards compat + per-tool catalog) ──


@router.get("/tools/state")
async def tools_state() -> JSONResponse:
    """Legacy group-level state (kept for any external clients)."""
    return JSONResponse({"groups": get_gate().group_state()})


@router.get("/tools/catalog")
async def tools_catalog() -> JSONResponse:
    """Every tool the app knows about (built-in + MCP), with per-tool state."""
    return JSONResponse(_build_catalog())


@router.post("/tools/catalog/{tool_id}")
async def tools_catalog_toggle(tool_id: str, req: ToolTogglePayload) -> JSONResponse:
    gate = get_gate()
    if not gate.set_tool_enabled(tool_id, req.enabled):
        raise HTTPException(status_code=400, detail=f"unknown tool: {tool_id!r}")
    return JSONResponse(_build_catalog())


def _build_catalog() -> dict:
    """Group every known tool by its source (Vault / Web / Notion / MCP)."""
    gate = get_gate()

    # Collect every tool we know about: built-ins from registry._SCHEMAS,
    # MCP-provided tools via the manager (if wired).
    schemas: list[dict[str, Any]] = list(tools_registry._SCHEMAS)
    if tools_registry._mcp_manager is not None:
        schemas.extend(tools_registry._mcp_manager.tool_schemas())

    builtin_group_for: dict[str, dict] = {
        "list_files": {"id": "files", "label": "Files & vault"},
        "read_file": {"id": "files", "label": "Files & vault"},
        "write_file": {"id": "files", "label": "Files & vault"},
        "append_to_file": {"id": "files", "label": "Files & vault"},
        "semantic_search": {"id": "search", "label": "Search"},
        "text_search": {"id": "search", "label": "Search"},
        "list_reminders": {"id": "reminders", "label": "Time & reminders"},
        "create_reminder": {"id": "reminders", "label": "Time & reminders"},
        "complete_reminder": {"id": "reminders", "label": "Time & reminders"},
        "current_datetime": {"id": "reminders", "label": "Time & reminders"},
        "list_threads": {"id": "memory", "label": "Memory"},
        "read_thread": {"id": "memory", "label": "Memory"},
    }

    grouped: dict[str, dict] = {}

    def add(
        tool_id: str,
        name: str,
        description: str,
        group_id: str,
        group_label: str,
        badge: str | None,
        available: bool,
        enabled: bool,
    ):
        g = grouped.setdefault(
            group_id, {"id": group_id, "label": group_label, "items": []}
        )
        g["items"].append({
            "id": tool_id,
            "name": name,
            "description": description,
            "badge": badge,
            "available": available,
            "enabled": enabled,
        })

    for s in schemas:
        fn = s.get("function", {}) or {}
        name = fn.get("name", "")
        if not name:
            continue
        description = fn.get("description", "") or ""
        ext_group = group_for_tool(name)
        if ext_group is not None:
            group_id = ext_group.id
            group_label = ext_group.label
            # External group: must be available (configured) AND its per-tool
            # flag true. Per-tool flag defaults to whatever the group says.
            available = gate.is_group_available(ext_group.id)
            enabled = available and gate.is_tool_enabled(name, default=True)
            badge = None
            if not available:
                badge = "needs setup"
        else:
            # Built-in: always available; per-tool flag defaults true.
            gmeta = builtin_group_for.get(name, {"id": "vault", "label": "Built-in"})
            group_id = gmeta["id"]
            group_label = gmeta["label"]
            available = True
            enabled = gate.is_tool_enabled(name, default=True)
            badge = None
        add(name, _pretty_name(name), description, group_id, group_label, badge, available, enabled)

    # Stable order: built-in groups first, then external.
    order = ["files", "search", "reminders", "memory", "vault", "web", "notion"]
    seen = set(order)
    extra = [gid for gid in grouped if gid not in seen]
    final = [grouped[gid] for gid in order if gid in grouped] + [grouped[gid] for gid in extra]
    return {"groups": final}


def _pretty_name(raw: str) -> str:
    # MCP tools come in as "server__tool"; surface just the tool part nicely.
    base = raw.split("__", 1)[-1]
    return base.replace("_", " ").strip().capitalize()


# ── Reminders ─────────────────────────────────────────────────────


@router.get("/reminders")
async def reminders_endpoint() -> JSONResponse:
    _require_mounted_vault()
    items = reminders_tool.list_active_items()
    return JSONResponse({"active": items})


@router.post("/reminders")
async def reminders_add(req: ReminderAddRequest) -> JSONResponse:
    _require_mounted_vault()
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text cannot be empty")
    reminders_tool.append_line(text)
    return JSONResponse({"active": reminders_tool.list_active_items()})


@router.patch("/reminders/{line}")
async def reminders_toggle(line: int, req: ReminderPatchRequest) -> JSONResponse:
    _require_mounted_vault()
    if not reminders_tool.set_done_at_line(line, req.done):
        raise HTTPException(status_code=404, detail=f"no reminder at line {line}")
    return JSONResponse({"active": reminders_tool.list_active_items()})


@router.delete("/reminders/{line}")
async def reminders_delete(line: int) -> JSONResponse:
    _require_mounted_vault()
    if not reminders_tool.delete_at_line(line):
        raise HTTPException(status_code=404, detail=f"no reminder at line {line}")
    return JSONResponse({"active": reminders_tool.list_active_items()})


# ── Profile ───────────────────────────────────────────────────────


@router.get("/profile")
async def profile_get() -> JSONResponse:
    vault = _require_mounted_vault()
    path = vault.root / PROFILE_FILE
    if not path.exists():
        return JSONResponse({"name": "", "pronouns": "", "voice": ""})
    note = Note.load(path)
    meta = note.metadata or {}
    return JSONResponse({
        "name": str(meta.get("name") or ""),
        "pronouns": str(meta.get("pronouns") or ""),
        "voice": str(meta.get("voice") or ""),
    })


@router.patch("/profile")
async def profile_patch(req: ProfileUpdate) -> JSONResponse:
    vault = _require_mounted_vault()
    path = vault.root / PROFILE_FILE
    note = Note.load(path) if path.exists() else Note(path=path, metadata={}, body="")
    if req.name is not None:
        note.metadata["name"] = req.name
    if req.pronouns is not None:
        note.metadata["pronouns"] = req.pronouns
    if req.voice is not None:
        note.metadata["voice"] = req.voice
    note.save()
    meta = note.metadata or {}
    return JSONResponse({
        "name": str(meta.get("name") or ""),
        "pronouns": str(meta.get("pronouns") or ""),
        "voice": str(meta.get("voice") or ""),
    })
