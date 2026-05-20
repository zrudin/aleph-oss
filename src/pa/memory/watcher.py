"""Filesystem watcher that re-embeds notes when they change on disk.

This is what makes "edit a file in your editor, ask the assistant about it
seconds later" work without any manual reindex step.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from pa.memory.index import get_index
from pa.vault.conventions import SYSTEM_DIR
from pa.vault.manager import get_vault

log = logging.getLogger(__name__)

_DEBOUNCE_SECONDS = 1.5


class _Handler(FileSystemEventHandler):
    def __init__(self, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue[tuple[str, Path]]) -> None:
        self._loop = loop
        self._queue = queue

    def _enqueue(self, kind: str, path: str) -> None:
        p = Path(path)
        if p.suffix != ".md":
            return
        try:
            rel = p.resolve().relative_to(get_vault().root)
        except ValueError:
            return
        if rel.parts and rel.parts[0] == SYSTEM_DIR:
            return
        self._loop.call_soon_threadsafe(self._queue.put_nowait, (kind, p))

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._enqueue("upsert", event.src_path)

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._enqueue("upsert", event.src_path)

    def on_moved(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._enqueue("delete", event.src_path)
            self._enqueue("upsert", event.dest_path)

    def on_deleted(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._enqueue("delete", event.src_path)


class VaultWatcher:
    def __init__(self) -> None:
        self._observer: Observer | None = None
        self._queue: asyncio.Queue[tuple[str, Path]] | None = None
        self._task: asyncio.Task | None = None
        self._pending: dict[Path, str] = {}

    async def start(self) -> None:
        vault = get_vault()
        vault.ensure_mounted()
        loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue()
        handler = _Handler(loop, self._queue)
        self._observer = Observer()
        self._observer.schedule(handler, str(vault.root), recursive=True)
        self._observer.start()
        self._task = asyncio.create_task(self._consume(), name="vault-watcher")
        log.info("vault watcher started on %s", vault.root)

    async def stop(self) -> None:
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=2.0)
            self._observer = None
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._task = None

    async def _consume(self) -> None:
        assert self._queue is not None
        index = get_index()
        while True:
            kind, path = await self._queue.get()
            self._pending[path] = kind
            # Debounce: keep draining until quiet.
            try:
                while True:
                    kind, path = await asyncio.wait_for(self._queue.get(), timeout=_DEBOUNCE_SECONDS)
                    self._pending[path] = kind
            except asyncio.TimeoutError:
                pass

            batch = list(self._pending.items())
            self._pending.clear()
            for p, k in batch:
                try:
                    if k == "delete":
                        await index.remove_file(p)
                    else:
                        await index.reindex_file(p)
                except Exception as exc:  # noqa: BLE001
                    log.warning("indexing failed for %s: %s", p, exc)
