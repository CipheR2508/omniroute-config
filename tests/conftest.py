import os
import sqlite3
import pytest
from pathlib import Path

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS provider_connections (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    auth_type TEXT,
    name TEXT,
    email TEXT,
    priority INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    access_token TEXT,
    refresh_token TEXT,
    expires_at TEXT,
    token_expires_at TEXT,
    scope TEXT,
    project_id TEXT,
    test_status TEXT,
    error_code TEXT,
    last_error TEXT,
    last_error_at TEXT,
    last_error_type TEXT,
    last_error_source TEXT,
    backoff_level INTEGER DEFAULT 0,
    rate_limited_until TEXT,
    health_check_interval INTEGER,
    last_health_check_at TEXT,
    last_tested TEXT,
    api_key TEXT,
    id_token TEXT,
    provider_specific_data TEXT,
    expires_in INTEGER,
    display_name TEXT,
    global_priority INTEGER,
    default_model TEXT,
    token_type TEXT,
    consecutive_use_count INTEGER DEFAULT 0,
    rate_limit_protection INTEGER DEFAULT 0,
    last_used_at TEXT,
    "group" TEXT,
    max_concurrent INTEGER,
    proxy_enabled INTEGER NOT NULL DEFAULT 1,
    per_key_proxy_enabled INTEGER NOT NULL DEFAULT 0,
    quota_visible INTEGER NOT NULL DEFAULT 1,
    quota_window_thresholds_json TEXT,
    rate_limit_overrides_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_ping_at TEXT,
    last_pinged_reset_key TEXT
);

CREATE TABLE IF NOT EXISTS combos (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    data TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    system_message TEXT DEFAULT NULL,
    tool_filter_regex TEXT DEFAULT NULL,
    context_cache_protection INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS model_combo_mappings (
    id TEXT PRIMARY KEY,
    pattern TEXT NOT NULL,
    combo_id TEXT NOT NULL,
    priority INTEGER DEFAULT 0,
    enabled INTEGER DEFAULT 1,
    description TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (combo_id) REFERENCES combos(id) ON DELETE CASCADE
);
"""

@pytest.fixture
def temp_db_path(tmp_path):
    """Provides a path to a temporary SQLite database initialized with OmniRoute schema."""
    db_file = tmp_path / "storage.sqlite"
    conn = sqlite3.connect(str(db_file))
    conn.executescript(SCHEMA_SQL)
    conn.close()
    return str(db_file)

@pytest.fixture
def temp_db_conn(temp_db_path):
    """Provides an open sqlite3 connection to the temporary database."""
    conn = sqlite3.connect(temp_db_path)
    yield conn
    conn.close()

@pytest.fixture
def populated_db_path(temp_db_path):
    """Provides a temporary database populated with active and inactive provider connections."""
    conn = sqlite3.connect(temp_db_path)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO provider_connections (id, provider, is_active, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        ("conn-gemini-1", "gemini", 1, "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z")
    )
    cursor.execute(
        "INSERT INTO provider_connections (id, provider, is_active, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        ("conn-groq-1", "groq", 1, "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z")
    )
    cursor.execute(
        "INSERT INTO provider_connections (id, provider, is_active, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        ("conn-openrouter-1", "openrouter", 1, "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z")
    )
    cursor.execute(
        "INSERT INTO provider_connections (id, provider, is_active, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        ("conn-inactive-1", "inactive-prov", 0, "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z")
    )
    conn.commit()
    conn.close()
    return temp_db_path

@pytest.fixture
def isolated_env(monkeypatch, temp_db_path):
    """Isolates OMNIROUTE_DB_PATH to the temporary database so tests never touch production storage."""
    monkeypatch.setenv("OMNIROUTE_DB_PATH", temp_db_path)
    return temp_db_path
