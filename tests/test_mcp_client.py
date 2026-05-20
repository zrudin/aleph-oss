"""MCP client glue — namespacing + schema conversion, without spawning a real server."""

from __future__ import annotations

from types import SimpleNamespace

from pa.mcp.client import (
    _flatten_result,
    _to_function_schema,
    qualified_name,
    split_qualified,
)


def test_qualified_name_round_trip():
    qname = qualified_name("notion", "search")
    assert qname == "notion__search"
    assert split_qualified(qname) == ("notion", "search")


def test_split_returns_none_for_non_namespaced():
    assert split_qualified("read_file") is None
    assert split_qualified("__leading") is None
    assert split_qualified("trailing__") is None


def test_to_function_schema_uses_input_schema():
    tool = SimpleNamespace(
        name="search",
        description="Search Notion",
        inputSchema={"type": "object", "properties": {"q": {"type": "string"}}},
    )
    schema = _to_function_schema("notion", tool)
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "notion__search"
    assert schema["function"]["description"] == "Search Notion"
    assert schema["function"]["parameters"]["properties"]["q"]["type"] == "string"


def test_to_function_schema_defaults_when_no_input_schema():
    tool = SimpleNamespace(name="ping", description=None, inputSchema=None)
    schema = _to_function_schema("svc", tool)
    assert schema["function"]["parameters"] == {"type": "object", "properties": {}}
    assert schema["function"]["description"] == ""


def test_flatten_result_text_only():
    item = SimpleNamespace(text="hello", type="text")
    result = SimpleNamespace(content=[item], isError=False)
    assert _flatten_result(result) == {"text": "hello"}


def test_flatten_result_marks_errors():
    item = SimpleNamespace(text="boom", type="text")
    result = SimpleNamespace(content=[item], isError=True)
    flat = _flatten_result(result)
    assert flat["error"] is True
    assert flat["text"] == "boom"


def test_flatten_result_empty():
    result = SimpleNamespace(content=[], isError=False)
    assert _flatten_result(result) == {"text": ""}
