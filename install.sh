#!/usr/bin/env bash
# Install directory-mcp into Claude Code: copy the bundled skills into your personal skills
# directory and wire the proactive-use rule into your CLAUDE.md. macOS / Linux / Git Bash / WSL.
#
# The rule ships as its own file next to CLAUDE.md, imported via one @ line between markers,
# so it toggles without editing CLAUDE.md: --disable renames the file aside (Claude Code
# skips a missing import silently); per-project opt-out is claudeMdExcludes in that project.
#
# Usage: ./install.sh [--no-rule | --uninstall | --disable | --enable]
#   --no-rule     install the skills only; leave CLAUDE.md untouched.
#   --uninstall   remove the skills, the rule file and the CLAUDE.md import block.
#   --disable     turn the rule off globally (everywhere on this machine).
#   --enable      turn it back on.
set -euo pipefail

ACTION=install
NO_RULE=0
for arg in "$@"; do
  case "$arg" in
    --no-rule) NO_RULE=1 ;;
    --uninstall) ACTION=uninstall ;;
    --disable) ACTION=disable ;;
    --enable) ACTION=enable ;;
    *) echo "unknown option: $arg (usage: ./install.sh [--no-rule | --uninstall | --disable | --enable])" >&2; exit 2 ;;
  esac
done

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
CLAUDE_MD="$CONFIG/CLAUDE.md"
RULE="$CONFIG/directory-rule.md"
BEGIN="<!-- directory-mcp:begin -->"
END="<!-- directory-mcp:end -->"

if [ "$ACTION" = disable ]; then
  if [ -f "$RULE" ]; then
    mv "$RULE" "$RULE.off"
    echo "rule disabled globally -> $RULE.off"
  else
    echo "nothing to disable ($RULE not found)"
  fi
  exit 0
fi

if [ "$ACTION" = enable ]; then
  if [ -f "$RULE.off" ]; then
    mv "$RULE.off" "$RULE"
    echo "rule enabled -> $RULE"
  else
    echo "nothing to enable ($RULE.off not found)"
  fi
  exit 0
fi

if [ "$ACTION" = uninstall ]; then
  for skill in directory-enroll directory-graph; do
    rm -rf "$CONFIG/skills/$skill"
    echo "removed $CONFIG/skills/$skill"
  done
  rm -f "$RULE" "$RULE.off"
  if [ -f "$CLAUDE_MD" ] && grep -qF "$BEGIN" "$CLAUDE_MD"; then
    tmp="$(mktemp)"
    awk -v b="$BEGIN" -v e="$END" 'index($0,b){skip=1} !skip{print} index($0,e){skip=0}' \
      "$CLAUDE_MD" > "$tmp"
    mv "$tmp" "$CLAUDE_MD"
    echo "removed directory rule block from $CLAUDE_MD"
  fi
  echo "Done. The MCP registration is separate - remove it with: claude mcp remove directory"
  exit 0
fi

# --- skills -----------------------------------------------------------------------------
DEST="$CONFIG/skills"
mkdir -p "$DEST"
for skill in directory-enroll directory-graph; do
  rm -rf "${DEST:?}/$skill"
  cp -R "$REPO/skills/$skill" "$DEST/$skill"
  echo "installed $skill -> $DEST/$skill"
done

# directory-graph locates the repo relative to the skill's own directory, which only holds
# inside the plugin/checkout layout; a copy under $CONFIG/skills needs the checkout path
# baked in instead. `#` delimits the sed expression because the repo path contains slashes.
graph="$DEST/directory-graph/SKILL.md"
tmp="$(mktemp)"
sed -e "s#Set \`ROOT\` to the repo root: two directories up from this skill's base directory.#Set \`ROOT\` to \`$REPO\` (this checkout).#" \
    "$graph" > "$tmp"
mv "$tmp" "$graph"
echo "pointed /directory-graph at $REPO"

# --- proactive-use rule -----------------------------------------------------------------
if [ "$NO_RULE" -eq 1 ]; then
  echo "skipped CLAUDE.md rule (--no-rule)"
else
  cp "$REPO/directory-rule.md" "$RULE"
  IMPORT="@./directory-rule.md"
  # Replacing (not skipping) an existing block migrates older installs that inlined the rule.
  if [ -f "$CLAUDE_MD" ] && grep -qF "$BEGIN" "$CLAUDE_MD"; then
    tmp="$(mktemp)"
    awk -v b="$BEGIN" -v e="$END" -v imp="$IMPORT" \
      'index($0,b){print; print imp; skip=1; next} index($0,e){print; skip=0; next} !skip{print}' \
      "$CLAUDE_MD" > "$tmp"
    mv "$tmp" "$CLAUDE_MD"
    echo "rewrote directory rule block in $CLAUDE_MD (single @import)"
  else
    printf '\n%s\n%s\n%s\n' "$BEGIN" "$IMPORT" "$END" >> "$CLAUDE_MD"
    echo "added directory rule import to $CLAUDE_MD"
  fi
fi

echo "Done. Start a new Claude Code session to pick everything up."
