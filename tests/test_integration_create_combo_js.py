import os
import shutil
import sqlite3
import subprocess
import pytest

NODE_EXE = shutil.which("node")
SCRIPT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "create_combo.js"))

@pytest.mark.skipif(NODE_EXE is None, reason="Node.js is not available")
def test_js_delegation_sync_and_list(populated_db_path):
    env = os.environ.copy()
    env["OMNIROUTE_DB_PATH"] = populated_db_path

    # Run 'sync' via node wrapper
    proc_sync = subprocess.run([NODE_EXE, SCRIPT_PATH, "sync"], capture_output=True, text=True, env=env)
    assert proc_sync.returncode == 0
    assert "Successfully updated combo \"inf-ai\"" in proc_sync.stdout

    # Run 'list' via node wrapper
    proc_list = subprocess.run([NODE_EXE, SCRIPT_PATH, "list"], capture_output=True, text=True, env=env)
    assert proc_list.returncode == 0
    assert '--- Combo "inf-ai" (priority) ---' in proc_list.stdout

@pytest.mark.skipif(NODE_EXE is None, reason="Node.js is not available")
def test_js_delegation_add_and_remove(populated_db_path):
    env = os.environ.copy()
    env["OMNIROUTE_DB_PATH"] = populated_db_path

    # Add model
    proc_add = subprocess.run([NODE_EXE, SCRIPT_PATH, "add", "gemini", "gemini-js-test"], capture_output=True, text=True, env=env)
    assert proc_add.returncode == 0
    assert "Successfully updated combo \"inf-ai\"" in proc_add.stdout

    # Verify model added in SQLite
    conn = sqlite3.connect(populated_db_path)
    cur = conn.cursor()
    cur.execute("SELECT data FROM combos WHERE name = 'inf-ai'")
    data = cur.fetchone()[0]
    assert "gemini-js-test" in data
    conn.close()

    # Remove model
    proc_remove = subprocess.run([NODE_EXE, SCRIPT_PATH, "remove", "gemini-js-test"], capture_output=True, text=True, env=env)
    assert proc_remove.returncode == 0
    assert "Successfully updated combo \"inf-ai\"" in proc_remove.stdout

    # Verify removal in SQLite
    conn = sqlite3.connect(populated_db_path)
    cur = conn.cursor()
    cur.execute("SELECT data FROM combos WHERE name = 'inf-ai'")
    data = cur.fetchone()[0]
    assert "gemini-js-test" not in data
    conn.close()

@pytest.mark.skipif(NODE_EXE is None, reason="Node.js is not available")
def test_js_delegation_invalid_command(populated_db_path):
    env = os.environ.copy()
    env["OMNIROUTE_DB_PATH"] = populated_db_path

    proc = subprocess.run([NODE_EXE, SCRIPT_PATH, "invalid-cmd"], capture_output=True, text=True, env=env)
    assert proc.returncode == 1
    assert "Unknown command 'invalid-cmd'" in proc.stdout
