# OmniRoute Setup Script
# Run from the cloned repo directory:
#   .\setup.ps1

$ErrorActionPreference = "Stop"

# Colors for output
function Write-Status { param([string]$Message) Write-Host $Message -ForegroundColor Cyan }
function Write-Success { param([string]$Message) Write-Host $Message -ForegroundColor Green }
function Write-Warning { param([string]$Message) Write-Host $Message -ForegroundColor Yellow }
function Write-Error { param([string]$Message) Write-Host $Message -ForegroundColor Red }

Write-Host "`n╔══════════════════════════════════════════════════════════╗" -ForegroundColor Magenta
Write-Host "║          OmniRoute free-coding-stable Setup              ║" -ForegroundColor Magenta
Write-Host "╚══════════════════════════════════════════════════════════╝" -ForegroundColor Magenta
Write-Host ""

# --- Step 1: Verify prerequisites ---
Write-Status "Step 1/5: Checking prerequisites..."

$missing = @()

if (-not (Get-Command omniroute -ErrorAction SilentlyContinue)) {
    $missing += "OmniRoute CLI not found in PATH"
}
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    $missing += "Node.js not found in PATH"
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    $missing += "Git not found in PATH"
}

if ($missing.Count -gt 0) {
    Write-Error "Missing prerequisites:`n  $($missing -join "`n  ")"
    Write-Host "Please install the missing items and re-run this script." -ForegroundColor Yellow
    exit 1
}
Write-Success "  All prerequisites found."

# --- Step 2: Ensure OmniRoute server is running ---
Write-Status "Step 2/5: Checking OmniRoute server..."

$serverRunning = $false
try {
    $health = omniroute health --timeout 3000 2>&1
    if ($LASTEXITCODE -eq 0) {
        $serverRunning = $true
    }
} catch {
    $serverRunning = $false
}

if (-not $serverRunning) {
    Write-Warning "  OmniRoute server is not running. Starting it..."
    Start-Process omniroute -ArgumentList "serve" -WindowStyle Minimized
    Write-Host "  Waiting for server to become ready..." -ForegroundColor Yellow
    $maxWait = 30
    for ($i = 1; $i -le $maxWait; $i++) {
        Start-Sleep -Seconds 2
        try {
            $health = omniroute health --timeout 3000 2>&1
            if ($LASTEXITCODE -eq 0) {
                $serverRunning = $true
                break
            }
        } catch {}
        Write-Host "    Still waiting... ($i/$($maxWait/2))" -ForegroundColor DarkYellow -NoNewline
        Write-Host "`r" -NoNewline
    }
    if (-not $serverRunning) {
        Write-Error "OmniRoute server did not start within $maxWait seconds."
        exit 1
    }
    Write-Success "  OmniRoute server is ready."
} else {
    Write-Success "  OmniRoute server is already running."
}

# --- Step 3: Create/Update the free-coding-stable combo ---
Write-Status "Step 3/5: Configuring the free-coding-stable model combo..."

$nodeResult = node create_combo.js sync 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to configure combo: $nodeResult"
    exit 1
}
Write-Success "  Combo configured successfully."
Write-Host $nodeResult

# --- Step 4: Configure environment for Claude Code ---
Write-Status "Step 4/5: Configuring Claude Code environment..."

$claudeProfileDir = Join-Path $env:USERPROFILE ".claude\profiles\omniroute"
if (-not (Test-Path $claudeProfileDir)) {
    New-Item -ItemType Directory -Path $claudeProfileDir -Force | Out-Null
}

# Write env file for the profile
$envContent = @"
ANTHROPIC_BASE_URL=http://localhost:20128
ANTHROPIC_API_KEY=sk-omniroute
"@
Set-Content -Path (Join-Path $claudeProfileDir ".env") -Value $envContent -Encoding UTF8

Write-Success "  Claude Code profile written to ~/.claude/profiles/omniroute/"
Write-Host "    Activate it with: claude --profile omniroute --model free-coding-stable" -ForegroundColor Gray

# --- Step 5: Configure environment for OpenCode ---
Write-Status "Step 5/5: Configuring OpenCode environment..."

$opencodeConfigDir = Join-Path $env:USERPROFILE ".config\opencode"
if (-not (Test-Path $opencodeConfigDir)) {
    New-Item -ItemType Directory -Path $opencodeConfigDir -Force | Out-Null
}

$opencodeConfigPath = Join-Path $opencodeConfigDir "opencode.json"

# Build or update the OpenCode config
$opencodeConfig = @{
    provider = @{}
}

if (Test-Path $opencodeConfigPath) {
    try {
        $existing = Get-Content $opencodeConfigPath -Raw | ConvertFrom-Json
        $opencodeConfig = $existing
    } catch {
        Write-Warning "  Could not parse existing opencode.json, backing up and overwriting."
        Copy-Item $opencodeConfigPath "$opencodeConfigPath.bak"
    }
}

# Add/ensure the omniroute provider
$opencodeConfig.provider | Add-Member -Force -NotePropertyName "omniroute" -NotePropertyValue @{
    apiKey = "sk-omniroute"
    baseURL = "http://localhost:20128/v1"
}

$opencodeConfig | ConvertTo-Json -Depth 5 | Set-Content -Path $opencodeConfigPath -Encoding UTF8

Write-Success "  OpenCode config written to ~/.config/opencode/opencode.json"
Write-Host "    Activate it with: opencode --model omniroute/free-coding-stable" -ForegroundColor Gray

# --- Done ---
Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════════╗" -ForegroundColor Magenta
Write-Host "║  Setup complete!                                        ║" -ForegroundColor Magenta
Write-Host "╠══════════════════════════════════════════════════════════╣" -ForegroundColor Magenta
Write-Host "║                                                          ║" -ForegroundColor Magenta
Write-Host "║  Claude Code:                                           ║" -ForegroundColor Magenta
Write-Host "║    claude --profile omniroute --model free-coding-stable║" -ForegroundColor White
Write-Host "║                                                          ║" -ForegroundColor Magenta
Write-Host "║  OpenCode:                                              ║" -ForegroundColor Magenta
Write-Host "║    opencode --model omniroute/free-coding-stable        ║" -ForegroundColor White
Write-Host "║                                                          ║" -ForegroundColor Magenta
Write-Host "║  Manage models:                                         ║" -ForegroundColor Magenta
Write-Host "║    node create_combo.js add <provider> <model_slug>     ║" -ForegroundColor White
Write-Host "║    node create_combo.js remove <model_slug>            ║" -ForegroundColor White
Write-Host "║    node create_combo.js list                           ║" -ForegroundColor White
Write-Host "╚══════════════════════════════════════════════════════════╝" -ForegroundColor Magenta
