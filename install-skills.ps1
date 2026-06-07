# Install the bundled Claude Code skills into your personal skills directory so they work
# from any project, not only inside this repo. Windows PowerShell.
$ErrorActionPreference = 'Stop'

$Repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$Dest = if ($env:CLAUDE_CONFIG_DIR) { Join-Path $env:CLAUDE_CONFIG_DIR 'skills' } else { Join-Path $HOME '.claude\skills' }
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
$text = $text.Replace('scripts/graph/directory-graph.html', (Join-Path $Repo 'scripts\graph\directory-graph.html'))
Set-Content -NoNewline -Path $graph -Value $text
Write-Host "pointed /directory-graph at $Repo"

Write-Host "Done. Start a new Claude Code session to pick up the skills."
