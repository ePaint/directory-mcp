import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="install.sh is POSIX-only")

_REPO = Path(__file__).resolve().parents[2]
_BEGIN = "<!-- directory-mcp:begin -->"
_END = "<!-- directory-mcp:end -->"
_IMPORT = "@./directory-rule.md"


def _install(config: Path, *args: str) -> str:
    env = {**os.environ, "CLAUDE_CONFIG_DIR": str(config)}
    result = subprocess.run(
        [str(_REPO / "install.sh"), *args],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def test_fresh_install_writes_skills_rule_and_import(tmp_path: Path) -> None:
    _install(tmp_path)

    assert (tmp_path / "skills" / "directory-enroll" / "SKILL.md").is_file()
    assert (tmp_path / "skills" / "directory-graph" / "SKILL.md").is_file()
    assert (tmp_path / "directory-rule.md").read_text() == (
        _REPO / "directory-rule.md"
    ).read_text()
    claude_md = (tmp_path / "CLAUDE.md").read_text()
    assert f"{_BEGIN}\n{_IMPORT}\n{_END}" in claude_md


def test_install_preserves_existing_claude_md_and_is_idempotent(tmp_path: Path) -> None:
    (tmp_path / "CLAUDE.md").write_text("# mine\nkeep me\n")

    _install(tmp_path)
    _install(tmp_path)

    claude_md = (tmp_path / "CLAUDE.md").read_text()
    assert claude_md.startswith("# mine\nkeep me\n")
    assert claude_md.count(_BEGIN) == 1


def test_install_migrates_inlined_rule_block_to_import(tmp_path: Path) -> None:
    (tmp_path / "CLAUDE.md").write_text(
        f"# mine\n\n{_BEGIN}\nOLD INLINED RULE\n{_END}\ntrailing\n"
    )

    _install(tmp_path)

    claude_md = (tmp_path / "CLAUDE.md").read_text()
    assert "OLD INLINED RULE" not in claude_md
    assert f"{_BEGIN}\n{_IMPORT}\n{_END}" in claude_md
    assert claude_md.startswith("# mine\n") and claude_md.endswith("trailing\n")


def test_no_rule_leaves_claude_md_untouched(tmp_path: Path) -> None:
    (tmp_path / "CLAUDE.md").write_text("# mine\n")

    _install(tmp_path, "--no-rule")

    assert (tmp_path / "CLAUDE.md").read_text() == "# mine\n"
    assert not (tmp_path / "directory-rule.md").exists()


def test_disable_and_enable_rename_the_rule_file(tmp_path: Path) -> None:
    _install(tmp_path)

    _install(tmp_path, "--disable")
    assert not (tmp_path / "directory-rule.md").exists()
    assert (tmp_path / "directory-rule.md.off").is_file()

    _install(tmp_path, "--enable")
    assert (tmp_path / "directory-rule.md").is_file()
    assert not (tmp_path / "directory-rule.md.off").exists()


def test_uninstall_removes_everything_but_keeps_other_content(tmp_path: Path) -> None:
    (tmp_path / "CLAUDE.md").write_text("# mine\nkeep me\n")
    _install(tmp_path)

    _install(tmp_path, "--uninstall")

    assert not (tmp_path / "skills" / "directory-enroll").exists()
    assert not (tmp_path / "skills" / "directory-graph").exists()
    assert not (tmp_path / "directory-rule.md").exists()
    claude_md = (tmp_path / "CLAUDE.md").read_text()
    assert _BEGIN not in claude_md and _IMPORT not in claude_md
    assert "keep me" in claude_md
