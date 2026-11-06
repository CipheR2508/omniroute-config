import os
import sys
import json
import shutil
import sqlite3
import subprocess
import pytest

POWERSHELL_EXE = shutil.which("powershell.exe") or "powershell"
SETUP_PS1_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "setup.ps1"))

@pytest.fixture
def mock_bin_dir(tmp_path):
    """Creates a temporary bin directory with a mock omniroute executable for testing."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    # Batch script for mock omniroute on Windows
    mock_cmd = bin_dir / "omniroute.cmd"
    mock_cmd.write_text(
        "@echo off\r\n"
        "if \"%1\"==\"health\" (\r\n"
        "    echo healthy\r\n"
        "    exit /b 0\r\n"
        ")\r\n"
        "if \"%1\"==\"serve\" (\r\n"
        "    exit /b 0\r\n"
        ")\r\n"
        "exit /b 0\r\n"
    )
    return str(bin_dir)

@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell script integration test runs on Windows")
def test_setup_ps1_invalid_port(tmp_path):
    env = os.environ.copy()
    env["OMNIROUTE_PORT"] = "99999"

    proc = subprocess.run(
        [POWERSHELL_EXE, "-ExecutionPolicy", "Bypass", "-File", SETUP_PS1_PATH],
        capture_output=True,
        text=True,
        env=env
    )
    assert proc.returncode == 1
    assert "Invalid OMNIROUTE_PORT: 99999" in proc.stdout

@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell script integration test runs on Windows")
def test_setup_ps1_missing_prerequisite(tmp_path):
    # Set PATH to empty directory so omniroute is not found
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    env = os.environ.copy()
    env["PATH"] = str(empty_dir)

    proc = subprocess.run(
        [POWERSHELL_EXE, "-ExecutionPolicy", "Bypass", "-File", SETUP_PS1_PATH],
        capture_output=True,
        text=True,
        env=env
    )
    assert proc.returncode == 1
    assert "Missing prerequisites:" in proc.stdout
    assert "OmniRoute CLI not found in PATH" in proc.stdout

@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell script integration test runs on Windows")
def test_setup_ps1_end_to_end_success(tmp_path, populated_db_path, mock_bin_dir):
    temp_userprofile = tmp_path / "userhome"
    temp_userprofile.mkdir()

    # Pre-create legacy profile directory to verify cleanup
    legacy_profile = temp_userprofile / ".claude" / "profiles" / "ollama-local-qwen2-5-coder-7b"
    legacy_profile.mkdir(parents=True)
    (legacy_profile / "settings.json").write_text("{}", encoding="utf-8")

    env = os.environ.copy()
    env["USERPROFILE"] = str(temp_userprofile)
    env["OMNIROUTE_DB_PATH"] = populated_db_path
    env["OMNIROUTE_PORT"] = "20128"
    # Prepend mock bin dir to PATH so our mock omniroute is invoked
    env["PATH"] = mock_bin_dir + os.pathsep + env.get("PATH", "")

    proc = subprocess.run(
        [POWERSHELL_EXE, "-ExecutionPolicy", "Bypass", "-File", SETUP_PS1_PATH],
        capture_output=True,
        text=True,
        env=env
    )

    assert proc.returncode == 0, f"Script failed with output:\n{proc.stdout}\n{proc.stderr}"
    assert "Step 1/5: Checking prerequisites..." in proc.stdout
    assert "Step 2/5: Checking OmniRoute server..." in proc.stdout
    assert "Step 3/5: Configuring the inf-ai model combo..." in proc.stdout
    assert "Step 4/5: Configuring Claude Code profile 'inf-ai'..." in proc.stdout
    assert "Step 5/5: Configuring OpenCode environment..." in proc.stdout
    assert "Setup complete!" in proc.stdout

    # 1. Verify legacy profile was removed
    assert not legacy_profile.exists()

    # 2. Verify Claude profile settings.json
    claude_settings_file = temp_userprofile / ".claude" / "profiles" / "inf-ai" / "settings.json"
    assert claude_settings_file.exists()
    claude_cfg = json.loads(claude_settings_file.read_text(encoding="utf-8"))
    assert claude_cfg["model"] == "inf-ai"
    assert claude_cfg["env"]["ANTHROPIC_BASE_URL"] == "http://localhost:20128"
    assert claude_cfg["env"]["ANTHROPIC_MODEL"] == "inf-ai"
    assert claude_cfg["env"]["CLAUDE_CODE_DISABLE_THINKING"] == "1"
    assert claude_cfg["thinking"] is False

    # 3. Verify OpenCode config
    opencode_file = temp_userprofile / ".config" / "opencode" / "opencode.json"
    assert opencode_file.exists()
    opencode_cfg = json.loads(opencode_file.read_text(encoding="utf-8"))
    assert opencode_cfg["model"] == "omniroute/inf-ai"
    assert opencode_cfg["provider"]["omniroute"]["options"]["baseURL"] == "http://localhost:20128/v1"
    assert opencode_cfg["provider"]["omniroute"]["options"]["apiKey"] == "sk-omniroute"
    assert "inf-ai" in opencode_cfg["provider"]["omniroute"]["models"]

    # 4. Verify SQLite DB combo
    conn = sqlite3.connect(populated_db_path)
    cur = conn.cursor()
    cur.execute("SELECT data FROM combos WHERE name = 'inf-ai'")
    row = cur.fetchone()
    assert row is not None
    combo_data = json.loads(row[0])
    assert combo_data["name"] == "inf-ai"
    conn.close()
