param(
    [string]$ProjectRoot = "ref_checker_windows_v5",
    [string]$Configuration = "Release"
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$workspaceRoot = Split-Path -Parent $scriptDir
$projectDir = Resolve-Path (Join-Path $workspaceRoot $ProjectRoot)
$distDir = Join-Path $projectDir "dist\\ReferenceChecker"
$payloadZip = Join-Path $scriptDir "payload.zip"
$outputDir = Join-Path $projectDir "dist_single"
$outputExe = Join-Path $outputDir "ReferenceChecker.SingleFile.exe"
$programCs = Join-Path $scriptDir "Program.cs"
$cscPath = "C:\\Windows\\Microsoft.NET\\Framework64\\v4.0.30319\\csc.exe"

if (-not (Test-Path $distDir)) {
    throw "Missing onedir package: $distDir"
}

Write-Host "Preparing payload from $distDir"

if (Test-Path $payloadZip) {
    Remove-Item $payloadZip -Force
}

Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory(
    $distDir,
    $payloadZip,
    [System.IO.Compression.CompressionLevel]::Optimal,
    $false
)

if (-not (Test-Path $cscPath)) {
    throw "csc.exe was not found at $cscPath"
}

New-Item -ItemType Directory -Force $outputDir | Out-Null

Write-Host "Building single-file launcher with csc.exe"
& $cscPath `
    /nologo `
    /target:winexe `
    /optimize+ `
    /platform:anycpu `
    /out:$outputExe `
    /resource:$payloadZip `
    /r:System.dll `
    /r:System.Core.dll `
    /r:System.IO.Compression.dll `
    /r:System.IO.Compression.FileSystem.dll `
    /r:System.Windows.Forms.dll `
    $programCs

if ($LASTEXITCODE -ne 0) {
    throw "csc build failed."
}

if (-not (Test-Path $outputExe)) {
    throw "Build finished but executable was not found: $outputExe"
}

$sizeMB = [Math]::Round(((Get-Item $outputExe).Length / 1MB), 2)
Write-Host "Single-file EXE created:"
Write-Host "  $outputExe"
Write-Host "Size: $sizeMB MB"
