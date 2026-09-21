# OmniRoute free-coding-stable Portable Setup

A portable, reproducible OmniRoute configuration for the `free-coding-stable` model combo, ready to be cloned onto any new computer.

## Quick Start

After cloning this repo on a new machine:

```powershell
.\setup.ps1
```

Or on Linux/macOS:

```bash
./setup.sh
```

This single command will:
1. ✅ Verify prerequisites (OmniRoute, Node.js, Git)
2. 🚀 Start the OmniRoute server if not running
3. ⚙️  Configure the `free-coding-stable` model combo (priority fallback chain)
4. 🔧 Write Claude Code profile config
5. 🔧 Write OpenCode config

## Usage After Setup

### Claude Code
```bash
claude --profile omniroute --model free-coding-stable
```

### OpenCode
```bash
opencode --model omniroute/free-coding-stable
```

## Managing Models

```bash
# Add a new model to the fallback chain
node create_combo.js add <provider> <model_slug>

# Remove a model from the chain
node create_combo.js remove <model_slug>

# List current models in the combo
node create_combo.js list
```

### Example - Add DeepSeek R1
```bash
node create_combo.js add openrouter deepseek/deepseek-r1:free
```

## Files

| File | Description |
|------|-------------|
| `create_combo.js` | Combo manager - reads/writes to OmniRoute's SQLite DB |
| `setup.ps1` | Windows setup script (PowerShell) |
| `setup.sh` | Linux/macOS setup script (Bash) |

## How It Works

The `create_combo.js` script dynamically discovers the local OmniRoute SQLite database path based on your OS, then:

1. Looks up active provider connections (e.g., OpenRouter) in the database
2. Creates or updates the `free-coding-stable` combo with a priority-based fallback strategy
3. Maps each model to its provider connection ID automatically

All configuration lives in the repo — no secrets are stored. API keys are discovered from your existing OmniRoute provider connections.

## Prerequisites

The new computer must have pre-installed:
- **OmniRoute** (with at least one configured provider, e.g., OpenRouter)
- **Node.js** (v16+ recommended)
- **Claude Code** (with profiles support)
- **OpenCode**

## Default Models

The combo ships with these verified free models in priority order:

1. `nvidia/nemotron-3-super-120b-a12b:free` (OpenRouter)
2. `poolside/laguna-s-2.1:free` (OpenRouter)
3. `google/gemma-4-31b-it:free` (OpenRouter)
4. `openrouter/free` (OpenRouter auto-router)

## Troubleshooting

### "Failed to configure combo"
Ensure OmniRoute has at least one active provider connection configured. Run `omniroute doctor` for diagnostics.

### "OmniRoute server did not start"
Check that the OmniRoute service is installed correctly. Try running `omniroute serve` manually to see errors.

### Models not appearing
Run `node create_combo.js list` to verify the combo contents. The DB path is auto-detected from:
- `~/.omniroute/storage.sqlite` (Linux/macOS)
- `%USERPROFILE%\.omniroute\storage.sqlite` (Windows)

Override with `OMNIROUTE_DB_PATH` env var if needed.
