# Potential Failure Points & Limitations for `setup.ps1`

This document details every potential failure point, environment halt, and fallback scenario when executing `setup.ps1` on a new or different machine, along with diagnostic indicators and resolutions.

---

## 1. PowerShell Execution Policy Restrictions

### Symptom
When running `.\setup.ps1` on a clean Windows machine, PowerShell immediately blocks execution with:
```text
File ...\setup.ps1 cannot be loaded because running scripts is disabled on this system.
```

### Cause
Windows sets the default PowerShell execution policy to `Restricted` for client versions of Windows.

### Fallback / Resolution
Run PowerShell with an execution policy bypass:
```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```
Or temporarily allow script execution in the current terminal session:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\setup.ps1
```

---

## 2. Missing Prerequisites in System PATH (Step 1/5)

### Symptom
The script halts immediately at Step 1 with:
```text
Missing prerequisites:
  OmniRoute CLI not found in PATH
  Neither Python nor Node.js found in PATH
  Git not found in PATH
```

### Potential Causes
1. **OmniRoute not installed globally**: OmniRoute was installed locally without `-g` or npm global binaries are not in system PATH:
   - Typical npm path: `%APPDATA%\npm`
2. **Python installed without PATH checked**: On Windows, the Python installer leaves "Add python.exe to PATH" **unchecked by default**.
3. **Node.js without npm in PATH**: Node.js was unpacked as a standalone zip rather than the MSI installer.

### Fallback / Resolution
- Install OmniRoute globally:
  ```powershell
  npm install -g omniroute
  ```
- Re-run the Python installer and ensure **"Add python.exe to PATH"** is selected.
- Restart your terminal after altering system PATH variables so PowerShell loads the new environment.

---

## 3. OmniRoute Server & Port Issues (Step 2/5)

### Symptom
The script halts or times out after 30 seconds:
```text
OmniRoute server is not running. Starting it...
Waiting for server to become ready...
  Still waiting... (15/15)
```
Claude Code may also report `ECONNREFUSED` when its configured local URL does not match a running OmniRoute server.

### Potential Causes
1. **Configured port already occupied**: Another application or an orphaned OmniRoute background process is using the configured port (default `20128`).
2. **Windows Defender / Third-party Antivirus / Firewall**: Blocks Node.js from binding to local ports or spawning background commands via `cmd.exe /c start /b`.
3. **Slow disk / First-time initialization**: The first initialization of OmniRoute may take longer than the 30-second loop if running on slow HDD storage or under heavy CPU load.

### Fallback / Resolution
- Check OmniRoute health:
  ```powershell
  omniroute health --timeout 3000
  ```
- Confirm the Claude profile points to the configured port (default `20128`):
  ```powershell
  (Get-Content "$env:USERPROFILE\.claude\profiles\inf-ai\settings.json" -Raw | ConvertFrom-Json).env.ANTHROPIC_BASE_URL
  ```
  It should print `http://localhost:20128`. If it is stale, rerun `setup.ps1` after confirming the server is healthy; setup regenerates the Claude and OpenCode config files.
- If health fails, check which process owns the configured port:
  ```powershell
  Get-NetTCPConnection -State Listen -LocalPort 20128 -ErrorAction SilentlyContinue | Select-Object LocalAddress, LocalPort, OwningProcess
  ```
- If there is no listener, start OmniRoute in a PowerShell window and leave it running:
  ```powershell
  omniroute serve
  ```
  In another window, wait until `omniroute health --timeout 3000` reports healthy, then run `setup.ps1` and launch Claude with `omniroute launch --profile inf-ai`. Do not start a second server when a listener already exists; that causes `EADDRINUSE`.
- If OmniRoute is intentionally configured to use another port, set the same port before setup:
  ```powershell
  $env:OMNIROUTE_PORT = "<configured-port>"
  .\setup.ps1
  ```

---

## 4. SQLite Database Initialization & Locking (Step 3/5)

### Symptom
`create_combo.py` fails with one of:
```text
FileNotFoundError: OmniRoute database not found at: C:\Users\...\.omniroute\storage.sqlite
```
or
```text
sqlite3.OperationalError: database is locked
```

### Potential Causes
1. **Fresh Machine / Database Not Yet Created**:
   - If OmniRoute has never run before on the new machine, `~/.omniroute/storage.sqlite` will not exist until `omniroute serve` executes its initial migrations.
2. **Database Locked by Active Process**:
   - SQLite allows only one writer at a time. If OmniRoute is actively writing sync tokens or running migrations, Python's SQLite connection may raise a lock error.
