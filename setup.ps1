# OmniRoute Setup Script
# Run from the cloned repo directory:
#   .\setup.ps1

$ErrorActionPreference = "Stop"

# Colors for output
function Write-Info { param([string]$Message) Write-Host $Message -ForegroundColor Cyan }
function Write-Ok { param([string]$Message) Write-Host $Message -ForegroundColor Green }
function Write-Warn { param([string]$Message) Write-Host $Message -ForegroundColor Yellow }
function Write-Err { param([string]$Message) Write-Host $Message -ForegroundColor Red }

Write-Host ""
Write-Host "+----------------------------------------------------------+" -ForegroundColor Magenta
Write-Host "|             OmniRoute inf-ai Setup                  |" -ForegroundColor Magenta
Write-Host "+----------------------------------------------------------+" -ForegroundColor Magenta
Write-Host ""

# --- Step 1: Verify prerequisites ---
Write-Info "Step 1/5: Checking prerequisites..."

$missing = @()

if (-not (Get-Command omniroute -ErrorAction SilentlyContinue)) {
    $missing += "OmniRoute CLI not found in PATH"
}
if (-not (Get-Command python -ErrorAction SilentlyContinue) -and -not (Get-Command node -ErrorAction SilentlyContinue)) {
    $missing += "Neither Python nor Node.js found in PATH"
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    $missing += "Git not found in PATH"
}

if ($missing.Count -gt 0) {
    $missingList = $missing -join "`n  "
    Write-Err "Missing prerequisites:`n  $missingList"
    Write-Host "Please install the missing items and re-run this script." -ForegroundColor Yellow
    exit 1
}
Write-Ok "  All prerequisites found."

$omniroutePort = if ([string]::IsNullOrWhiteSpace($env:OMNIROUTE_PORT)) { "20128" } else { $env:OMNIROUTE_PORT }
if ($omniroutePort -notmatch '^[0-9]+$' -or [int]$omniroutePort -lt 1 -or [int]$omniroutePort -gt 65535) {
    Write-Err "Invalid OMNIROUTE_PORT: $omniroutePort"
    exit 1
}
Write-Info "  OmniRoute endpoint: http://localhost:$omniroutePort"

# --- Step 2: Ensure OmniRoute server is running ---
Write-Info "Step 2/5: Checking OmniRoute server..."

$serverRunning = $false
try {
    omniroute health --timeout 3000 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        $serverRunning = $true
    }
} catch {
    $serverRunning = $false
}

if (-not $serverRunning) {
    Write-Warn "  OmniRoute server is not running. Starting it..."
    Start-Process cmd.exe -ArgumentList "/c start /b omniroute serve" -WindowStyle Hidden
    Write-Host "  Waiting for server to become ready..." -ForegroundColor Yellow
    $maxWait = 15
    for ($i = 1; $i -le $maxWait; $i++) {
        Start-Sleep -Seconds 2
        try {
            omniroute health --timeout 3000 2>&1 | Out-Null
            if ($LASTEXITCODE -eq 0) {
                $serverRunning = $true
                break
            }
        } catch {}
        Write-Host "    Still waiting... ($i/$maxWait)`r" -ForegroundColor DarkYellow -NoNewline
    }
    if (-not $serverRunning) {
        Write-Err "OmniRoute did not become healthy at http://localhost:$omniroutePort after 30 seconds. Setup stopped before writing client configuration."
        Write-Host "Check the port and start the server, then run setup again." -ForegroundColor Yellow
        exit 1
    } else {
        Write-Ok "  OmniRoute server is ready."
    }
} else {
    Write-Ok "  OmniRoute server is already running."
}

# --- Step 3: Create/Update the inf-ai combo ---
Write-Info "Step 3/5: Configuring the inf-ai model combo..."

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$scriptRan = $false
if (Get-Command python -ErrorAction SilentlyContinue) {
    $comboResult = python "$scriptDir\create_combo.py" sync 2>&1
    if ($LASTEXITCODE -eq 0) {
        $scriptRan = $true
    }
}
if (-not $scriptRan -and (Get-Command node -ErrorAction SilentlyContinue)) {
    $comboResult = node "$scriptDir\create_combo.js" sync 2>&1
    if ($LASTEXITCODE -eq 0) {
        $scriptRan = $true
    }
}

if (-not $scriptRan) {
    Write-Err "Failed to configure combo: $comboResult"
    exit 1
}
Write-Ok "  Combo 'inf-ai' configured successfully."
Write-Host $comboResult

# --- Step 4: Configure Claude Code environment ---
Write-Info "Step 4/5: Configuring Claude Code profile 'inf-ai'..."

