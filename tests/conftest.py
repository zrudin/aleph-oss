"""Shared pytest fixtures — primarily a temp vault that real code can run against.

The vault fixture is only defined when `pa.vault.manager` is importable, so
tests for unrelated modules (web tools, gate, net, MCP) can still run before
the vault module lands.
"""

from __future__ import annotations

from pathlib import Path

import pytest

try:
    from pa.vault.manager import VaultManager  # type: ignore[import-not-found]
except ModuleNotFoundError:
    VaultManager = None  # type: ignore[assignment,misc]


if VaultManager is not None:

    @pytest.fixture
    def temp_vault(tmp_path: Path, monkeypatch):
        """A fully bootstrapped vault rooted at a pytest tmp_path."""
        vault = VaultManager(root=tmp_path)
        vault.bootstrap()

        # Replace the module-level singleton so tools and the agent see this vault.
        import pa.vault.manager as vm

        monkeypatch.setattr(vm, "_vault", vault)
        return vault
