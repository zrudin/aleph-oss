"""FastAPI app factory + lifespan management.

Lifespan orchestrates: ensure vault mounted → bootstrap directories → start the
file watcher and background scheduler → reverse the order on shutdown.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from pa.config import settings
from pa.llm import get_llm, installed_model_names, model_installed
from pa.mcp import MCPManager, MCPServer
from pa.memory.index import get_index
from pa.memory.watcher import VaultWatcher
from pa.scheduler import build_scheduler
from pa.secrets import get_secret
from pa.tool_gate import get_gate
from pa.tools.registry import set_mcp_manager
from pa.vault.manager import VaultNotMountedError, get_vault
from pa.web.routes import router

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    vault = get_vault()
    try:
        vault.ensure_mounted()
    except VaultNotMountedError as exc:
        log.error("%s", exc)
        raise

    vault.bootstrap()
    log.info("vault ready at %s", vault.root)

    await _log_ollama_preflight()

    # Initial reindex is best-effort; if Ollama isn't up, we'll keep serving
    # chat (which will surface a clearer error) rather than block startup.
    try:
        result = await get_index().reindex_all()
        log.info("initial index: %s", result)
    except Exception as exc:  # noqa: BLE001
        log.warning("initial reindex failed (Ollama not running?): %s", exc)

    watcher = VaultWatcher()
    await watcher.start()

    scheduler = build_scheduler()
    scheduler.start()
    log.info("scheduler started")

    gate = get_gate()
    gate.set_available("web", settings.enable_web)

    mcp_manager = MCPManager()
    mcp_specs = _build_mcp_specs()
    if mcp_specs:
        await mcp_manager.start(mcp_specs)
        set_mcp_manager(mcp_manager)
    gate.set_available("notion", "notion" in mcp_manager.server_names())

    app.state.watcher = watcher
    app.state.scheduler = scheduler
    app.state.mcp = mcp_manager

    try:
        yield
    finally:
        set_mcp_manager(None)
        await mcp_manager.stop()
        scheduler.shutdown(wait=False)
        await watcher.stop()
        log.info("shutdown complete")


async def _log_ollama_preflight() -> None:
    """Log whether Ollama is reachable and the configured models are installed.

    Best-effort: we don't fail startup if Ollama is down — chat itself will
    surface the error — but we want the log to make the problem obvious.
    """
    llm = get_llm()
    try:
        listed = await llm.list_models()
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "ollama preflight: cannot reach %s (%s: %s) — chat will fail until "
            "this is fixed",
            llm.host, type(exc).__name__, exc,
        )
        return

    names = installed_model_names(listed)
    log.info(
        "ollama preflight: %s reachable, %d models installed (%s)",
        llm.host, len(names), ", ".join(sorted(names)) if names else "<none>",
    )
    installed = set(names)
    for required, label in (
        (settings.chat_model, "chat"),
        (settings.embed_model, "embed"),
    ):
        if model_installed(required, installed):
            log.info("ollama %s model %r is installed", label, required)
        else:
            log.warning(
                "ollama %s model %r is NOT installed — run `ollama pull %s` "
                "(or `make ollama-pull`)",
                label, required, required,
            )


def _build_mcp_specs() -> list[MCPServer]:
    """Materialize MCP server specs from config + Keychain secrets."""
    specs: list[MCPServer] = []
    if settings.enable_notion and settings.notion_mcp_command:
        token = get_secret("notion_token")
        if not token:
            log.warning("PA_ENABLE_NOTION set but no notion_token in keychain; skipping")
        else:
            parts = settings.notion_mcp_command.split()
            specs.append(
                MCPServer(
                    name="notion",
                    command=parts[0],
                    args=parts[1:],
                    env={"NOTION_TOKEN": token},
                )
            )
    return specs


def create_app() -> FastAPI:
    app = FastAPI(title="Aleph", lifespan=lifespan)
    static_dir = Path(__file__).parent / "web" / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    app.include_router(router)
    return app


app = create_app()
