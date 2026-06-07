#!/usr/bin/env bash
# Install directory-mcp into Claude Code: copy the bundled skills into your personal skills
# directory and add the proactive-use rule to your CLAUDE.md. macOS / Linux / Git Bash / WSL.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"

# --- skills -----------------------------------------------------------------------------
DEST="$CONFIG/skills"
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

# --- proactive-use rule -----------------------------------------------------------------
# Append the rule to CLAUDE.md between markers, idempotently — re-running won't duplicate it.
CLAUDE_MD="$CONFIG/CLAUDE.md"
BEGIN="<!-- directory-mcp:begin -->"
END="<!-- directory-mcp:end -->"
if [ -f "$CLAUDE_MD" ] && grep -qF "$BEGIN" "$CLAUDE_MD"; then
  echo "directory rule already in $CLAUDE_MD — skipping"
else
  { printf '\n%s\n' "$BEGIN"; cat "$REPO/directory-rule.md"; printf '%s\n' "$END"; } >> "$CLAUDE_MD"
  echo "added directory rule to $CLAUDE_MD"
fi

echo "Done. Start a new Claude Code session to pick everything up."
