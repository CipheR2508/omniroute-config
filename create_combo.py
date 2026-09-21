#!/usr/bin/env python3
"""
OmniRoute free-coding Combo Manager
Usage:
  python create_combo.py                             (sync/apply combo)
  python create_combo.py list                        (shows current chain)
  python create_combo.py add <provider> <model_slug> (appends model)
  python create_combo.py remove <model_slug>         (removes model)
"""

import sys
import os
import sqlite3
import json
import uuid
from datetime import datetime, timezone

def get_db_path():
    if os.environ.get("OMNIROUTE_DB_PATH"):
        return os.environ["OMNIROUTE_DB_PATH"]
    if sys.platform == "win32":
        return os.path.join(os.environ.get("USERPROFILE", ""), ".omniroute", "storage.sqlite")
    return os.path.join(os.path.expanduser("~"), ".omniroute", "storage.sqlite")

def get_connection(db_path):
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"OmniRoute database not found at: {db_path}")
    return sqlite3.connect(db_path)

def get_active_providers(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT id, provider FROM provider_connections WHERE is_active = 1")
    return {row[1]: row[0] for row in cursor.fetchall()}

def get_existing_combo(conn, combo_name="free-coding"):
    cursor = conn.cursor()
    cursor.execute("SELECT id, data FROM combos WHERE name = ?", (combo_name,))
    row = cursor.fetchone()
    if row:
        try:
            return {"dbId": row[0], "data": json.loads(row[1])}
        except Exception:
            pass
    return None

def save_combo(conn, combo_data, combo_name="free-coding"):
    now = datetime.now(timezone.utc).isoformat()
    combo_data["updatedAt"] = now
    db_id = combo_data.get("id") or str(uuid.uuid4())
    combo_data["id"] = db_id

    cursor = conn.cursor()
    cursor.execute("SELECT id FROM combos WHERE name = ?", (combo_name,))
    existing = cursor.fetchone()
    if existing:
        cursor.execute("DELETE FROM combos WHERE name = ?", (combo_name,))
        cursor.execute("DELETE FROM model_combo_mappings WHERE combo_id = ?", (existing[0],))

    cursor.execute(
        "INSERT INTO combos (id, name, data, sort_order, created_at, updated_at, context_cache_protection) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (db_id, combo_name, json.dumps(combo_data), 1, combo_data.get("createdAt", now), now, 0)
    )
    conn.commit()

    print(f"\n[SUCCESS] Successfully updated combo \"{combo_name}\" in OmniRoute SQLite DB!")
    print("  Current priority order:")
    for i, m in enumerate(combo_data.get("models", [])):
        print(f"    #{i+1}: [{m.get('providerId')}] {m.get('model')}")

def list_combo(conn, combo_name="free-coding"):
    combo = get_existing_combo(conn, combo_name)
    if not combo:
        print(f'Combo "{combo_name}" does not exist yet.')
        return
    models = combo["data"].get("models", [])
    strategy = combo["data"].get("strategy", "priority")
    print(f'\n--- Combo "{combo_name}" ({strategy}) ---')
    for i, m in enumerate(models):
        print(f"  #{i+1}: [{m.get('providerId')}] {m.get('model')}")

def add_model(conn, provider, model_slug, combo_name="free-coding"):
    combo = get_existing_combo(conn, combo_name)
    now = datetime.now(timezone.utc).isoformat()
    if not combo:
        combo = {
            "data": {
                "id": str(uuid.uuid4()),
                "name": combo_name,
                "models": [],
                "strategy": "priority",
                "config": {
                    "maxRetries": 3,
                    "retryDelayMs": 500,
                    "trackMetrics": True
                },
                "isHidden": False,
                "sortOrder": 1,
                "description": "Free coding fallback chain",
                "createdAt": now,
                "updatedAt": now,
                "version": 2,
                "isActive": True
            }
        }

    active_providers = get_active_providers(conn)
    conn_id = active_providers.get(provider)

    step_id = f"{combo_name}-{provider}-{model_slug.replace('/', '-').replace(':', '-')}".lower()
    models = combo["data"].get("models", [])

    existing_idx = next((i for i, m in enumerate(models) if m.get("model") == model_slug), None)
    if existing_idx is not None:
        print(f'Model "{model_slug}" already exists at position #{existing_idx + 1}. Updating...')
        models[existing_idx]["providerId"] = provider
        models[existing_idx]["connectionId"] = conn_id
    else:
        models.append({
            "id": step_id,
            "kind": "model",
            "model": model_slug,
            "providerId": provider,
            "connectionId": conn_id,
            "weight": 0,
            "label": f"{model_slug} ({provider})"
        })

    combo["data"]["models"] = models
    save_combo(conn, combo["data"], combo_name)

def remove_model(conn, model_slug, combo_name="free-coding"):
    combo = get_existing_combo(conn, combo_name)
    if not combo:
        print(f'Combo "{combo_name}" does not exist.')
        return

    models = combo["data"].get("models", [])
    initial_len = len(models)
    models = [m for m in models if m.get("model") != model_slug and model_slug not in m.get("model", "")]

    if len(models) == initial_len:
        print(f'Model matching "{model_slug}" not found in combo.')
    else:
        combo["data"]["models"] = models
        save_combo(conn, combo["data"], combo_name)

def sync_combo(conn, combo_name="free-coding"):
    existing = get_existing_combo(conn, combo_name)
    active_providers = get_active_providers(conn)

    if existing and existing["data"].get("models"):
        # Refresh connection IDs in case providers were re-linked
        combo_data = existing["data"]
        for m in combo_data["models"]:
            prov = m.get("providerId")
            if prov in active_providers:
                m["connectionId"] = active_providers[prov]
        save_combo(conn, combo_data, combo_name)
        return

    # If initializing new, configure models based on active providers
    candidate_models = [
        ("ollama-cloud", "ollama-cloud/gemma4:31b", "Ollama Cloud Gemma 4 31B"),
        ("nvidia", "nvidia/openai/gpt-oss-20b", "NVIDIA GPT OSS 20B"),
        ("opencode", "opencode/big-pickle", "OpenCode Big Pickle"),
        ("ollama-local", "ollama-local/qwen2.5-coder:7b", "Ollama Local Qwen 2.5 Coder 7B"),
        ("openrouter", "nvidia/nemotron-3-super-120b-a12b:free", "Nemotron 3 Super 120B (OpenRouter Free)"),
        ("openrouter", "poolside/laguna-s-2.1:free", "Poolside Laguna S (OpenRouter Free)"),
        ("openrouter", "google/gemma-4-31b-it:free", "Google Gemma 4 (OpenRouter Free)"),
        ("openrouter", "openrouter/free", "OpenRouter Free Auto-Router"),
    ]

    models_list = []
    for prov, model, label in candidate_models:
        if prov in active_providers or not active_providers:
            models_list.append({
                "id": f"{combo_name}-{prov}-{model.replace('/', '-').replace(':', '-')}".lower(),
                "kind": "model",
                "model": model,
                "providerId": prov,
                "connectionId": active_providers.get(prov),
                "weight": 0,
                "label": label
            })

    now = datetime.now(timezone.utc).isoformat()
    combo_data = {
        "id": str(uuid.uuid4()),
        "name": combo_name,
        "models": models_list,
        "strategy": "priority",
        "config": {
            "maxRetries": 3,
            "retryDelayMs": 500,
            "trackMetrics": True
        },
        "isHidden": False,
        "sortOrder": 1,
        "description": "Deterministic priority fallback chain for free coding.",
        "createdAt": now,
        "updatedAt": now,
        "version": 2,
        "isActive": True
    }
    save_combo(conn, combo_data, combo_name)

def main():
    args = sys.argv[1:]
    command = args[0].lower() if args else "sync"

    db_path = get_db_path()
    try:
        conn = get_connection(db_path)
    except Exception as e:
        print(f"Error connecting to OmniRoute database at '{db_path}': {e}", file=sys.stderr)
        sys.exit(1)

    try:
        if command == "list":
            list_combo(conn)
        elif command == "add":
            if len(args) < 3:
                print("Usage: python create_combo.py add <provider> <model_slug>")
                sys.exit(1)
            add_model(conn, args[1], args[2])
        elif command == "remove":
            if len(args) < 2:
                print("Usage: python create_combo.py remove <model_slug>")
                sys.exit(1)
            remove_model(conn, args[1])
        elif command in ("sync", "apply"):
            sync_combo(conn)
        else:
            print(f"Unknown command '{command}'. Available: sync, list, add, remove")
            sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
