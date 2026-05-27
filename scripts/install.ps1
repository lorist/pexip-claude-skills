<#
.SYNOPSIS
    Install Pexip Claude skills on Windows (PowerShell native).

.DESCRIPTION
    PowerShell equivalent of scripts/install.sh + install-one.sh for users who
    don't have Git Bash or WSL. Copies (or symlinks) skills from skills/ into
    your Claude skills directory.

    Default destination: $HOME\.claude\skills  (= %USERPROFILE%\.claude\skills,
    the same location Claude Code reads skills from on Windows).

.PARAMETER Skill
    Install only the named skill (e.g. pexip-external-policy). Omit to install
    every skill under skills/.

.PARAMETER Symlink
    Create a symbolic link instead of copying, so `git pull` updates the
    installed skill in place. Requires Windows Developer Mode or an elevated
    (Administrator) shell; falls back to a copy with a warning otherwise.

.PARAMETER Project
    Install into .\.claude\skills (relative to the current directory) instead
    of $HOME.

.PARAMETER Dest
    Explicit destination directory. Overrides -Project and the default.
    Also honoured via the CLAUDE_SKILLS_DIR environment variable.

.EXAMPLE
    .\scripts\install.ps1
    Install all skills to $HOME\.claude\skills.

.EXAMPLE
    .\scripts\install.ps1 -Skill pexip-external-policy

.EXAMPLE
    .\scripts\install.ps1 -Symlink
#>
[CmdletBinding()]
param(
    [string]$Skill,
    [switch]$Symlink,
    [switch]$Project,
    [string]$Dest
)

$ErrorActionPreference = 'Stop'

$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoDir    = Split-Path -Parent $ScriptDir
$SkillsSrc  = Join-Path $RepoDir 'skills'

if (-not (Test-Path -LiteralPath $SkillsSrc)) {
    Write-Error "No skills directory found at: $SkillsSrc"
    exit 1
}

# Resolve destination (precedence: -Dest > $env:CLAUDE_SKILLS_DIR > -Project > $HOME)
if ($Dest) {
    $DestDir = $Dest
} elseif ($env:CLAUDE_SKILLS_DIR) {
    $DestDir = $env:CLAUDE_SKILLS_DIR
} elseif ($Project) {
    $DestDir = Join-Path (Get-Location).Path '.claude\skills'
} else {
    $DestDir = Join-Path $HOME '.claude\skills'
}

New-Item -ItemType Directory -Force -Path $DestDir | Out-Null

$mode = if ($Symlink) { 'symlink' } else { 'copy' }
Write-Host "Installing skills from: $SkillsSrc"
Write-Host "                    to: $DestDir"
Write-Host "                  mode: $mode"
Write-Host ""

# Build the list of skill directories to install.
if ($Skill) {
    $skillPath = Join-Path $SkillsSrc $Skill
    if (-not (Test-Path -LiteralPath (Join-Path $skillPath 'SKILL.md'))) {
        Write-Error "Skill not found or invalid: $Skill"
        Write-Host "Available skills:" -ForegroundColor Yellow
        Get-ChildItem -Directory $SkillsSrc | ForEach-Object { Write-Host "  - $($_.Name)" }
        exit 1
    }
    $skillDirs = @(Get-Item -LiteralPath $skillPath)
} else {
    $skillDirs = Get-ChildItem -Directory $SkillsSrc
}

$count = 0
foreach ($dir in $skillDirs) {
    $name = $dir.Name
    if (-not (Test-Path -LiteralPath (Join-Path $dir.FullName 'SKILL.md'))) {
        Write-Host "  [skip] $name (no SKILL.md)" -ForegroundColor Yellow
        continue
    }

    $target = Join-Path $DestDir $name

    # Remove any existing install (file, dir, or link).
    if (Test-Path -LiteralPath $target) {
        Remove-Item -LiteralPath $target -Recurse -Force
    }

    if ($Symlink) {
        try {
            New-Item -ItemType SymbolicLink -Path $target -Target $dir.FullName -ErrorAction Stop | Out-Null
            Write-Host "  [link] $name (symlinked)" -ForegroundColor Green
        } catch {
            Write-Host "  [warn] symlink failed for $name (need Developer Mode or admin); copying instead" -ForegroundColor Yellow
            Copy-Item -LiteralPath $dir.FullName -Destination $target -Recurse -Force
            Write-Host "  [ok]   $name (copied)" -ForegroundColor Green
        }
    } else {
        Copy-Item -LiteralPath $dir.FullName -Destination $target -Recurse -Force
        Write-Host "  [ok]   $name (copied)" -ForegroundColor Green
    }
    $count++
}

Write-Host ""
Write-Host "Installed $count skill(s) to $DestDir"
Write-Host ""
Write-Host "Installed skills:"
Get-ChildItem -Directory $DestDir | ForEach-Object { Write-Host "  - $($_.Name)" }
