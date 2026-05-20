"""Application settings, sourced from environment variables (.env file supported)."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ollama_host: str = Field(default="http://127.0.0.1:11434", alias="OLLAMA_HOST")
    chat_model: str = Field(default="qwen2.5:32b-instruct-q4_K_M", alias="PA_CHAT_MODEL")
    embed_model: str = Field(default="nomic-embed-text", alias="PA_EMBED_MODEL")

    vault_path: Path = Field(default=Path("/Volumes/PA-Vault"), alias="PA_VAULT_PATH")
    # When true, the vault path must be a real macOS mount point. `make dev`
    # flips this off so the app can run against a plain directory.
    require_mount: bool = Field(default=True, alias="PA_VAULT_REQUIRE_MOUNT")

    host: str = Field(default="127.0.0.1", alias="PA_HOST")
    port: int = Field(default=8765, alias="PA_PORT")

    max_tool_iterations: int = Field(default=8, alias="PA_MAX_TOOL_ITERATIONS")
    history_turns: int = Field(default=20, alias="PA_HISTORY_TURNS")

    log_level: str = Field(default="INFO", alias="PA_LOG_LEVEL")

    # External capabilities. Off by default; toggle on at runtime from the UI.
    enable_web: bool = Field(default=True, alias="PA_ENABLE_WEB")
    enable_notion: bool = Field(default=False, alias="PA_ENABLE_NOTION")
    notion_mcp_command: str | None = Field(default=None, alias="PA_NOTION_MCP_COMMAND")

    web_max_fetch_bytes: int = Field(default=16 * 1024 * 1024, alias="PA_WEB_MAX_FETCH_BYTES")
    web_search_max_retries: int = Field(default=3, alias="PA_WEB_SEARCH_MAX_RETRIES")
    web_search_region: str = Field(default="wt-wt", alias="PA_WEB_SEARCH_REGION")


settings = Settings()
