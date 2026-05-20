"""Search tools: semantic (via LanceDB) and exact text (via Python re)."""

from __future__ import annotations

import re

from pa.memory.index import get_index
from pa.vault.conventions import THREADS_DIR
from pa.vault.manager import get_vault


async def semantic_search(query: str, k: int = 5) -> dict:
    index = get_index()
    hits = await index.search(query, k=k)
    return {"query": query, "results": hits}


async def text_search(pattern: str, directory: str = "") -> dict:
    """Plain substring/regex search across vault markdown.

    For a v1 prototype this is good enough; we can swap in ripgrep if a vault
    grows past a few thousand notes.
    """
    vault = get_vault()
    root = vault.resolve_inside(directory) if directory else vault.root

    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        return {"error": f"invalid regex: {exc}"}

    matches: list[dict] = []
    for path in root.rglob("*.md"):
        rel = path.relative_to(vault.root)
        if any(part.startswith(".") for part in rel.parts):
            continue
        if THREADS_DIR in rel.parts:
            # Past chats have dedicated list_threads/read_thread tools.
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for lineno, line in enumerate(lines, start=1):
            if regex.search(line):
                matches.append({"path": str(rel), "line": lineno, "text": line.rstrip()})
                if len(matches) >= 50:
                    return {"pattern": pattern, "results": matches, "truncated": True}

    return {"pattern": pattern, "results": matches, "truncated": False}
