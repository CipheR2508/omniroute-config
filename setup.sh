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
NC='\033[0m' # No Color

print_status() { echo -e "${CYAN}$1${NC}"; }
print_success() { echo -e "${GREEN}$1${NC}"; }
print_warning() { echo -e "${YELLOW}$1${NC}"; }
print_error() { echo -e "${RED}$1${NC}"; }

echo ""
echo -e "${MAGENTA}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${MAGENTA}║          OmniRoute free-coding-stable Setup              ║${NC}"
echo -e "${MAGENTA}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""

# --- Step 1: Verify prerequisites ---
print_status "Step 1/5: Checking prerequisites..."

missing=()

if ! command -v omniroute &> /dev/null; then
    missing+=("OmniRoute CLI not found in PATH")
fi
if ! command -v node &> /dev/null; then
    missing+=("Node.js not found in PATH")
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

# --- Step 2: Ensure OmniRoute server is running ---
print_status "Step 2/5: Checking OmniRoute server..."

if omniroute health --timeout 3000 &> /dev/null; then
    print_success "  OmniRoute server is already running."
else
    print_warning "  OmniRoute server is not running. Starting it..."
    omniroute serve &
    SERVER_PID=$!
    echo "  Waiting for server to become ready..."
    max_wait=30
    for i in $(seq 1 $max_wait); do
        sleep 2
        if omniroute health --timeout 3000 &> /dev/null; then
            print_success "  OmniRoute server is ready."
            break
        fi
        echo -ne "    Still waiting... ($i/$((max_wait/2)))\r"
    done
    if ! omniroute health --timeout 3000 &> /dev/null; then
        print_error "OmniRoute server did not start within $max_wait seconds."
        exit 1
    fi
fi

# --- Step 3: Create/Update the free-coding-stable combo ---
print_status "Step 3/5: Configuring the free-coding-stable model combo..."

if ! node create_combo.js sync; then
    print_error "Failed to configure combo."
    exit 1
fi
print_success "  Combo configured successfully."

# --- Step 4: Configure environment for Claude Code ---
print_status "Step 4/5: Configuring Claude Code environment..."

CLAUDE_PROFILE_DIR="$HOME/.claude/profiles/omniroute"
mkdir -p "$CLAUDE_PROFILE_DIR"

cat > "$CLAUDE_PROFILE_DIR/.env" << 'EOF'
ANTHROPIC_BASE_URL=http://localhost:20128
ANTHROPIC_API_KEY=sk-omniroute
EOF

print_success "  Claude Code profile written to ~/.claude/profiles/omniroute/"
echo "    Activate it with: claude --profile omniroute --model free-coding-stable"

# --- Step 5: Configure environment for OpenCode ---
print_status "Step 5/5: Configuring OpenCode environment..."

OPENCODE_CONFIG_DIR="$HOME/.config/opencode"
mkdir -p "$OPENCODE_CONFIG_DIR"

OPENCODE_CONFIG_PATH="$OPENCODE_CONFIG_DIR/opencode.json"

# Build or update the OpenCode config
if [ -f "$OPENCODE_CONFIG_PATH" ]; then
    # Backup existing
    cp "$OPENCODE_CONFIG_PATH" "$OPENCODE_CONFIG_PATH.bak"
fi

# Use node to merge JSON (since jq may not be available)
node -e "
const fs = require('fs');
const path = '$OPENCODE_CONFIG_PATH';
let config = {};
try { config = JSON.parse(fs.readFileSync(path, 'utf8')); } catch(e) {}
if (!config.provider) config.provider = {};
config.provider.omniroute = {
    apiKey: 'sk-omniroute',
    baseURL: 'http://localhost:20128/v1'
};
fs.writeFileSync(path, JSON.stringify(config, null, 2));
"

print_success "  OpenCode config written to ~/.config/opencode/opencode.json"
echo "    Activate it with: opencode --model omniroute/free-coding-stable"

# --- Done ---
echo ""
echo -e "${MAGENTA}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${MAGENTA}║  Setup complete!                                        ║${NC}"
echo -e "${MAGENTA}╠══════════════════════════════════════════════════════╣${NC}"
echo -e "${MAGENTA}║                                                          ║${NC}"
echo -e "${MAGENTA}║  Claude Code:                                           ║${NC}"
echo -e "${MAGENTA}║    claude --profile omniroute --model free-coding-stable${NC}"
echo -e "${MAGENTA}║                                                          ║${NC}"
echo -e "${MAGENTA}║  OpenCode:                                              ║${NC}"
echo -e "${MAGENTA}║    opencode --model omniroute/free-coding-stable        ║${NC}"
echo -e "${MAGENTA}║                                                          ║${NC}"
echo -e "${MAGENTA}║  Manage models:                                         ║${NC}"
echo -e "${MAGENTA}║    node create_combo.js add <provider> <model_slug>     ║${NC}"
echo -e "${MAGENTA}║    node create_combo.js remove <model_slug>            ║${NC}"
echo -e "${MAGENTA}║    node create_combo.js list                           ║${NC}"
echo -e "${MAGENTA}╚══════════════════════════════════════════════════════════╝${NC}"
