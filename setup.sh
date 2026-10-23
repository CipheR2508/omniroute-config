#!/usr/bin/env bash
# OmniRoute Setup Script
# Run from the cloned repo directory:
#   ./setup.sh

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
GRAY='\033[0;90m'
NC='\033[0m' # No Color

print_status() { echo -e "${CYAN}$1${NC}"; }
print_success() { echo -e "${GREEN}$1${NC}"; }
print_warning() { echo -e "${YELLOW}$1${NC}"; }
print_error() { echo -e "${RED}$1${NC}"; }

echo ""
echo -e "${MAGENTA}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${MAGENTA}║             OmniRoute inf-ai Setup                  ║${NC}"
echo -e "${MAGENTA}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""

# --- Step 1: Verify prerequisites ---
print_status "Step 1/5: Checking prerequisites..."

missing=()

if ! command -v omniroute &> /dev/null; then
    missing+=("OmniRoute CLI not found in PATH")
fi
if ! command -v python3 &> /dev/null && ! command -v python &> /dev/null && ! command -v node &> /dev/null; then
    missing+=("Neither Python nor Node.js found in PATH")
fi
if ! command -v git &> /dev/null; then
    missing+=("Git not found in PATH")
fi

if [ ${#missing[@]} -gt 0 ]; then
    print_error "Missing prerequisites:"
    printf '  %s\n' "${missing[@]}"
    echo "Please install the missing items and re-run this script."
    exit 1
fi
print_success "  All prerequisites found."

OMNIROUTE_PORT="${OMNIROUTE_PORT:-20128}"
if ! [[ "$OMNIROUTE_PORT" =~ ^[0-9]+$ ]] || [ "$OMNIROUTE_PORT" -lt 1 ] || [ "$OMNIROUTE_PORT" -gt 65535 ]; then
  print_error "Invalid OMNIROUTE_PORT: $OMNIROUTE_PORT"
  exit 1
fi
print_status "  OmniRoute endpoint: http://localhost:$OMNIROUTE_PORT"

# --- Step 2: Ensure OmniRoute server is running ---
print_status "Step 2/5: Checking OmniRoute server..."

if omniroute health --timeout 3000 &> /dev/null; then
    print_success "  OmniRoute server is already running."
else
    print_warning "  OmniRoute server is not running. Starting it..."
    omniroute serve &
    echo "  Waiting for server to become ready..."
    max_wait=30
    ready=false
    for i in $(seq 1 $max_wait); do
        sleep 2
        if omniroute health --timeout 3000 &> /dev/null; then
            print_success "  OmniRoute server is ready."
            ready=true
            break
        fi
        echo -ne "    Still waiting... ($i/$((max_wait/2)))\r"
    done
    if [ "$ready" = false ]; then
      print_error "OmniRoute did not become healthy at http://localhost:$OMNIROUTE_PORT after 30 seconds. Setup stopped before writing client configuration."
      echo "Check the port and start the server, then run setup again."
      exit 1
    fi
fi

# --- Step 3: Create/Update the inf-ai combo ---
print_status "Step 3/5: Configuring the inf-ai model combo..."

if command -v python3 &> /dev/null; then
    python3 create_combo.py sync
elif command -v python &> /dev/null; then
    python create_combo.py sync
else
    node create_combo.js sync
fi
print_success "  Combo 'inf-ai' configured successfully."

# --- Step 4: Configure Claude Code environment ---
print_status "Step 4/5: Configuring Claude Code profile 'inf-ai'..."

# Remove legacy profile if present
LEGACY_PROFILE_DIR="$HOME/.claude/profiles/ollama-local-qwen2-5-coder-7b"
if [ -d "$LEGACY_PROFILE_DIR" ]; then
    rm -rf "$LEGACY_PROFILE_DIR"
    print_success "  Removed legacy profile: ~/.claude/profiles/ollama-local-qwen2-5-coder-7b"
fi

CLAUDE_PROFILE_DIR="$HOME/.claude/profiles/inf-ai"
mkdir -p "$CLAUDE_PROFILE_DIR"

cat > "$CLAUDE_PROFILE_DIR/settings.json" << 'EOF'
{
  "$schema": "https://json.schemastore.org/claude-code-settings.json",
  "model": "inf-ai",
  "env": {
    "ANTHROPIC_BASE_URL": "http://localhost:${OMNIROUTE_PORT}",
    "ANTHROPIC_MODEL": "inf-ai",
    "CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY": "1",
    "CLAUDE_CODE_AUTO_COMPACT_WINDOW": "190000",
    "CLAUDE_CODE_DISABLE_THINKING": "1",
    "CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING": "1",
    "DISABLE_INTERLEAVED_THINKING": "1"
  },
  "alwaysThinkingEnabled": false,
  "theme": "dark",
  "thinking": false,
  "maxThinkingTokens": 0
}
EOF

print_success "  Claude Code profile written to ~/.claude/profiles/inf-ai/settings.json"
echo -e "${GRAY}    Activate it with: omniroute launch --profile inf-ai${NC}"

# --- Step 5: Configure OpenCode environment ---
print_status "Step 5/5: Configuring OpenCode environment..."

OPENCODE_CONFIG_DIR="$HOME/.config/opencode"
mkdir -p "$OPENCODE_CONFIG_DIR"

cat > "$OPENCODE_CONFIG_DIR/opencode.json" << 'EOF'
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "omniroute": {
      "name": "OmniRoute",
      "npm": "@ai-sdk/openai-compatible",
      "options": {
        "baseURL": "http://localhost:${OMNIROUTE_PORT}/v1",
        "apiKey": "sk-omniroute"
      },
      "models": {
        "inf-ai": {
          "name": "inf-ai",
          "limit": {
            "context": 128000,
            "input": 128000,
            "output": 128000
          }
        }
      }
    }
  },
  "model": "omniroute/inf-ai"
}
EOF

print_success "  OpenCode config written to ~/.config/opencode/opencode.json"
echo -e "${GRAY}    Activate it with: opencode (default model: omniroute/inf-ai)${NC}"

# --- Done ---
echo ""
echo -e "${MAGENTA}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${MAGENTA}║  Setup complete!                                        ║${NC}"
echo -e "${MAGENTA}╠══════════════════════════════════════════════════════════╣${NC}"
echo -e "${MAGENTA}║                                                          ║${NC}"
echo -e "${MAGENTA}║  Claude Code:                                           ║${NC}"
echo -e "${MAGENTA}║    omniroute launch --profile inf-ai               ║${NC}"
echo -e "${MAGENTA}║    (or: claude --profile inf-ai)                   ║${NC}"
echo -e "${MAGENTA}║                                                          ║${NC}"
echo -e "${MAGENTA}║  OpenCode:                                              ║${NC}"
echo -e "${MAGENTA}║    opencode                                             ║${NC}"
echo -e "${MAGENTA}║    (or: opencode -m omniroute/inf-ai)              ║${NC}"
echo -e "${MAGENTA}║                                                          ║${NC}"
echo -e "${MAGENTA}║  Manage models:                                         ║${NC}"
echo -e "${MAGENTA}║    python create_combo.py add <provider> <model_slug>   ║${NC}"
echo -e "${MAGENTA}║    python create_combo.py remove <model_slug>           ║${NC}"
echo -e "${MAGENTA}║    python create_combo.py list                          ║${NC}"
echo -e "${MAGENTA}╚══════════════════════════════════════════════════════════╝${NC}"
