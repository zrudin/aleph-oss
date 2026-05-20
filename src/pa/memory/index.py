"""LanceDB-backed vector index over vault notes.

Stored inside `<vault>/.pa/index.lance/` so it travels with the encrypted volume.
Rows: (path, chunk_id, text, mtime, vector). One row per chunk.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import lancedb
import pyarrow as pa

from pa.llm import get_llm
from pa.memory.embeddings import chunk_text, embed_chunks
from pa.vault.conventions import INDEX_SUBDIR, SYSTEM_DIR
from pa.vault.manager import get_vault

log = logging.getLogger(__name__)

TABLE_NAME = "notes"
_EMBED_DIM = 768  # nomic-embed-text


def _schema(dim: int) -> pa.Schema:
    return pa.schema(
        [
            pa.field("path", pa.string()),
            pa.field("chunk_id", pa.int32()),
            pa.field("text", pa.string()),
            pa.field("mtime", pa.float64()),
            pa.field("vector", pa.list_(pa.float32(), dim)),
        ]
    )


class VaultIndex:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._db = None
        self._table = None
        self._dim = _EMBED_DIM

    def _index_dir(self) -> Path:
        return get_vault().root / SYSTEM_DIR / INDEX_SUBDIR

    async def _ensure_open(self) -> None:
        if self._table is not None:
            return
        index_dir = self._index_dir()
        index_dir.parent.mkdir(parents=True, exist_ok=True)
        self._db = lancedb.connect(str(index_dir.parent))
        if TABLE_NAME in self._db.table_names():
            self._table = self._db.open_table(TABLE_NAME)
            # Detect embedding dimension from existing table to stay consistent.
            try:
                first = self._table.to_pandas().head(1)
                if not first.empty:
                    self._dim = len(first["vector"].iloc[0])
            except Exception:  # noqa: BLE001
                pass
        else:
            # Probe the embed model once so we use the right dim on first run.
            try:
                sample = await get_llm().embed("dimension probe")
                self._dim = len(sample)
            except Exception as exc:  # noqa: BLE001
                log.warning("could not probe embed dim, defaulting to %d: %s", _EMBED_DIM, exc)
            self._table = self._db.create_table(TABLE_NAME, schema=_schema(self._dim))

    async def reindex_file(self, path: Path) -> int:
        """Re-embed a single note. Returns number of chunks written."""
        async with self._lock:
            await self._ensure_open()
            vault = get_vault()
            rel = vault.relative(path)

            self._table.delete(f"path = '{rel}'")

            if not path.exists():
                return 0
            try:
                raw = path.read_text(encoding="utf-8")
            except OSError as exc:
                log.warning("skip %s: %s", rel, exc)
                return 0

            chunks = chunk_text(raw)
            if not chunks:
                return 0
            vectors = await embed_chunks(chunks)
            mtime = path.stat().st_mtime
            rows = [
                {
                    "path": rel,
                    "chunk_id": i,
                    "text": chunk,
                    "mtime": mtime,
                    "vector": vec,
                }
                for i, (chunk, vec) in enumerate(zip(chunks, vectors, strict=True))
            ]
            self._table.add(rows)
            return len(rows)

    async def remove_file(self, path: Path) -> None:
        async with self._lock:
            await self._ensure_open()
            vault = get_vault()
            try:
                rel = vault.relative(path)
            except ValueError:
                return
            self._table.delete(f"path = '{rel}'")

    async def reindex_all(self) -> dict:
        await self._ensure_open()
        vault = get_vault()
        total_chunks = 0
        files = 0
        for path in vault.iter_notes():
            n = await self.reindex_file(path)
            total_chunks += n
            files += 1
        return {"files": files, "chunks": total_chunks}

    async def search(self, query: str, k: int = 5) -> list[dict]:
        await self._ensure_open()
        if self._table is None or self._table.count_rows() == 0:
            return []
        vector = await get_llm().embed(query)
        df = (
            self._table.search(vector)
            .limit(k)
            .to_pandas()
        )
        results: list[dict] = []
        for _, row in df.iterrows():
            results.append(
                {
                    "path": row["path"],
                    "chunk_id": int(row["chunk_id"]),
                    "score": float(row.get("_distance", 0.0)),
                    "text": row["text"],
                }
            )
        return results


_index: VaultIndex | None = None


def get_index() -> VaultIndex:
    global _index
    if _index is None:
        _index = VaultIndex()
    return _index