# Remove legacy profile if present
$legacyProfileDir = Join-Path $env:USERPROFILE ".claude\profiles\ollama-local-qwen2-5-coder-7b"
if (Test-Path $legacyProfileDir) {
    try {
        cmd.exe /c "rd /s /q `"$legacyProfileDir`"" 2>$null
        Write-Ok "  Removed legacy profile: ~/.claude/profiles/ollama-local-qwen2-5-coder-7b"
    } catch {
        Write-Warn "  Could not remove legacy profile folder: $_"
    }
}

$claudeProfileDir = Join-Path $env:USERPROFILE ".claude\profiles\inf-ai"
if (-not (Test-Path $claudeProfileDir)) {
    New-Item -ItemType Directory -Path $claudeProfileDir -Force | Out-Null
}

$claudeSettings = [ordered]@{
    '$schema' = 'https://json.schemastore.org/claude-code-settings.json'
    model = 'inf-ai'
    env = [ordered]@{
        ANTHROPIC_BASE_URL = "http://localhost:$omniroutePort"
        ANTHROPIC_MODEL = 'inf-ai'
        CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY = '1'
        CLAUDE_CODE_AUTO_COMPACT_WINDOW = '190000'
        CLAUDE_CODE_DISABLE_THINKING = '1'
        CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING = '1'
        DISABLE_INTERLEAVED_THINKING = '1'
    }
    alwaysThinkingEnabled = $false
    theme = 'dark'
    thinking = $false
    maxThinkingTokens = 0
} | ConvertTo-Json -Depth 5
Set-Content -Path (Join-Path $claudeProfileDir "settings.json") -Value $claudeSettings -Encoding UTF8

Write-Ok "  Claude Code profile written to ~/.claude/profiles/inf-ai/settings.json"
Write-Host "    Activate it with: omniroute launch --profile inf-ai" -ForegroundColor Gray

# --- Step 5: Configure OpenCode environment ---
Write-Info "Step 5/5: Configuring OpenCode environment..."

$opencodeConfigDir = Join-Path $env:USERPROFILE ".config\opencode"
if (-not (Test-Path $opencodeConfigDir)) {
    New-Item -ItemType Directory -Path $opencodeConfigDir -Force | Out-Null
}

$opencodeConfigPath = Join-Path $opencodeConfigDir "opencode.json"

$opencodeConfig = [ordered]@{
    '$schema' = 'https://opencode.ai/config.json'
    provider = [ordered]@{
        omniroute = [ordered]@{
            name = 'OmniRoute'
            npm = '@ai-sdk/openai-compatible'
            options = [ordered]@{
                baseURL = "http://localhost:$omniroutePort/v1"
                apiKey = 'sk-omniroute'
            }
            models = [ordered]@{
                'inf-ai' = [ordered]@{
                    name = 'inf-ai'
                    limit = [ordered]@{
                        context = 128000
                        input = 128000
                        output = 128000
                    }
                }
            }
        }
    }
    model = 'omniroute/inf-ai'
} | ConvertTo-Json -Depth 5
Set-Content -Path $opencodeConfigPath -Value $opencodeConfig -Encoding UTF8

Write-Ok "  OpenCode config written to ~/.config/opencode/opencode.json"
Write-Host "    Activate it with: opencode (default model: omniroute/inf-ai)" -ForegroundColor Gray

# --- Done ---
Write-Host ""
Write-Host "+----------------------------------------------------------+" -ForegroundColor Magenta
Write-Host "|  Setup complete!                                         |" -ForegroundColor Magenta
Write-Host "+----------------------------------------------------------+" -ForegroundColor Magenta
Write-Host "|                                                          |" -ForegroundColor Magenta
Write-Host "|  Claude Code:                                            |" -ForegroundColor Magenta
Write-Host "|    omniroute launch --profile inf-ai                |" -ForegroundColor White
Write-Host "|    (or: claude --profile inf-ai)                    |" -ForegroundColor Gray
Write-Host "|                                                          |" -ForegroundColor Magenta
Write-Host "|  OpenCode:                                               |" -ForegroundColor Magenta
Write-Host "|    opencode                                              |" -ForegroundColor White
Write-Host "|    (or: opencode -m omniroute/inf-ai)               |" -ForegroundColor Gray
Write-Host "|                                                          |" -ForegroundColor Magenta
Write-Host "|  Manage models:                                          |" -ForegroundColor Magenta
Write-Host "|    python create_combo.py add <provider> <model_slug>    |" -ForegroundColor White
Write-Host "|    python create_combo.py remove <model_slug>            |" -ForegroundColor White
Write-Host "|    python create_combo.py list                           |" -ForegroundColor White
Write-Host "+----------------------------------------------------------+" -ForegroundColor Magenta
