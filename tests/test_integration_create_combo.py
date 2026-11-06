import os
import sys
import json
import sqlite3
import subprocess
import pytest

PYTHON_EXE = sys.executable
SCRIPT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "create_combo.py"))

def run_cli(*args, env=None):
    cmd = [PYTHON_EXE, SCRIPT_PATH, *args]
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    return result

def test_integration_missing_db(tmp_path):
    missing_db = str(tmp_path / "missing.sqlite")
    env = os.environ.copy()
    env["OMNIROUTE_DB_PATH"] = missing_db

    proc = run_cli("sync", env=env)
    assert proc.returncode == 1
    assert "Error connecting to OmniRoute database" in proc.stderr
    assert missing_db in proc.stderr

def test_integration_full_lifecycle(populated_db_path):
    env = os.environ.copy()
    env["OMNIROUTE_DB_PATH"] = populated_db_path

    # Step 1: Run 'sync' on populated database
    proc_sync = run_cli("sync", env=env)
    assert proc_sync.returncode == 0
    assert "Successfully updated combo \"inf-ai\"" in proc_sync.stdout

    # Verify directly in SQLite DB
    conn = sqlite3.connect(populated_db_path)
    cur = conn.cursor()
    cur.execute("SELECT id, name, data, sort_order, context_cache_protection FROM combos WHERE name = 'inf-ai'")
    row = cur.fetchone()
    assert row is not None
    assert row[1] == "inf-ai"
    combo_data = json.loads(row[2])
    assert combo_data["strategy"] == "priority"
    assert len(combo_data["models"]) > 0
    # Gemini, Groq, Openrouter were populated as active providers in conftest
    providers_in_chain = {m["providerId"] for m in combo_data["models"]}
    assert "gemini" in providers_in_chain
    assert "groq" in providers_in_chain
    assert "openrouter" in providers_in_chain
    conn.close()

    # Step 2: Run 'list'
    proc_list = run_cli("list", env=env)
    assert proc_list.returncode == 0
    assert '--- Combo "inf-ai" (priority) ---' in proc_list.stdout
    assert "gemini" in proc_list.stdout

    # Step 3: Run 'add'
    proc_add = run_cli("add", "gemini", "gemini-2.5-pro", env=env)
    assert proc_add.returncode == 0
    assert "Successfully updated combo \"inf-ai\"" in proc_add.stdout

    # Verify model is in DB
    conn = sqlite3.connect(populated_db_path)
    cur = conn.cursor()
    cur.execute("SELECT data FROM combos WHERE name = 'inf-ai'")
    updated_data = json.loads(cur.fetchone()[0])
    models = updated_data["models"]
    added = next((m for m in models if m["model"] == "gemini-2.5-pro"), None)
    assert added is not None
    assert added["providerId"] == "gemini"
    assert added["connectionId"] == "conn-gemini-1"
    conn.close()

    # Step 4: Run 'remove'
    proc_remove = run_cli("remove", "gemini-2.5-pro", env=env)
    assert proc_remove.returncode == 0
    assert "Successfully updated combo \"inf-ai\"" in proc_remove.stdout

    # Verify model was removed from DB
    conn = sqlite3.connect(populated_db_path)
    cur = conn.cursor()
    cur.execute("SELECT data FROM combos WHERE name = 'inf-ai'")
    after_remove_data = json.loads(cur.fetchone()[0])
    assert not any(m["model"] == "gemini-2.5-pro" for m in after_remove_data["models"])
    conn.close()

    # Step 5: Run 'reset' (force reinitialization)
    proc_reset = run_cli("reset", env=env)
    assert proc_reset.returncode == 0
    assert "Successfully updated combo \"inf-ai\"" in proc_reset.stdout

def test_integration_cli_invalid_arguments(populated_db_path):
    env = os.environ.copy()
    env["OMNIROUTE_DB_PATH"] = populated_db_path

    # add with missing model_slug
    proc = run_cli("add", "openrouter", env=env)
    assert proc.returncode == 1
    assert "Usage: python create_combo.py add <provider> <model_slug>" in proc.stdout

    # remove with missing slug
    proc = run_cli("remove", env=env)
    assert proc.returncode == 1
    assert "Usage: python create_combo.py remove <model_slug>" in proc.stdout

    # unknown command
    proc = run_cli("foobar", env=env)
    assert proc.returncode == 1
    assert "Unknown command 'foobar'" in proc.stdout
