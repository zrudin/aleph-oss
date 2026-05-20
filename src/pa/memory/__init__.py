"""Local embedding index over vault notes."""

from pa.memory.index import VaultIndex, get_index
from pa.memory.watcher import VaultWatcher

__all__ = ["VaultIndex", "VaultWatcher", "get_index"]
