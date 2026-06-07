"""Typed configuration for the local directory MCP."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
_DATA_DIR = Path.home() / ".local" / "share" / "directory-mcp"


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DIRECTORY_",
        env_file=_ENV_FILE,
        extra="ignore",
    )

    database_url: str = f"sqlite:///{_DATA_DIR / 'directory.db'}"
