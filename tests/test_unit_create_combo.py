import sys
import os
import json
import sqlite3
from datetime import datetime, timezone

import pytest
from unittest.mock import patch, MagicMock

import create_combo

def test_get_db_path_with_env(monkeypatch):
    monkeypatch.setenv("OMNIROUTE_DB_PATH", "/custom/path/storage.sqlite")
    assert create_combo.get_db_path() == "/custom/path/storage.sqlite"

def test_get_db_path_windows_default(monkeypatch):
    monkeypatch.delenv("OMNIROUTE_DB_PATH", raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("USERPROFILE", "C:\\Users\\TestUser")
    expected = os.path.join("C:\\Users\\TestUser", ".omniroute", "storage.sqlite")
    assert create_combo.get_db_path() == expected

def test_get_db_path_posix_default(monkeypatch):
    monkeypatch.delenv("OMNIROUTE_DB_PATH", raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    with patch("os.path.expanduser", return_value="/home/testuser"):
        expected = os.path.join("/home/testuser", ".omniroute", "storage.sqlite")
        assert create_combo.get_db_path() == expected

def test_get_connection_file_not_found(tmp_path):
    missing_file = str(tmp_path / "non_existent.sqlite")
    with pytest.raises(FileNotFoundError) as excinfo:
        create_combo.get_connection(missing_file)
    assert "OmniRoute database not found" in str(excinfo.value)

def test_get_connection_success(temp_db_path):
    conn = create_combo.get_connection(temp_db_path)
    assert isinstance(conn, sqlite3.Connection)
    conn.close()

def test_get_active_providers_empty(temp_db_conn):
    providers = create_combo.get_active_providers(temp_db_conn)
    assert providers == {}

def test_get_active_providers_populated(temp_db_conn):
    cursor = temp_db_conn.cursor()
    cursor.execute(
        "INSERT INTO provider_connections (id, provider, is_active, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        ("id-active", "active-prov", 1, "2026-01-01", "2026-01-01")
    )
    cursor.execute(
        "INSERT INTO provider_connections (id, provider, is_active, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        ("id-inactive", "inactive-prov", 0, "2026-01-01", "2026-01-01")
    )
    temp_db_conn.commit()

    providers = create_combo.get_active_providers(temp_db_conn)
    assert providers == {"active-prov": "id-active"}
    assert "inactive-prov" not in providers

def test_get_existing_combo_not_found(temp_db_conn):
    res = create_combo.get_existing_combo(temp_db_conn, "inf-ai")
    assert res is None

def test_get_existing_combo_found(temp_db_conn):
    sample_data = {"id": "combo-1", "name": "inf-ai", "models": []}
    cursor = temp_db_conn.cursor()
    cursor.execute(
        "INSERT INTO combos (id, name, data, sort_order, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        ("combo-1", "inf-ai", json.dumps(sample_data), 1, "2026-01-01", "2026-01-01")
    )
    temp_db_conn.commit()

    res = create_combo.get_existing_combo(temp_db_conn, "inf-ai")
    assert res is not None
    assert res["dbId"] == "combo-1"
    assert res["data"] == sample_data

def test_get_existing_combo_corrupted_json(temp_db_conn):
    cursor = temp_db_conn.cursor()
    cursor.execute(
        "INSERT INTO combos (id, name, data, sort_order, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        ("combo-bad", "bad-combo", "INVALID_JSON{", 1, "2026-01-01", "2026-01-01")
    )
    temp_db_conn.commit()

    res = create_combo.get_existing_combo(temp_db_conn, "bad-combo")
    assert res is None

def test_save_combo_new(temp_db_conn, capsys):
    combo_data = {
        "name": "inf-ai",
        "models": [{"providerId": "gemini", "model": "gemini-flash"}]
    }
    create_combo.save_combo(temp_db_conn, combo_data, "inf-ai")

    cursor = temp_db_conn.cursor()
    cursor.execute("SELECT id, name, data, sort_order, context_cache_protection FROM combos WHERE name = ?", ("inf-ai",))
    row = cursor.fetchone()
    assert row is not None
    assert row[1] == "inf-ai"
    saved_data = json.loads(row[2])
    assert saved_data["name"] == "inf-ai"
    assert "updatedAt" in saved_data
    assert "id" in saved_data
    assert row[3] == 1
    assert row[4] == 0

    captured = capsys.readouterr()
    assert "Successfully updated combo \"inf-ai\"" in captured.out
    assert "#1: [gemini] gemini-flash" in captured.out

def test_save_combo_overwrite_and_cleanup_mappings(temp_db_conn):
    # Setup initial combo and a mapping record
    cursor = temp_db_conn.cursor()
    cursor.execute(
        "INSERT INTO combos (id, name, data, sort_order, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        ("combo-old", "inf-ai", "{}", 1, "2026-01-01", "2026-01-01")
    )
    cursor.execute(
        "INSERT INTO model_combo_mappings (id, pattern, combo_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        ("map-1", "pattern-1", "combo-old", "2026-01-01", "2026-01-01")
    )
    temp_db_conn.commit()

    # Overwrite
    new_data = {"id": "combo-new", "name": "inf-ai", "models": []}
    create_combo.save_combo(temp_db_conn, new_data, "inf-ai")

    cursor.execute("SELECT id FROM combos WHERE name = 'inf-ai'")
    assert cursor.fetchone()[0] == "combo-new"

    cursor.execute("SELECT COUNT(*) FROM model_combo_mappings WHERE combo_id = 'combo-old'")
    assert cursor.fetchone()[0] == 0

def test_list_combo_empty(temp_db_conn, capsys):
    create_combo.list_combo(temp_db_conn, "inf-ai")
    captured = capsys.readouterr()
    assert 'Combo "inf-ai" does not exist yet.' in captured.out

def test_list_combo_populated(temp_db_conn, capsys):
    combo_data = {
        "id": "combo-1",
        "name": "inf-ai",
        "strategy": "priority",
        "models": [
            {"providerId": "gemini", "model": "gemini-flash"},
            {"providerId": "groq", "model": "llama-3"}
        ]
    }
    create_combo.save_combo(temp_db_conn, combo_data, "inf-ai")
    capsys.readouterr()  # clear buffer

    create_combo.list_combo(temp_db_conn, "inf-ai")
    captured = capsys.readouterr()
    assert '--- Combo "inf-ai" (priority) ---' in captured.out
    assert "#1: [gemini] gemini-flash" in captured.out
    assert "#2: [groq] llama-3" in captured.out

def test_add_model_to_new_combo(temp_db_conn):
    # Add active provider
    cursor = temp_db_conn.cursor()
    cursor.execute(
        "INSERT INTO provider_connections (id, provider, is_active, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        ("conn-gemini", "gemini", 1, "2026-01-01", "2026-01-01")
    )
    temp_db_conn.commit()

    create_combo.add_model(temp_db_conn, "gemini", "google/gemini-2.0:free", combo_name="inf-ai")
    combo = create_combo.get_existing_combo(temp_db_conn, "inf-ai")
    assert combo is not None
    models = combo["data"]["models"]
    assert len(models) == 1
    m = models[0]
    assert m["providerId"] == "gemini"
    assert m["model"] == "google/gemini-2.0:free"
    assert m["connectionId"] == "conn-gemini"
    assert m["id"] == "inf-ai-gemini-google-gemini-2.0-free"
    assert m["label"] == "google/gemini-2.0:free (gemini)"

def test_add_model_update_existing(temp_db_conn, capsys):
    cursor = temp_db_conn.cursor()
    cursor.execute(
        "INSERT INTO provider_connections (id, provider, is_active, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        ("conn-groq", "groq", 1, "2026-01-01", "2026-01-01")
    )
    temp_db_conn.commit()

    # Initial add
    create_combo.add_model(temp_db_conn, "openrouter", "deepseek/deepseek-chat:free")
    capsys.readouterr()

    # Re-add same model slug with different provider
    create_combo.add_model(temp_db_conn, "groq", "deepseek/deepseek-chat:free")
    captured = capsys.readouterr()
    assert 'already exists at position #1. Updating...' in captured.out

    combo = create_combo.get_existing_combo(temp_db_conn, "inf-ai")
    models = combo["data"]["models"]
    assert len(models) == 1
    assert models[0]["providerId"] == "groq"
    assert models[0]["connectionId"] == "conn-groq"

def test_remove_model_nonexistent_combo(temp_db_conn, capsys):
    create_combo.remove_model(temp_db_conn, "some-model", "inf-ai")
    captured = capsys.readouterr()
    assert 'Combo "inf-ai" does not exist.' in captured.out

def test_remove_model_not_found(temp_db_conn, capsys):
    create_combo.add_model(temp_db_conn, "gemini", "model-a")
    capsys.readouterr()

    create_combo.remove_model(temp_db_conn, "model-b")
    captured = capsys.readouterr()
    assert 'Model matching "model-b" not found in combo.' in captured.out

    combo = create_combo.get_existing_combo(temp_db_conn, "inf-ai")
    assert len(combo["data"]["models"]) == 1

def test_remove_model_success(temp_db_conn):
    create_combo.add_model(temp_db_conn, "gemini", "model-a")
    create_combo.add_model(temp_db_conn, "gemini", "model-b")

    create_combo.remove_model(temp_db_conn, "model-a")
    combo = create_combo.get_existing_combo(temp_db_conn, "inf-ai")
    models = combo["data"]["models"]
    assert len(models) == 1
    assert models[0]["model"] == "model-b"

def test_sync_combo_purges_unwanted_models(temp_db_conn):
    # Set up active provider
    cursor = temp_db_conn.cursor()
    cursor.execute(
        "INSERT INTO provider_connections (id, provider, is_active, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        ("conn-groq", "groq", 1, "2026-01-01", "2026-01-01")
    )
    temp_db_conn.commit()

    # Pre-populate combo with prohibited/stale models
    initial_combo = {
        "id": "combo-test",
        "name": "inf-ai",
        "models": [
            {"providerId": "ollama-local", "model": "qwen2.5-coder:7b"},
            {"providerId": "opencode", "model": "claude-3-5"},
            {"providerId": "groq", "model": "opencode/free-model"},
            {"providerId": "groq", "model": "qwen2.5-coder-32b"},
            {"providerId": "groq", "model": "llama-3.1-8b-instant"}
        ]
    }
    create_combo.save_combo(temp_db_conn, initial_combo, "inf-ai")

    # Sync rebuilds the chain from the verified list instead of preserving stale entries
    create_combo.sync_combo(temp_db_conn)

    combo = create_combo.get_existing_combo(temp_db_conn, "inf-ai")
    remaining_models = combo["data"]["models"]
    assert len(remaining_models) == 1
    assert remaining_models[0]["model"] == "openai/gpt-oss-20b"
    assert remaining_models[0]["providerId"] == "groq"
    assert remaining_models[0]["connectionId"] == "conn-groq"
    assert all(m["providerId"] != "ollama-local" for m in remaining_models)
    assert all(m["providerId"] != "opencode" for m in remaining_models)

def test_sync_combo_initial_population(temp_db_conn):
    # Setup active provider: gemini
    cursor = temp_db_conn.cursor()
    cursor.execute(
        "INSERT INTO provider_connections (id, provider, is_active, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        ("conn-gemini", "gemini", 1, "2026-01-01", "2026-01-01")
    )
    temp_db_conn.commit()

    create_combo.sync_combo(temp_db_conn, force_reset=True)

    combo = create_combo.get_existing_combo(temp_db_conn, "inf-ai")
    assert combo is not None
    data = combo["data"]
    assert data["strategy"] == "priority"
    # Fail-fast: one attempt per target, health-checked, no retry cadence
    assert data["config"]["maxRetries"] == 0
    assert data["config"]["retryDelayMs"] == 0
    assert data["config"]["failoverBeforeRetry"] is True
    assert data["config"]["healthCheckEnabled"] is True

    models = data["models"]
    # Only models from providers with an active connection are written
    providers = {m["providerId"] for m in models}
    assert "gemini" in providers
    assert "openrouter" not in providers  # no active openrouter connection
    assert "groq" not in providers  # groq was not active

    # Check connection ID resolution
    for m in models:
        if m["providerId"] == "gemini":
            assert m["connectionId"] == "conn-gemini"

def _active_connection(conn, provider, conn_id):
    conn.execute(
        "INSERT INTO provider_connections (id, provider, is_active, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (conn_id, provider, 1, "2026-01-01", "2026-01-01")
    )

def test_sync_combo_drops_models_missing_from_provider_catalog(temp_db_conn):
    _active_connection(temp_db_conn, "openrouter", "conn-openrouter")
    _active_connection(temp_db_conn, "nvidia", "conn-nvidia")
    temp_db_conn.execute(
        "CREATE TABLE key_value (namespace TEXT, key TEXT, value TEXT)"
    )
    temp_db_conn.execute(
        "INSERT INTO key_value (namespace, key, value) VALUES (?, ?, ?)",
        ("syncedAvailableModels", "openrouter:conn-openrouter", json.dumps([{"id": "poolside/laguna-s-2.1:free"}]))
    )
    temp_db_conn.execute(
        "INSERT INTO key_value (namespace, key, value) VALUES (?, ?, ?)",
        ("syncedAvailableModels", "nvidia:conn-nvidia", json.dumps([{"id": "openai/gpt-oss-20b"}]))
    )
    temp_db_conn.commit()

    create_combo.sync_combo(temp_db_conn)

    combo = create_combo.get_existing_combo(temp_db_conn, "inf-ai")
    models = {(m["providerId"], m["model"]) for m in combo["data"]["models"]}
    assert ("openrouter", "poolside/laguna-s-2.1:free") in models
    assert ("nvidia", "openai/gpt-oss-20b") in models
    # nvidia/nemotron-3-super-120b-a12b is not in the synced nvidia catalog -> dropped
    assert ("nvidia", "nvidia/nemotron-3-super-120b-a12b") not in models

def test_sync_combo_drops_models_with_recent_failures(temp_db_conn):
    _active_connection(temp_db_conn, "nvidia", "conn-nvidia")
    temp_db_conn.execute(
        "CREATE TABLE call_logs (provider TEXT, model TEXT, status INTEGER, timestamp TEXT)"
    )
    now = datetime.now(timezone.utc).isoformat()
    rows = [
        # gpt-oss had a success, but its last attempt failed
        ("nvidia", "openai/gpt-oss-20b", 200, now),
        ("nvidia", "openai/gpt-oss-20b", 429, now),
        # nemotron's latest attempt succeeded
        ("nvidia", "nvidia/nemotron-3-super-120b-a12b", 200, now),
    ]
    temp_db_conn.executemany(
        "INSERT INTO call_logs (provider, model, status, timestamp) VALUES (?, ?, ?, ?)",
        rows
    )
    temp_db_conn.commit()

    create_combo.sync_combo(temp_db_conn)

    combo = create_combo.get_existing_combo(temp_db_conn, "inf-ai")
    models = {m["model"] for m in combo["data"]["models"]}
    assert "openai/gpt-oss-20b" not in models
    assert "nvidia/nemotron-3-super-120b-a12b" in models

def test_main_cli_dispatch(monkeypatch, populated_db_path, capsys):
    monkeypatch.setenv("OMNIROUTE_DB_PATH", populated_db_path)

    # 1. Test "sync"
    monkeypatch.setattr(sys, "argv", ["create_combo.py", "sync"])
    create_combo.main()
    captured = capsys.readouterr()
    assert "Successfully updated combo \"inf-ai\"" in captured.out

    # 2. Test "list"
    monkeypatch.setattr(sys, "argv", ["create_combo.py", "list"])
    create_combo.main()
    captured = capsys.readouterr()
    assert '--- Combo "inf-ai" (priority) ---' in captured.out

    # 3. Test "add"
    monkeypatch.setattr(sys, "argv", ["create_combo.py", "add", "gemini", "test-model-1"])
    create_combo.main()
    captured = capsys.readouterr()
    assert "Successfully updated combo \"inf-ai\"" in captured.out

    # 4. Test "remove"
    monkeypatch.setattr(sys, "argv", ["create_combo.py", "remove", "test-model-1"])
    create_combo.main()
    captured = capsys.readouterr()
    assert "Successfully updated combo \"inf-ai\"" in captured.out

    # 5. Test "reset"
    monkeypatch.setattr(sys, "argv", ["create_combo.py", "reset"])
    create_combo.main()
    captured = capsys.readouterr()
    assert "Successfully updated combo \"inf-ai\"" in captured.out

def test_main_cli_errors(monkeypatch, populated_db_path, capsys):
    monkeypatch.setenv("OMNIROUTE_DB_PATH", populated_db_path)

    # Missing args for add
    monkeypatch.setattr(sys, "argv", ["create_combo.py", "add", "only_one_arg"])
    with pytest.raises(SystemExit) as exc:
        create_combo.main()
    assert exc.value.code == 1
    assert "Usage: python create_combo.py add <provider> <model_slug>" in capsys.readouterr().out

    # Missing args for remove
    monkeypatch.setattr(sys, "argv", ["create_combo.py", "remove"])
    with pytest.raises(SystemExit) as exc:
        create_combo.main()
    assert exc.value.code == 1
    assert "Usage: python create_combo.py remove <model_slug>" in capsys.readouterr().out

    # Unknown command
    monkeypatch.setattr(sys, "argv", ["create_combo.py", "unknown-cmd"])
    with pytest.raises(SystemExit) as exc:
        create_combo.main()
    assert exc.value.code == 1
    assert "Unknown command 'unknown-cmd'" in capsys.readouterr().out

def test_main_db_connection_error(monkeypatch, tmp_path, capsys):
    non_existent = str(tmp_path / "does_not_exist.sqlite")
    monkeypatch.setenv("OMNIROUTE_DB_PATH", non_existent)
    monkeypatch.setattr(sys, "argv", ["create_combo.py", "sync"])

    with pytest.raises(SystemExit) as exc:
        create_combo.main()
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "Error connecting to OmniRoute database" in captured.err
