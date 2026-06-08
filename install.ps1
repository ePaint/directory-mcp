# Install directory-mcp into Claude Code: copy the bundled skills into your personal skills
# directory and add the proactive-use rule to your CLAUDE.md. Windows PowerShell.
#
# Usage: .\install.ps1 [-NoRule]
#   -NoRule   install the skills only; leave CLAUDE.md untouched.
param([switch]$NoRule)
$ErrorActionPreference = 'Stop'

$Repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$Config = if ($env:CLAUDE_CONFIG_DIR) { $env:CLAUDE_CONFIG_DIR } else { Join-Path $HOME '.claude' }

# --- skills -----------------------------------------------------------------------------
$Dest = Join-Path $Config 'skills'
New-Item -ItemType Directory -Force -Path $Dest | Out-Null
foreach ($skill in 'directory-enroll', 'directory-graph') {
    $target = Join-Path $Dest $skill
    if (Test-Path $target) { Remove-Item -Recurse -Force $target }
    Copy-Item -Recurse (Join-Path $Repo ".claude\skills\$skill") $target
    Write-Host "installed $skill -> $target"
}

# directory-graph runs the bundled renderer by relative path; point the installed copy at
# this checkout so it resolves from any working directory. .Replace is a literal swap.
$graph = Join-Path $Dest 'directory-graph\SKILL.md'
$text = Get-Content -Raw $graph
$text = $text.Replace('uv run python scripts/graph/build_graph.py', "uv run --directory `"$Repo`" python scripts/graph/build_graph.py")
$text = $text.Replace('scripts/graph/directory-graph.html', '"' + (Join-Path $Repo 'scripts\graph\directory-graph.html') + '"')
Set-Content -NoNewline -Path $graph -Value $text
Write-Host "pointed /directory-graph at $Repo"

# --- proactive-use rule -----------------------------------------------------------------
# Append the rule to CLAUDE.md between markers, idempotently -- re-running won't duplicate it.
$ClaudeMd = Join-Path $Config 'CLAUDE.md'
$Begin = '<!-- directory-mcp:begin -->'
$End = '<!-- directory-mcp:end -->'
if ($NoRule) {
    Write-Host "skipped CLAUDE.md rule (-NoRule)"
} elseif ((Test-Path $ClaudeMd) -and ((Get-Content -Raw $ClaudeMd) -like "*$Begin*")) {
    Write-Host "directory rule already in $ClaudeMd - skipping"
} else {
    $rule = Get-Content -Raw (Join-Path $Repo 'directory-rule.md')
    Add-Content -Path $ClaudeMd -Value "`n$Begin`n$rule$End"
    Write-Host "added directory rule to $ClaudeMd"
}

Write-Host "Done. Start a new Claude Code session to pick everything up."
