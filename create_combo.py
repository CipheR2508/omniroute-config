#!/usr/bin/env python3
"""
OmniRoute inf-ai Combo Manager
Usage:
  python create_combo.py                             (sync/apply combo)
  python create_combo.py list                        (shows current chain)
  python create_combo.py add <provider> <model_slug> (appends model)
  python create_combo.py remove <model_slug>         (removes model)

sync rebuilds the chain from VERIFIED_MODELS, keeping only models whose provider
connection is active, that exist in the provider's synced catalog, and that do
not have a recent failing call log. Excluded models are reported with a reason.
"""

import sys
import os
import sqlite3
import json
import uuid
from datetime import datetime, timezone, timedelta

# Fallback chain, ordered by priority. Every entry must reference a model that
# exists in the provider's synced catalog; the sync step re-checks this and drops
# anything stale so OmniRoute never fails over into a "model does not exist" 400/404.
VERIFIED_MODELS = [
    ("openrouter", "poolside/laguna-s-2.1:free", "Poolside Laguna S 2.1 (OpenRouter Free)"),
    ("nvidia", "openai/gpt-oss-20b", "GPT-OSS 20B (NVIDIA)"),
    ("nvidia", "nvidia/nemotron-3-super-120b-a12b", "Nemotron 3 Super 120B (NVIDIA)"),
    ("agentrouter", "deepseek-v4-flash", "DeepSeek V4 Flash (AgentRouter)"),
    ("gemini", "gemini-3.8-flash", "Gemini 3.8 Flash"),
    ("gemini", "gemini-3.5-flash-lite", "Gemini 3.5 Flash Lite"),
    ("groq", "openai/gpt-oss-20b", "GPT-OSS 20B (Groq)"),
    ("openrouter", "nvidia/nemotron-3.5-super-vl:free", "Nemotron 3.5 Super VL (OpenRouter Free)"),
]

# Providers/models that OmniRoute cannot route through (local-only, OpenCode's
# free tier is confined to OpenCode, and retired local models).
BLOCKED_PROVIDERS = {"ollama-local", "opencode", "opencode-go"}
BLOCKED_MODEL_PREFIXES = ("opencode/",)
BLOCKED_MODEL_MARKERS = ("qwen2.5-coder",)
DEPRECATED_MODELS = {"gemini-2.5-flash"}

# How far back call logs are inspected when deciding whether a model is healthy.
HEALTH_WINDOW_HOURS = 24
# A model whose last recorded attempt is older than this is treated as stale.
HEALTH_MAX_AGE_DAYS = 7

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

def get_model_catalog(conn):
    """Return {provider: {model_id, ...}} from the catalogs OmniRoute synced from each provider."""
    catalog = {}
    try:
        rows = conn.execute(
            "SELECT key, value FROM key_value WHERE namespace = 'syncedAvailableModels'"
        ).fetchall()
    except sqlite3.Error:
        # Older OmniRoute schemas (or the test fixture) may not have this table.
        return catalog

    for key, raw in rows:
        provider = str(key).split(":", 1)[0]
        try:
            models = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if not isinstance(models, list):
            continue
        ids = catalog.setdefault(provider, set())
        for entry in models:
            if isinstance(entry, dict) and entry.get("id"):
                ids.add(entry["id"])
    return catalog

def get_model_health(conn, window_hours=HEALTH_WINDOW_HOURS):
    """Per-model outcomes from call logs: {(provider, model): {...}}.

    Tracks both the recent window (for active models) and the last recorded
    attempt (for models that have not been touched recently but still carry a
    known failure).
    """
    try:
        rows = conn.execute(
            "SELECT provider, model, status, timestamp FROM call_logs"
        ).fetchall()
    except sqlite3.Error:
        return {}

    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    health = {}
    for provider, model, status, timestamp in rows:
        if not provider or not model:
            continue
        try:
            observed = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
        except ValueError:
            continue
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=timezone.utc)

        entry = health.setdefault(
            (provider, model),
            {
                "attempts": 0,
                "successes": 0,
                "latest_status": None,
                "latest_at": None,
                "last_status": None,
                "last_at": None,
                "last_success_at": None,
            },
        )
        if observed >= cutoff:
            entry["attempts"] += 1
            if status == 200:
                entry["successes"] += 1
            if not entry["latest_at"] or observed >= entry["latest_at"]:
                entry["latest_at"] = observed
                entry["latest_status"] = status
        if not entry["last_at"] or observed >= entry["last_at"]:
            entry["last_at"] = observed
            entry["last_status"] = status
        if status == 200 and (not entry["last_success_at"] or observed >= entry["last_success_at"]):
            entry["last_success_at"] = observed
    return health

def get_block_reason(provider, model):
    model_lower = (model or "").lower()
    if provider in BLOCKED_PROVIDERS:
        return "provider cannot be routed through OmniRoute"
    if model_lower.startswith(BLOCKED_MODEL_PREFIXES):
        return "OpenCode-only model"
    if any(marker in model_lower for marker in BLOCKED_MODEL_MARKERS):
        return "retired local model"
    if model in DEPRECATED_MODELS:
        return "retired upstream model"
    return None

