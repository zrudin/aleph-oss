"""Helpers in pa.llm that don't require an Ollama server."""

from __future__ import annotations

from pa.llm import installed_model_names, model_installed


class _FakeModel:
    """Imitates the ollama-python Model pydantic object: name on `.model`."""

    def __init__(self, name: str) -> None:
        self.model = name


class _FakeListResponse:
    """Imitates ollama-python ListResponse: models on `.models`."""

    def __init__(self, names: list[str]) -> None:
        self.models = [_FakeModel(n) for n in names]


def test_installed_model_names_from_listresponse_object():
    listed = _FakeListResponse(["qwen2.5:32b-instruct-q4_K_M", "nomic-embed-text:latest"])
    assert installed_model_names(listed) == [
        "qwen2.5:32b-instruct-q4_K_M",
        "nomic-embed-text:latest",
    ]


def test_installed_model_names_from_legacy_dict():
    listed = {"models": [{"name": "foo:1"}, {"model": "bar:2"}]}
    assert installed_model_names(listed) == ["foo:1", "bar:2"]


def test_installed_model_names_handles_empty_and_missing():
    assert installed_model_names(None) == []
    assert installed_model_names({}) == []
    assert installed_model_names({"models": []}) == []
    assert installed_model_names(_FakeListResponse([])) == []


def test_model_installed_exact_match():
    assert model_installed("qwen2.5:32b-instruct-q4_K_M", {"qwen2.5:32b-instruct-q4_K_M"})
    assert not model_installed("qwen2.5:7b", {"qwen2.5:32b-instruct-q4_K_M"})


def test_model_installed_bare_name_maps_to_latest():
    # Configured without a tag should match the :latest that ollama stores.
    assert model_installed("nomic-embed-text", {"nomic-embed-text:latest"})


def test_model_installed_tagged_name_does_not_silently_match_latest():
    # If the config explicitly asks for a tag, don't fall back to :latest.
    assert not model_installed("nomic-embed-text:v1.5", {"nomic-embed-text:latest"})


def test_model_installed_accepts_list_input():
    assert model_installed("foo", ["foo:latest", "bar:latest"])
    assert not model_installed("baz", ["foo:latest", "bar:latest"])
