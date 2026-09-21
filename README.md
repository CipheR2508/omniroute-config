# OmniRoute free-coding Portable Setup

A portable, reproducible OmniRoute configuration for the `free-coding` model combo, ready to be cloned onto any new computer.

## Quick Start

After cloning this repo:

```powershell
.\setup.ps1
```

Or on Linux/macOS:

```bash
chmod +x setup.sh
./setup.sh
```

This single command will:
1. Verify prerequisites (OmniRoute, Python/Node.js, Git)
2. Ensure the OmniRoute server is running
3. Configure the `free-coding` model combo in OmniRoute's SQLite DB
4. Remove legacy Claude profile (`ollama-local-qwen2-5-coder-7b`) and configure clean `free-coding` profile
5. Configure OpenCode with `omniroute/free-coding` as the default model

## Usage After Setup

### 1. Claude Code
Launch Claude Code using OmniRoute:
```bash
omniroute launch --profile free-coding
```
*(Or directly: `claude --profile free-coding`)*

### 2. OpenCode
Launch OpenCode directly (default model is pre-configured to `omniroute/free-coding`):
```bash
opencode
```
*(Or explicitly specify model: `opencode -m omniroute/free-coding`)*

## Managing Models in the Combo

```bash
# List current models in the combo
python create_combo.py list

# Add a model to the fallback chain
python create_combo.py add <provider> <model_slug>

# Remove a model from the chain
python create_combo.py remove <model_slug>

# Sync / refresh the combo
python create_combo.py sync
```

### Examples
```bash
# Add DeepSeek R1 from OpenRouter
python create_combo.py add openrouter deepseek/deepseek-r1:free

# Add local Ollama model
python create_combo.py add ollama-local ollama-local/qwen2.5-coder:7b
```

## Files

| File | Description |
|------|-------------|
| `create_combo.py` | Combo manager using Python standard library `sqlite3` (zero extra dependencies) |
| `create_combo.js` | Node.js wrapper that delegates to `create_combo.py` |
| `setup.ps1` | Windows automated setup script (PowerShell) |
| `setup.sh` | Linux/macOS automated setup script (Bash) |

## How It Works

1. `create_combo.py` accesses OmniRoute's local SQLite DB (`~/.omniroute/storage.sqlite`).
2. Looks up active provider connections (e.g. `ollama-cloud`, `nvidia`, `opencode`, `ollama-local`, `openrouter`).
3. Creates or updates the `free-coding` combo with a priority-based fallback strategy.
4. Generates `~/.claude/profiles/free-coding/settings.json` pointing to OmniRoute (`http://localhost:20128`) and model `free-coding`.
5. Updates `~/.config/opencode/opencode.json` with the `omniroute` provider and sets default model to `omniroute/free-coding`.