3. **Custom User Profile Paths**:
   - Corporate machines using OneDrive redirection, folder redirection, or non-ASCII characters in username (e.g. `C:\Users\Jürgen\`) can cause path discovery discrepancies between `%USERPROFILE%` and Python's `os.path.expanduser`.

### Fallback / Resolution
- Set the database path explicitly via environment variable:
  ```powershell
  $env:OMNIROUTE_DB_PATH = "$env:USERPROFILE\.omniroute\storage.sqlite"
  python create_combo.py sync
  ```
- If the database file is missing, start OmniRoute once manually (`omniroute serve`) to let it generate the initial schema, then re-run setup.

---

## 5. Clean Machine with Zero Configured Providers (Step 3/5)

### Symptom
Setup completes, but when calling the model in Claude Code or OpenCode, you get:
```text
No active credentials for provider: nvidia / openrouter
```

### Cause
On a fresh computer, OmniRoute's `provider_connections` table has zero credentials. While `setup.ps1` configures the combo structure, it cannot fabricate API keys.

### Fallback / Resolution
At least one provider must be authenticated in OmniRoute before models will respond:
```powershell
# Add your preferred free provider:
omniroute provider add nvidia
# or
omniroute provider add openrouter
```
Once linked, re-run `python create_combo.py sync` to bind the new connection ID to the combo.

---

## 6. OpenCode Free-Tier Provider Error

### Symptom
OpenCode reports:
```text
OpenCode's free tier can only be used from within OpenCode
```

### Cause
The `inf-ai` fallback chain contains an OpenCode-hosted free-tier model. OpenCode
restricts those models to requests made within OpenCode, so they cannot be used
as a backend through OmniRoute.

### Fallback / Resolution
Update the combo to remove models from the OpenCode provider, then restart the
client:
```powershell
python create_combo.py sync
```

---

## 7. OpenCode Config Overwrite (Step 5/5)

### Symptom
Existing OpenCode configurations (custom themes, other providers, custom keybindings) get wiped out.

### Cause
`setup.ps1` writes a fresh `~/.config/opencode/opencode.json` using `Set-Content`. On a machine where OpenCode was already customized, this overwrites existing provider blocks.

### Fallback / Resolution
Back up existing OpenCode configuration before running `setup.ps1`:
```powershell
if (Test-Path "$env:USERPROFILE\.config\opencode\opencode.json") {
    Copy-Item "$env:USERPROFILE\.config\opencode\opencode.json" "$env:USERPROFILE\.config\opencode\opencode.json.bak"
}
```

---

## 8. File In-Use / File Lock (Step 4/5)

### Symptom
Step 4 fails with:
```text
The process cannot access the file because it is being used by another process.
```

### Cause
If Claude Code or OpenCode is actively running while `setup.ps1` executes, the process may hold open file handles to `settings.json` or legacy profile folders.

### Fallback / Resolution
Close any active Claude Code or OpenCode terminal windows before running `setup.ps1`.

---

## 9. Combo Falls Back Into Broken Models

### Symptom
Requests routed through `inf-ai` end with one of these instead of an answer:
```text
[400]: <model> is not a valid model ID
[404]: The model `<model>` does not exist or you do not have access to it
[429]: All credentials for model <model> are cooling down
[503]: Service temporarily unavailable: all upstream accounts are inactive
[504]: upstream timed out
```

### Cause
OmniRoute treats every non-OK upstream response as a reason to try the next
combo target. If the chain contains stale model IDs, expired free models, or
providers that are down/quota-exhausted, those errors become the chain's steady
state (and one bad model can put its whole provider into cooldown).

### Automatic Protection
`python create_combo.py sync` now rebuilds the chain instead of keeping old
entries:
- only providers with an **active connection** are used,
- only models present in the provider's **synced catalog** are used,
- models whose recent `call_logs` show no success, a failed last attempt, or
  only stale results are skipped,
- the combo runs with `maxRetries: 0`, `failoverBeforeRetry: true` and
  per-target health checks, so a broken target is skipped rather than retried.

The excluded models and the exact reason are printed by `sync`, e.g.
```text
[SKIPPED] Models excluded to avoid missing-model / uptime / API errors:
  - [gemini] gemini-3.8-flash: 3 recent attempts without a success (last HTTP 499)
```

### Fallback / Resolution
- Run `python create_combo.py sync` after adding or re-authenticating a provider.
- If a provider is temporarily down, wait for it to recover, make one successful
  call (or `omniroute test <provider> <model>`), then `sync` again. Models with a
  recent success are re-added automatically.
- Change `VERIFIED_MODELS` in `create_combo.py` to add or remove candidates.
- If every candidate is skipped, `sync` warns and keeps all catalog-valid models
  on active providers, so the combo is never empty.
- `add`/`remove` are temporary: the next `sync` rebuilds from `VERIFIED_MODELS`.

---

## Summary Matrix

| Failure Stage | Primary Cause | Automatic Fallback in Script | Manual Fix |
|:---|:---|:---:|:---|
| **Script Launch** | Execution Policy | ❌ None | `powershell -ExecutionPolicy Bypass -File .\setup.ps1` |
| **Prerequisites** | Missing PATH entries | ❌ Halts with error | Install tool / add to system PATH |
| **Server Health** | Configured port conflict / timeout | ❌ Retries 15 times, then halts before writing client config | Check health and the configured port; don't start a duplicate server |
| **Database** | DB file doesn't exist yet | ❌ Halts | Launch `omniroute serve` once to initialize DB |
| **Providers** | Zero credentials on new machine | ⚠️ Configures chain with null IDs | Run `omniroute provider add <name>` |
| **Combo Health** | Stale model IDs / dead providers in chain | ✅ Rebuilds from verified, catalog-valid models and skips recent failures | Run `python create_combo.py sync` after a provider recovers |
| **Config Write** | File locked by running Claude | ⚠️ Catches error, prints warning | Exit active Claude sessions |
