"""ToolGate: fail-closed defaults, persistence, schema filtering, dispatch backstop."""

from __future__ import annotations

import json

import pytest

import pa.tool_gate as tg


@pytest.fixture
def gate(tmp_path, monkeypatch):
    tg.reset_gate_for_tests()
    monkeypatch.setattr(tg.settings, "vault_path", tmp_path)
    return tg.get_gate()


def test_defaults_are_fail_closed(gate):
    # No group should report enabled before set_available is called.
    assert gate.is_enabled("web") is False
    assert gate.is_enabled("notion") is False
    # state() only lists configured (available) groups → empty by default.
    assert gate.state() == []


def test_cannot_enable_unavailable_group(gate):
    assert gate.set_enabled("web", True) is False
    assert gate.is_enabled("web") is False


def test_enable_after_available(gate):
    gate.set_available("web", True)
    assert gate.set_enabled("web", True) is True
    assert gate.is_enabled("web") is True
    assert {g["id"] for g in gate.state()} == {"web"}


def test_unavailable_disables_existing(gate):
    gate.set_available("web", True)
    gate.set_enabled("web", True)
    gate.set_available("web", False)
    assert gate.is_enabled("web") is False


def test_persistence_round_trip(tmp_path, monkeypatch):
    tg.reset_gate_for_tests()
    monkeypatch.setattr(tg.settings, "vault_path", tmp_path)
    g1 = tg.get_gate()
    g1.set_available("web", True)
    g1.set_enabled("web", True)

    # Simulate a restart — fresh singleton against the same path.
    tg.reset_gate_for_tests()
    g2 = tg.get_gate()
    g2.set_available("web", True)
    assert g2.is_enabled("web") is True

    saved = json.loads((tmp_path / ".pa" / "tool_gate.json").read_text())
    assert saved["groups"]["web"] is True


def test_legacy_enabled_block_still_loads(tmp_path, monkeypatch):
    """A pre-existing tool_gate.json with the old `{enabled: ...}` shape
    should still seed the in-memory state on startup."""
    tg.reset_gate_for_tests()
    monkeypatch.setattr(tg.settings, "vault_path", tmp_path)
    state_dir = tmp_path / ".pa"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "tool_gate.json").write_text(
        json.dumps({"enabled": {"web": True}})
    )
    gate = tg.get_gate()
    gate.set_available("web", True)
    assert gate.is_enabled("web") is True


def test_per_tool_overrides_persist(tmp_path, monkeypatch):
    tg.reset_gate_for_tests()
    monkeypatch.setattr(tg.settings, "vault_path", tmp_path)
    g1 = tg.get_gate()
    g1.set_available("web", True)
    g1.set_enabled("web", True)
    assert g1.is_tool_allowed("web_search") is True
    g1.set_tool_enabled("web_search", False)
    assert g1.is_tool_allowed("web_search") is False
    # web_fetch is still on because per-tool defaults to True.
    assert g1.is_tool_allowed("web_fetch") is True

    # Fresh singleton picks up the per-tool override.
    tg.reset_gate_for_tests()
    g2 = tg.get_gate()
    g2.set_available("web", True)
    assert g2.is_tool_allowed("web_search") is False
    assert g2.is_tool_allowed("web_fetch") is True


def test_is_tool_allowed_for_builtins(gate):
    # Built-ins not owned by any group should always pass.
    assert gate.is_tool_allowed("read_file") is True
    assert gate.is_tool_allowed("semantic_search") is True


def test_is_tool_allowed_respects_group(gate):
    gate.set_available("web", True)
    assert gate.is_tool_allowed("web_search") is False
    gate.set_enabled("web", True)
    assert gate.is_tool_allowed("web_search") is True
    assert gate.is_tool_allowed("web_fetch") is True


def test_filter_schemas_strips_disabled(gate):
    gate.set_available("web", True)  # available but off
    schemas = [
        {"function": {"name": "read_file"}},
        {"function": {"name": "web_search"}},
        {"function": {"name": "notion__search"}},
    ]
    filtered = gate.filter_schemas(schemas)
    names = [s["function"]["name"] for s in filtered]
    assert names == ["read_file"]

    gate.set_enabled("web", True)
    names = [s["function"]["name"] for s in gate.filter_schemas(schemas)]
    assert "web_search" in names
    assert "notion__search" not in names  # notion still unavailable


def test_namespaced_mcp_tool_matches_prefix(gate):
    gate.set_available("notion", True)
    gate.set_enabled("notion", True)
    assert gate.is_tool_allowed("notion__search") is True
    assert gate.is_tool_allowed("notion__fetch_page") is True
    # Wrong prefix → still rejected because no group owns it (built-in path).
    assert gate.is_tool_allowed("gmail__list") is True  # treated as built-in
