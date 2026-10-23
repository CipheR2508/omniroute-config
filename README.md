# OmniRoute inf-ai Portable Setup

A portable, reproducible OmniRoute configuration for the `inf-ai` model combo, ready to be cloned onto any new computer.

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
3. Configure the `inf-ai` model combo in OmniRoute's SQLite DB
4. Remove legacy Claude profile (`ollama-local-qwen2-5-coder-7b`) and configure clean `inf-ai` profile
5. Configure OpenCode with `omniroute/inf-ai` as the default model

## Usage After Setup

### 1. Claude Code
Launch Claude Code using OmniRoute:
```bash
omniroute launch --profile inf-ai
```
*(Or directly: `claude --profile inf-ai`)*

### 2. OpenCode
Launch OpenCode directly (default model is pre-configured to `omniroute/inf-ai`):
```bash
opencode
```
*(Or explicitly specify model: `opencode -m omniroute/inf-ai`)*

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

# Add AgentRouter model
python create_combo.py add agentrouter agentrouter/deepseek-v4-flash
```

OpenCode's free-tier models can only be used inside OpenCode and cannot be
routed through OmniRoute. If the combo reports
`OpenCode's free tier can only be used from within OpenCode`, run
`python create_combo.py sync` to remove OpenCode models from the fallback chain,
then restart your client.

## Files

| File | Description |
|------|-------------|
| `create_combo.py` | Combo manager using Python standard library `sqlite3` (zero extra dependencies) |
| `create_combo.js` | Node.js wrapper that delegates to `create_combo.py` |
| `setup.ps1` | Windows automated setup script (PowerShell) |
| `setup.sh` | Linux/macOS automated setup script (Bash) |
| `limitations.md` | Detailed list of potential failure points, environmental halts, and fallback fixes |

## Troubleshooting & Limitations

If `setup.ps1` halts or fails on a new machine (execution policy restrictions, port conflicts, uninitialized database, missing providers), consult the complete guide in [limitations.md](file:///c:/Users/lenovo/Desktop/omniroute-config/omniroute-config/limitations.md).

## How It Works

1. `create_combo.py` accesses OmniRoute's local SQLite DB (`~/.omniroute/storage.sqlite`).
2. Looks up active provider connections (e.g. `nvidia`, `agentrouter`, `openrouter`).
3. Creates or updates the `inf-ai` combo with a priority-based fallback strategy using verified free models.
4. Generates `~/.claude/profiles/inf-ai/settings.json` pointing to OmniRoute (`http://localhost:20128` by default) and model `inf-ai`.
5. Updates `~/.config/opencode/opencode.json` with the `omniroute` provider and sets default model to `omniroute/inf-ai`.

Set `OMNIROUTE_PORT` before setup if OmniRoute uses a different local port:

```powershell
$env:OMNIROUTE_PORT = "20128"
.\setup.ps1
```
