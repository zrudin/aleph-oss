"""Note chunking + embedding via Ollama.

Chunks are split on Markdown headings with a soft cap so a chunk fits into a
single embedding call comfortably. The note's YAML frontmatter is prepended to
every chunk so structured metadata is searchable alongside prose.
"""

from __future__ import annotations

import re

import frontmatter

from pa.llm import get_llm

_HEADING_RE = re.compile(r"^(#{1,6})\s+.+$", re.MULTILINE)
_CHUNK_SOFT_LIMIT = 800


def chunk_text(raw: str) -> list[str]:
    """Split a note into chunks suitable for embedding."""
    post = frontmatter.loads(raw)
    fm_header = ""
    if post.metadata:
        fm_header = "\n".join(f"{k}: {v}" for k, v in post.metadata.items()) + "\n\n"
    body = post.content.strip()
    if not body:
        return []

    # Split at headings; keep heading with the section.
    positions = [m.start() for m in _HEADING_RE.finditer(body)]
    if not positions or positions[0] != 0:
        positions = [0, *positions]
    positions.append(len(body))

    sections: list[str] = []
    for i in range(len(positions) - 1):
        section = body[positions[i] : positions[i + 1]].strip()
        if section:
            sections.append(section)

    # Pack sections so each chunk stays under the soft limit.
    chunks: list[str] = []
    buf = ""
    for section in sections:
        if len(buf) + len(section) + 2 > _CHUNK_SOFT_LIMIT and buf:
            chunks.append(buf)
            buf = section
        else:
            buf = f"{buf}\n\n{section}".strip()
    if buf:
        chunks.append(buf)

    return [fm_header + c for c in chunks]


async def embed_chunks(chunks: list[str]) -> list[list[float]]:
    llm = get_llm()
    return await llm.embed_many(chunks)
