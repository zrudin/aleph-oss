"""web_search / web_fetch tools: happy paths, error handling, gate enforcement."""

from __future__ import annotations

import json

import pytest

from pa.tools import web_search as ws


@pytest.mark.asyncio
async def test_web_search_normalizes_results(monkeypatch):
    fake = [
        {"title": "A", "href": "https://a.example/", "body": "snip-a"},
        {"title": "B", "url": "https://b.example/", "body": "snip-b"},
        {"title": "no-url", "body": "skip"},
    ]
    monkeypatch.setattr(ws, "_run_blocking_search", lambda q, n, r: fake)

    result = await ws.web_search("hello", max_results=5)
    assert result["query"] == "hello"
    urls = [r["url"] for r in result["results"]]
    assert urls == ["https://a.example/", "https://b.example/"]


@pytest.mark.asyncio
async def test_web_search_rejects_empty():
    result = await ws.web_search("")
    assert "error" in result


@pytest.mark.asyncio
async def test_web_search_caps_max_results(monkeypatch):
    captured: dict = {}

    def fake(q, n, r):
        captured["n"] = n
        return []

    monkeypatch.setattr(ws, "_run_blocking_search", fake)
    await ws.web_search("x", max_results=999)
    assert captured["n"] == 10


@pytest.mark.asyncio
async def test_web_fetch_refuses_private(monkeypatch):
    # The URL guard fires before any network call.
    result = await ws.web_fetch("http://127.0.0.1:8765/")
    assert "error" in result
    assert "refused" in result["error"]


@pytest.mark.asyncio
async def test_registry_dispatch_blocks_when_gate_disabled(tmp_path, monkeypatch):
    """Even if the model emits a tool call for a disabled group, dispatch refuses."""
    import pa.tool_gate as tg

    tg.reset_gate_for_tests()
    monkeypatch.setattr(tg.settings, "vault_path", tmp_path)
    # Don't set 'web' available → it stays off.

    from pa.tools.registry import ToolCall, dispatch

    result_json = await dispatch(ToolCall(name="web_search", arguments={"query": "anything"}))
    payload = json.loads(result_json)
    assert "error" in payload
    assert "disabled" in payload["error"]


@pytest.mark.asyncio
async def test_registry_dispatch_passes_when_gate_enabled(tmp_path, monkeypatch):
    import pa.tool_gate as tg

    tg.reset_gate_for_tests()
    monkeypatch.setattr(tg.settings, "vault_path", tmp_path)
    gate = tg.get_gate()
    gate.set_available("web", True)
    gate.set_enabled("web", True)

    monkeypatch.setattr(ws, "_run_blocking_search", lambda q, n, r: [])

    from pa.tools.registry import ToolCall, dispatch

    result_json = await dispatch(ToolCall(name="web_search", arguments={"query": "hi"}))
    payload = json.loads(result_json)
    assert "error" not in payload
    assert payload["query"] == "hi"
