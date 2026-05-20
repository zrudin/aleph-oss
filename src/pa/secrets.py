"""Thin wrapper over the OS keyring for connector secrets.

Service name is fixed to "pa" so all the agent's secrets live in one Keychain
group on macOS. Each connector uses a stable key (e.g., "notion_token",
"google_workspace_refresh_token").

Falls back to environment variables when the keyring backend is unusable
(e.g., headless CI). In that case set PA_SECRET_<UPPER_KEY> in the env.
"""

from __future__ import annotations

import contextlib
import logging
import os

import keyring
import keyring.errors

log = logging.getLogger(__name__)

_SERVICE = "pa"


def _env_key(key: str) -> str:
    return f"PA_SECRET_{key.upper()}"


def get_secret(key: str) -> str | None:
    env_value = os.environ.get(_env_key(key))
    if env_value:
        return env_value
    try:
        return keyring.get_password(_SERVICE, key)
    except keyring.errors.KeyringError as exc:
        log.warning("keyring read failed for %r: %s", key, exc)
        return None


def set_secret(key: str, value: str) -> None:
    keyring.set_password(_SERVICE, key, value)


def delete_secret(key: str) -> None:
    # Idempotent: not there is fine.
    with contextlib.suppress(keyring.errors.PasswordDeleteError):
        keyring.delete_password(_SERVICE, key)