def get_health_failure(health, provider, model):
    entry = health.get((provider, model))
    if not entry:
        # Never attempted (fresh install) - keep it, the catalog check still applies.
        return None

    if entry["attempts"] > 0:
        if entry["successes"] == 0:
            return f"{entry['attempts']} recent attempts without a success (last HTTP {entry['latest_status']})"
        if entry["latest_status"] != 200:
            return f"last attempt failed with HTTP {entry['latest_status']}"
        return None

    # No attempt inside the window: fall back to the last recorded outcome.
    if entry["last_status"] != 200:
        return f"last recorded attempt failed with HTTP {entry['last_status']}"
    stale_before = datetime.now(timezone.utc) - timedelta(days=HEALTH_MAX_AGE_DAYS)
    if not entry["last_success_at"] or entry["last_success_at"] < stale_before:
        return f"no successful attempt in the last {HEALTH_MAX_AGE_DAYS} days"
    return None

def build_model_chain(conn, combo_name, ignore_health=False):
    """Build the verified fallback chain and report why candidates were skipped."""
    active_providers = get_active_providers(conn)
    catalog = get_model_catalog(conn)
    health = {} if ignore_health else get_model_health(conn)

    models_list = []
    skipped = []
    seen = set()

    for provider, model, label in VERIFIED_MODELS:
        if (provider, model) in seen:
            continue
        seen.add((provider, model))

        reason = get_block_reason(provider, model)
        if reason:
            skipped.append((provider, model, reason))
            continue
        if provider not in active_providers:
            skipped.append((provider, model, "no active provider connection"))
            continue
        if provider in catalog and model not in catalog[provider]:
            skipped.append((provider, model, "not in the provider's synced catalog"))
            continue
        health_failure = get_health_failure(health, provider, model)
        if health_failure:
            skipped.append((provider, model, health_failure))
            continue

        models_list.append({
            "id": f"{combo_name}-{provider}-{model.replace('/', '-').replace(':', '-')}".lower(),
            "kind": "model",
            "model": model,
            "providerId": provider,
            "connectionId": active_providers.get(provider),
            "weight": 0,
            "label": label
        })

    return models_list, skipped

def get_existing_combo(conn, combo_name="inf-ai"):
    cursor = conn.cursor()
    cursor.execute("SELECT id, data FROM combos WHERE name = ?", (combo_name,))
    row = cursor.fetchone()
    if row:
        try:
            return {"dbId": row[0], "data": json.loads(row[1])}
        except Exception:
            pass
    return None

def save_combo(conn, combo_data, combo_name="inf-ai"):
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

def list_combo(conn, combo_name="inf-ai"):
    combo = get_existing_combo(conn, combo_name)
    if not combo:
        print(f'Combo "{combo_name}" does not exist yet.')
        return
    models = combo["data"].get("models", [])
    strategy = combo["data"].get("strategy", "priority")
    print(f'\n--- Combo "{combo_name}" ({strategy}) ---')
    for i, m in enumerate(models):
        print(f"  #{i+1}: [{m.get('providerId')}] {m.get('model')}")

def add_model(conn, provider, model_slug, combo_name="inf-ai"):
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
                    "maxRetries": 0,
                    "retryDelayMs": 0,
                    "failoverBeforeRetry": True,
                    "healthCheckEnabled": True,
                    "healthCheckTimeoutMs": 8000,
                    "targetTimeoutMs": 60000,
                    "queueDepth": 0,
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

def remove_model(conn, model_slug, combo_name="inf-ai"):
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

def sync_combo(conn, combo_name="inf-ai", force_reset=False):
    """Rebuild the combo from verified models only.

    A model is written to the chain only when all of these hold:
      1. its provider has an active connection,
      2. the model exists in the provider's synced catalog,
      3. recent call logs do not show it failing (missing model / uptime / API errors).

    Rebuilding instead of patching the previous chain is intentional: a stale
    entry that returns 400/404/429/503 keeps poisoning every request that falls
    back to it. force_reset is kept for CLI compatibility.
    """
    models_list, skipped = build_model_chain(conn, combo_name)

    if not models_list:
        print("[WARN] No model passed verification. Keeping every catalog-valid model on active providers.")
        models_list, skipped = build_model_chain(conn, combo_name, ignore_health=True)

    if skipped:
        print("\n[SKIPPED] Models excluded to avoid missing-model / uptime / API errors:")
        for provider, model, reason in skipped:
            print(f"  - [{provider}] {model}: {reason}")

    now = datetime.now(timezone.utc).isoformat()
    combo_data = {
        "id": str(uuid.uuid4()),
        "name": combo_name,
        "models": models_list,
        "strategy": "priority",
        "config": {
            # One attempt per target, then fail over. Never retry a target that
            # just returned a missing-model / uptime / API error.
            "maxRetries": 0,
            "retryDelayMs": 0,
            "failoverBeforeRetry": True,
            # Pre-flight each target and skip the dead ones instead of surfacing their errors.
            "healthCheckEnabled": True,
            "healthCheckTimeoutMs": 8000,
            "targetTimeoutMs": 60000,
            "queueDepth": 0,
            "trackMetrics": True
        },
        "isHidden": False,
        "sortOrder": 1,
        "description": "Verified priority chain: catalog-valid models on active providers, fail-fast failover.",
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
        elif command in ("reset", "init"):
            sync_combo(conn, force_reset=True)
        else:
            print(f"Unknown command '{command}'. Available: sync, reset, list, add, remove")
            sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
