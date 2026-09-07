import json
import tomllib
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]


def _json(path: str) -> dict[str, object]:
    data: dict[str, object] = json.loads((_REPO / path).read_text())
    return data


def test_plugin_manifest_matches_pyproject_version() -> None:
    manifest = _json(".claude-plugin/plugin.json")
    pyproject = tomllib.loads((_REPO / "pyproject.toml").read_text())

    assert manifest["name"] == "directory-mcp"
    assert manifest["version"] == pyproject["project"]["version"]


def test_plugin_manifest_carries_catalog_metadata() -> None:
    manifest = _json(".claude-plugin/plugin.json")

    assert manifest["repository"] == "https://github.com/ePaint/directory-mcp"
    assert str(manifest["homepage"]).startswith("https://github.com/ePaint/directory-mcp")
    assert manifest["license"] == "MIT"
    assert isinstance(manifest["keywords"], list) and "mcp" in manifest["keywords"]


def test_marketplace_lists_the_plugin_at_repo_root() -> None:
    marketplace = _json(".claude-plugin/marketplace.json")

    plugins = marketplace["plugins"]
    assert isinstance(plugins, list) and len(plugins) == 1
    assert plugins[0]["name"] == "directory-mcp"
    assert plugins[0]["source"] == "./"


def test_mcp_config_runs_the_bundled_server_from_plugin_root() -> None:
    servers = _json(".claude-plugin/plugin.json")["mcpServers"]

    assert isinstance(servers, dict)
    directory = servers["directory"]
    assert directory["command"] == "uv"
    assert "${CLAUDE_PLUGIN_ROOT}" in directory["args"]
    assert "mcp_server.py" in directory["args"]
    assert "--no-dev" in directory["args"]
    assert (_REPO / "mcp_server.py").is_file()


def test_mcp_config_keeps_the_venv_outside_the_versioned_plugin_root() -> None:
    servers = _json(".claude-plugin/plugin.json")["mcpServers"]

    assert isinstance(servers, dict)
    venv = servers["directory"]["env"]["UV_PROJECT_ENVIRONMENT"]
    assert venv.startswith("${CLAUDE_PLUGIN_DATA}/")
    assert "${CLAUDE_PLUGIN_ROOT}" not in venv


def test_session_start_hook_injects_the_shipped_rule() -> None:
    hooks = _json("hooks/hooks.json")["hooks"]

    assert isinstance(hooks, dict)
    entries = hooks["SessionStart"]
    command = entries[0]["hooks"][0]["command"]
    assert "${CLAUDE_PLUGIN_ROOT}/directory-rule.md" in command
    assert (_REPO / "directory-rule.md").is_file()


def test_skills_ship_in_the_plugin_skills_dir() -> None:
    for skill in ("directory-enroll", "directory-graph"):
        assert (_REPO / "skills" / skill / "SKILL.md").is_file()
    assert not (_REPO / ".claude" / "skills").exists()
