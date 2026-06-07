"""Composition root for the directory MCP server (stdio).

Opens the local SQLite directory, wraps it in the Directory facade and exposes the thin
verb tools over MCP for one local Claude Code instance.
"""

from pathlib import Path

from mcp.server.fastmcp import FastMCP
from sqlalchemy import create_engine

from directory.config import Config
from directory.mcp.api import build_mcp_server
from directory.resolve import Directory
from directory.store.api import build_directory_store


def build() -> FastMCP:
    config = Config()
    db_path = config.database_url.removeprefix("sqlite:///")
    if db_path != config.database_url:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(config.database_url)
    store = build_directory_store(engine=engine)
    return build_mcp_server(directory=Directory(store=store))


if __name__ == "__main__":
    build().run()
