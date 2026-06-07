#!/usr/bin/env bash
# Install the bundled Claude Code skills into your personal skills directory so they work
# from any project, not only inside this repo. macOS / Linux / Git Bash / WSL.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills"
mkdir -p "$DEST"

for skill in directory-enroll directory-graph; do
  rm -rf "${DEST:?}/$skill"
  cp -R "$REPO/.claude/skills/$skill" "$DEST/$skill"
  echo "installed $skill -> $DEST/$skill"
done

# directory-graph runs the bundled renderer by relative path; point the installed copy at
# this checkout so it resolves from any working directory. `#` delimits the sed expression
# because the repo path contains slashes.
graph="$DEST/directory-graph/SKILL.md"
tmp="$(mktemp)"
sed -e "s#uv run python scripts/graph/build_graph.py#uv run --directory \"$REPO\" python scripts/graph/build_graph.py#g" \
    -e "s#scripts/graph/directory-graph.html#$REPO/scripts/graph/directory-graph.html#g" \
    "$graph" > "$tmp"
mv "$tmp" "$graph"
echo "pointed /directory-graph at $REPO"

echo "Done. Start a new Claude Code session to pick up the skills."
