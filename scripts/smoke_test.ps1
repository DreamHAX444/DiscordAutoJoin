# Smoke Test Script for DiscordAutoJoin PyPI Release
# Usage: .\scripts\smoke_test.ps1
# Verifies: pip install from PyPI, import, version, CLI entry point

param(
    [string]$Version = "",
    [switch]$KeepVenv = $false
)

$ErrorActionPreference = "Stop"
$TempDir = Join-Path $env:TEMP "daj-smoke-$(Get-Random)"
$VenvDir = Join-Path $TempDir "venv"

Write-Host "=== DiscordAutoJoin Smoke Test ===" -ForegroundColor Cyan
Write-Host ""

# Step 1: Create temp directory and venv
Write-Host "[1/5] Creating clean virtual environment..." -ForegroundColor Yellow
python -m venv $VenvDir
$Python = Join-Path $VenvDir "Scripts" "python.exe"
$Pip = Join-Path $VenvDir "Scripts" "pip.exe"
& $Python -m pip install --upgrade pip --quiet
Write-Host "  OK: venv created at $VenvDir" -ForegroundColor Green

# Step 2: Install dependencies
Write-Host "[2/5] Installing runtime dependencies..." -ForegroundColor Yellow
& $Pip install playwright pystray pillow psutil --quiet
Write-Host "  OK: dependencies installed" -ForegroundColor Green

# Step 3: Install discordautojoin from PyPI
Write-Host "[3/5] Installing discordautojoin from PyPI..." -ForegroundColor Yellow
if ($Version) {
    & $Pip install --no-deps "discordautojoin==$Version"
} else {
    & $Pip install --no-deps discordautojoin
}
Write-Host "  OK: discordautojoin installed" -ForegroundColor Green

# Step 4: Verify import and version
Write-Host "[4/5] Verifying import and version..." -ForegroundColor Yellow
$output = & $Python -c "import DiscordAutoJoin; print(DiscordAutoJoin.VERSION)"
Write-Host "  Version: $output" -ForegroundColor Green
$symbols = & $Python -c "import DiscordAutoJoin; print(len([x for x in dir(DiscordAutoJoin) if not x.startswith('_')]))"
Write-Host "  Exported symbols: $symbols" -ForegroundColor Green

# Step 5: Verify CLI entry point
Write-Host "[5/5] Verifying CLI entry point..." -ForegroundColor Yellow
$cli = Join-Path $VenvDir "Scripts" "discord-autojoin.exe"
$cliOutput = & $cli --version
Write-Host "  CLI: $cliOutput" -ForegroundColor Green

# Cleanup
if (-not $KeepVenv) {
    Write-Host ""
    Write-Host "Cleaning up temp directory..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force $TempDir -ErrorAction SilentlyContinue
    Write-Host "  OK: $TempDir removed" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "Venv kept at: $VenvDir" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "=== Smoke Test PASSED ===" -ForegroundColor Green
Write-Host "DiscordAutoJoin v$output is installable and functional from PyPI." -ForegroundColor Green