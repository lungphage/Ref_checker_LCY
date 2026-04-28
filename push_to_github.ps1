param(
    [string]$RepoUrl = "https://github.com/lungphage/Ref_checker_LCY.git",
    [string]$RepoDir = "_remote_repo_check",
    [string]$CommitMessage = ""
)

$ErrorActionPreference = "Stop"

$workspace = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoPath = Join-Path $workspace $RepoDir

if (-not (Test-Path $repoPath)) {
    git clone $RepoUrl $RepoDir
}

Copy-Item (Join-Path $workspace ".gitignore") (Join-Path $repoPath ".gitignore") -Force
Copy-Item (Join-Path $workspace "build_single_file.cmd") (Join-Path $repoPath "build_single_file.cmd") -Force
Copy-Item $MyInvocation.MyCommand.Path (Join-Path $repoPath "push_to_github.ps1") -Force

robocopy (Join-Path $workspace "ref_checker_windows_v5") (Join-Path $repoPath "ref_checker_windows_v5") /E /XD build dist dist_single __pycache__ /XF python-3.13.13-amd64.exe debug_log.txt | Out-Null
if ($LASTEXITCODE -gt 7) {
    throw "robocopy for ref_checker_windows_v5 failed with exit code $LASTEXITCODE"
}

robocopy (Join-Path $workspace "single_file_builder") (Join-Path $repoPath "single_file_builder") /E /XD bin obj /XF payload.zip | Out-Null
if ($LASTEXITCODE -gt 7) {
    throw "robocopy for single_file_builder failed with exit code $LASTEXITCODE"
}

Push-Location $repoPath
try {
    if (-not $CommitMessage) {
        $CommitMessage = "Update modern UI and single-file builder " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
    }

    git add .
    $status = git status --porcelain
    if (-not $status) {
        Write-Host "No changes to commit."
        exit 0
    }

    git commit -m $CommitMessage
    git push origin main
}
finally {
    Pop-Location
}
