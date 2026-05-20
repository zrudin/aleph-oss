"""Note model: YAML frontmatter + Markdown body, with timestamped round-trip."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import frontmatter


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass
class Note:
    path: Path
    metadata: dict = field(default_factory=dict)
    body: str = ""

    @classmethod
    def parse(cls, path: Path, content: str) -> Note:
        post = frontmatter.loads(content)
        return cls(path=Path(path), metadata=dict(post.metadata), body=post.content)

    @classmethod
    def load(cls, path: Path) -> Note:
        return cls.parse(Path(path), Path(path).read_text(encoding="utf-8"))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        now = _now_iso()
        self.metadata.setdefault("created", now)
        self.metadata["updated"] = now

        post = frontmatter.Post(self.body)
        post.metadata = dict(self.metadata)
        text = frontmatter.dumps(post)
        if not text.endswith("\n"):
            text += "\n"
        self.path.write_text(text, encoding="utf-8")


_DASH_RUN = re.compile(r"-+")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    normalised = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in normalised if not unicodedata.combining(c))
    replaced = _NON_ALNUM.sub("-", stripped.lower())
    collapsed = _DASH_RUN.sub("-", replaced).strip("-")
    return collapsed or "untitled"
