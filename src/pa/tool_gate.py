"""Runtime on/off switches for tool groups exposed to the agent.

Built-in vault tools are always on. Every external group (web, notion, ...)
is fail-closed: off until the user explicitly enables it from the UI.

State persists to <vault>/.pa/tool_gate.json so toggles survive restart.
The model is told only about *enabled* tools; dispatch also rejects calls
for disabled groups as a backstop.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from pathlib import Path

from pa.config import settings

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolGroup:
    id: str
    label: str
    description: str
    # Prefix that identifies tools in this group. Built-in web tools use plain
    # names ("web_search", "web_fetch"); MCP tools use a namespace prefix like
    # "notion__".
    tool_names: frozenset[str] = frozenset()
    tool_prefix: str | None = None

    def matches(self, tool_name: str) -> bool:
        if tool_name in self.tool_names:
            return True
        return bool(self.tool_prefix) and tool_name.startswith(self.tool_prefix or "")


# The set of *external* groups the gate manages. Built-in vault tools (read_file,
# list_reminders, semantic_search, etc.) are not listed here and are always on.
GROUPS: tuple[ToolGroup, ...] = (
    ToolGroup(
        id="web",
        label="Web search",
        description="DuckDuckGo search and fetching public web pages.",
        tool_names=frozenset({"web_search", "web_fetch"}),
    ),
    ToolGroup(
        id="notion",
        label="Notion",
        description="Read pages and databases from your Notion workspace.",
        tool_prefix="notion__",
    ),
)


def _group_by_id(group_id: str) -> ToolGroup | None:
    for g in GROUPS:
        if g.id == group_id:
            return g
    return None


def group_for_tool(tool_name: str) -> ToolGroup | None:
    for g in GROUPS:
        if g.matches(tool_name):
            return g
    return None


class ToolGate:
    """Process-wide gate. Thread-safe; persists to disk on every change.

    Two layers of toggles:
      • Group-level (`web`, `notion`, ...) — fail-closed switches for
        external tool groups. A group must also be *available* (configured)
        before it can be enabled.
      • Per-tool overrides (`{tool_name: bool}`) — fine-grained on/off
        flags surfaced in the Tools modal. Built-in tools default on; tools
        in an external group are also gated by the group's enabled flag.
    """

    def __init__(self, state_path: Path) -> None:
        self._path = state_path
        self._lock = threading.Lock()
        self._enabled: dict[str, bool] = {g.id: False for g in GROUPS}
        # Configured-ness: only groups whose backing is actually available
        # (env flag on, command set, token present) should be surfaced to the UI.
        # The agent can mark groups available at startup.
        self._available: dict[str, bool] = {g.id: False for g in GROUPS}
        # Per-tool override map. Absent → default on for known tools.
        self._tool_overrides: dict[str, bool] = {}
        self._load()

    # ----- persistence -----------------------------------------------------

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("tool_gate.json unreadable, defaulting to all-off: %s", exc)
            return
        # New schema: {"groups": {...}, "tools": {...}}
        # Old schema: {"enabled": {...}}
        groups_block = data.get("groups")
        if groups_block is None:
            groups_block = data.get("enabled", {})
        for gid in self._enabled:
            if isinstance(groups_block.get(gid), bool):
                self._enabled[gid] = groups_block[gid]
        tools_block = data.get("tools", {})
        if isinstance(tools_block, dict):
            for name, value in tools_block.items():
                if isinstance(value, bool):
                    self._tool_overrides[str(name)] = value

    def _save_locked(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(
                    {"groups": self._enabled, "tools": self._tool_overrides},
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError as exc:
            log.warning("could not persist tool gate: %s", exc)

    # ----- availability (set at startup based on config/secrets) ----------

    def set_available(self, group_id: str, available: bool) -> None:
        if group_id not in self._available:
            return
        with self._lock:
            self._available[group_id] = available
            if not available and self._enabled.get(group_id):
                # If a group becomes unavailable, also disable it so the UI
                # doesn't claim something is on that can't actually run.
                self._enabled[group_id] = False
                self._save_locked()

    # ----- public API ------------------------------------------------------

    def is_enabled(self, group_id: str) -> bool:
        with self._lock:
            return self._available.get(group_id, False) and self._enabled.get(group_id, False)

    def is_group_available(self, group_id: str) -> bool:
        with self._lock:
            return self._available.get(group_id, False)

    def is_tool_enabled(self, tool_name: str, *, default: bool = True) -> bool:
        """Per-tool flag, ignoring the group gate. Used by the catalog UI."""
        with self._lock:
            return self._tool_overrides.get(tool_name, default)

    def is_tool_allowed(self, tool_name: str) -> bool:
        """The real gate: group enabled (if any) AND per-tool flag."""
        group = group_for_tool(tool_name)
        if group is not None and not self.is_enabled(group.id):
            return False
        return self.is_tool_enabled(tool_name, default=True)

    def set_enabled(self, group_id: str, value: bool) -> bool:
        with self._lock:
            if group_id not in self._enabled:
                return False
            if value and not self._available.get(group_id, False):
                # Can't enable something that isn't configured.
                return False
            self._enabled[group_id] = bool(value)
            self._save_locked()
        return True

    def set_tool_enabled(self, tool_name: str, value: bool) -> bool:
        """Set the per-tool override. Returns False if the tool is unknown."""
        # We accept any tool name the registry knows about — caller (route)
        # validates against the live registry before calling us. Here we just
        # write the override.
        if not tool_name:
            return False
        with self._lock:
            self._tool_overrides[tool_name] = bool(value)
            self._save_locked()
        return True

    def group_state(self) -> list[dict]:
        """List configured groups with their enabled state, for the UI."""
        with self._lock:
            return [
                {
                    "id": g.id,
                    "label": g.label,
                    "description": g.description,
                    "enabled": self._enabled.get(g.id, False),
                }
                for g in GROUPS
                if self._available.get(g.id, False)
            ]

    # Backwards-compatible alias (was named `state` in the previous version).
    state = group_state

    def filter_schemas(self, schemas: list[dict]) -> list[dict]:
        """Strip schemas for tools whose group OR per-tool flag is off."""
        out: list[dict] = []
        for schema in schemas:
            name = schema.get("function", {}).get("name", "")
            if self.is_tool_allowed(name):
                out.append(schema)
        return out


_gate: ToolGate | None = None


def get_gate() -> ToolGate:
    global _gate
    if _gate is None:
        state_path = settings.vault_path / ".pa" / "tool_gate.json"
        _gate = ToolGate(state_path)
    return _gate


def reset_gate_for_tests() -> None:
    """Test helper — drop the cached singleton."""
    global _gate
    _gate = None
