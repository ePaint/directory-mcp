# Install directory-mcp into Claude Code: copy the bundled skills into your personal skills
# directory and wire the proactive-use rule into your CLAUDE.md. Windows PowerShell.
#
# The rule ships as its own file next to CLAUDE.md, imported via one @ line between markers,
# so it toggles without editing CLAUDE.md: -Disable renames the file aside (Claude Code
# skips a missing import silently); per-project opt-out is claudeMdExcludes in that project.
#
# Usage: .\install.ps1 [-NoRule | -Uninstall | -Disable | -Enable]
#   -NoRule      install the skills only; leave CLAUDE.md untouched.
#   -Uninstall   remove the skills, the rule file and the CLAUDE.md import block.
#   -Disable     turn the rule off globally (everywhere on this machine).
#   -Enable      turn it back on.
param([switch]$NoRule, [switch]$Uninstall, [switch]$Disable, [switch]$Enable)
$ErrorActionPreference = 'Stop'

$Repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$Config = if ($env:CLAUDE_CONFIG_DIR) { $env:CLAUDE_CONFIG_DIR } else { Join-Path $HOME '.claude' }
$ClaudeMd = Join-Path $Config 'CLAUDE.md'
$Rule = Join-Path $Config 'directory-rule.md'
$Begin = '<!-- directory-mcp:begin -->'
$End = '<!-- directory-mcp:end -->'

if ($Disable) {
    if (Test-Path $Rule) {
        Move-Item $Rule "$Rule.off"
        Write-Host "rule disabled globally -> $Rule.off"
    } else {
        Write-Host "nothing to disable ($Rule not found)"
    }
    exit 0
}

if ($Enable) {
    if (Test-Path "$Rule.off") {
        Move-Item "$Rule.off" $Rule
        Write-Host "rule enabled -> $Rule"
    } else {
        Write-Host "nothing to enable ($Rule.off not found)"
    }
    exit 0
}

if ($Uninstall) {
    foreach ($skill in 'directory-enroll', 'directory-graph') {
        $target = Join-Path $Config "skills\$skill"
        if (Test-Path $target) { Remove-Item -Recurse -Force $target }
        Write-Host "removed $target"
    }
    Remove-Item -Force -ErrorAction Ignore $Rule, "$Rule.off"
    if ((Test-Path $ClaudeMd) -and ((Get-Content -Raw $ClaudeMd) -like "*$Begin*")) {
        $text = Get-Content -Raw $ClaudeMd
        $pattern = "(?s)\n?$([regex]::Escape($Begin)).*?$([regex]::Escape($End))\n?"
        Set-Content -NoNewline -Path $ClaudeMd -Value ($text -replace $pattern, '')
        Write-Host "removed directory rule block from $ClaudeMd"
    }
    Write-Host "Done. The MCP registration is separate - remove it with: claude mcp remove directory"
    exit 0
}

# --- skills -----------------------------------------------------------------------------
$Dest = Join-Path $Config 'skills'
New-Item -ItemType Directory -Force -Path $Dest | Out-Null
foreach ($skill in 'directory-enroll', 'directory-graph') {
    $target = Join-Path $Dest $skill
    if (Test-Path $target) { Remove-Item -Recurse -Force $target }
    Copy-Item -Recurse (Join-Path $Repo "skills\$skill") $target
    Write-Host "installed $skill -> $target"
}

# directory-graph locates the repo relative to the skill's own directory, which only holds
# inside the plugin/checkout layout; a copy under $Config\skills needs the checkout path
# baked in instead. .Replace is a literal swap.
$graph = Join-Path $Dest 'directory-graph\SKILL.md'
$text = Get-Content -Raw $graph
$text = $text.Replace("Set ``ROOT`` to the repo root: two directories up from this skill's base directory.", "Set ``ROOT`` to ``$Repo`` (this checkout).")
Set-Content -NoNewline -Path $graph -Value $text
Write-Host "pointed /directory-graph at $Repo"

# --- proactive-use rule -----------------------------------------------------------------
if ($NoRule) {
    Write-Host "skipped CLAUDE.md rule (-NoRule)"
} else {
    Copy-Item -Force (Join-Path $Repo 'directory-rule.md') $Rule
    $import = '@./directory-rule.md'
    # Replacing (not skipping) an existing block migrates older installs that inlined the rule.
    if ((Test-Path $ClaudeMd) -and ((Get-Content -Raw $ClaudeMd) -like "*$Begin*")) {
        $text = Get-Content -Raw $ClaudeMd
        $pattern = "(?s)$([regex]::Escape($Begin)).*?$([regex]::Escape($End))"
        Set-Content -NoNewline -Path $ClaudeMd -Value ($text -replace $pattern, "$Begin`n$import`n$End")
        Write-Host "rewrote directory rule block in $ClaudeMd (single @import)"
    } else {
        Add-Content -Path $ClaudeMd -Value "`n$Begin`n$import`n$End"
        Write-Host "added directory rule import to $ClaudeMd"
    }
}

Write-Host "Done. Start a new Claude Code session to pick everything up."
