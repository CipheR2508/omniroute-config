# OmniRoute `inf-ai` Fallback Fix — Report

**Date:** 2026-10-25
**Scope:** OmniRoute `inf-ai` combo, live database and portable setup scripts
**Result:** The combo no longer falls back into missing-model, uptime, or API errors. It was rebuilt from verified models and answers requests again.

---

## 1. Symptom

Requests routed through `inf-ai` failed instead of answering. The call log showed the chain walking through several broken targets and ending on one of:

```text
[400]: <model> is not a valid model ID
[404]: The model `<model>` does not exist or you do not have access to it
[404]: This model is unavailable for free. The paid version is available now...
[429]: All credentials for model <model> are cooling down
[429]: You reached the Free usage limit
[503]: Service temporarily unavailable: all upstream accounts are inactive
[504]: upstream timed out
```

The most frequent failures in `call_logs` were:

| Status | Error | Count |
|---|---|---|
| 429 | `free-models-per-day` quota (OpenRouter) | 219 |
| 400 | `nemotron-3-super-120b:free is not a valid model ID` | 167 |
| 403 | Perplexity Sonar migration error | 86 |
| 404 | `qwen3.8-27b` does not exist / no access | 38 |
| 503 | `all upstream accounts are inactive` | 35 |
| 404 | `mistral-7b-instruct-tool-v0.1` does not exist | 30 |
| 404 | `gemini-2.5-flash is no longer available to new users` | 26 |
| 502 | wedged local rate-limit queue | 25 |
| 410 | end-of-life models | 36 |

## 2. Root Cause

1. **OmniRoute treats every non-OK target response as a fallback signal.** A 400, 404, 429, 503, or 504 on one target moves the request to the next combo entry.
2. **The old `sync` preserved the existing chain.** It only removed `ollama-local`/`opencode` entries, so stale model IDs and dead providers stayed at the top of the chain indefinitely.
3. **The chain was built from a hardcoded candidate list, not from what the providers actually serve.** Several IDs did not exist, had become paid-only, or were retired (`qwen/qwen3.8-27b`, `gemini-2.5-flash`, `nvidia/nvidia/...`, per-model free slugs).
4. **A bad model could poison its whole provider.** Repeated 404s on one model marked the provider unavailable/cooling down, which then broke working models on the same provider.
5. **The combo retried failing targets** (`maxRetries: 3–5`) before moving on, doubling the error cascade.

## 3. What Changed

### `create_combo.py`

`sync` is now a **verified rebuild** instead of a patch:

- Reads active connections from `provider_connections`.
- Reads each provider's real model catalog from
  `key_value` → `syncedAvailableModels`.
- Reads recent outcomes (last 24h) from `call_logs`, plus the last recorded
  attempt for models that have not been used recently.
- Writes a model into the chain only when:
  1. its provider has an **active** connection,
  2. the model exists in the provider's **synced catalog**,
  3. its recent attempts show a success and its latest attempt is HTTP 200,
     and its last success is not stale.
- Hard-blocks providers/models that OmniRoute cannot route through
  (`ollama-local`, `opencode`, `opencode-go`, `qwen2.5-coder` locals) and
  retired IDs.
- Prints every excluded model with the reason.
- If everything is skipped, warns and keeps all catalog-valid models on active
  providers so the combo is never empty.

Fallback order comes from `VERIFIED_MODELS` in `create_combo.py`, which is the
place to add or remove candidates permanently.

### Combo runtime config

```json
{
  "maxRetries": 0,
  "retryDelayMs": 0,
  "failoverBeforeRetry": true,
  "healthCheckEnabled": true,
  "healthCheckTimeoutMs": 8000,
  "targetTimeoutMs": 60000,
  "queueDepth": 0,
  "trackMetrics": true
}
```

A target is attempted once, then the next verified target is used. Dead
targets are skipped by the pre-flight health check instead of being retried.

### Tests

- Updated `tests/test_unit_create_combo.py` for the rebuild behavior and the
  new config.
- Added:
  - `test_sync_combo_drops_models_missing_from_provider_catalog`
  - `test_sync_combo_drops_models_with_recent_failures`
- Integration and JS-wrapper tests still pass.

### Docs

- `README.md`: documented catalog/health gating, the fail-fast config, and the
  `add`/`remove` versus `sync` behavior.
- `limitations.md`: added section 9, “Combo Falls Back Into Broken Models,”
  plus a summary-matrix row.

## 4. Live Configuration Applied

`python create_combo.py sync` was run against
`~/.omniroute/storage.sqlite`. The resulting chain:

```text
--- Combo "inf-ai" (priority) ---
  #1: [openrouter] poolside/laguna-s-2.1:free
  #2: [nvidia] openai/gpt-oss-20b
```

Models excluded automatically, with reasons:

```text
[SKIPPED] Models excluded to avoid missing-model / uptime / API errors:
  - [nvidia] nvidia/nemotron-3-super-120b-a12b: 1 recent attempts without a success (last HTTP 404)
  - [agentrouter] deepseek-v4-flash: 11 recent attempts without a success (last HTTP 503)
  - [gemini] gemini-3.8-flash: 3 recent attempts without a success (last HTTP 499)
  - [gemini] gemini-3.5-flash-lite: last recorded attempt failed with HTTP 400
  - [groq] openai/gpt-oss-20b: 3 recent attempts without a success (last HTTP 502)
  - [openrouter] nvidia/nemotron-3.5-super-vl:free: not in the provider's synced catalog
```

Provider state at the time of the fix:

| Provider | State | Effect |
|---|---|---|
| openrouter | active | Laguna free model works |
| nvidia | active | `openai/gpt-oss-20b` works; nemotron returns 404 |
| agentrouter | 503 / no channel | excluded |
| gemini | hangs / 499, last 400 | excluded |
| groq | 502 empty response | excluded |
| deepinfra | 402 no balance | excluded |
| ollama-cloud | 429 free usage limit | excluded |
| opencode-go | 401 invalid key | excluded |
| opencode | OpenCode free tier only | excluded by policy |
| perplexity | 403 Sonar migration | excluded |
| xai | active, no free/used model | not in verified list |

## 5. Verification

- `python create_combo.py list` shows the two-model chain above.
- `omniroute chat -m inf-ai "Reply with OK"` succeeded twice:
  - HTTP 200 via `inf-ai-openrouter-poolside-laguna-s-2.1-free`, 4.9 s
  - HTTP 200 via `inf-ai-openrouter-poolside-laguna-s-2.1-free`, 2.4 s
- `call_logs` confirms `combo_name = inf-ai` and the expected
  `combo_step_id`.
- Test suite: **34 passed, 1 pre-existing failure**
  - `test_setup_ps1_end_to_end_success` fails reading the Claude settings JSON
    because Windows PowerShell 5.1 writes a UTF-8 BOM with
    `Set-Content -Encoding UTF8`. This is unrelated to the fallback change and
    was not modified.

## 6. Operational Notes

- Use `-m inf-ai` (or the pre-configured Claude/OpenCode model name). The CLI
  `--combo` flag was not honored for chat on this version.
- `omniroute combo list` prints “No combos configured” because the CLI’s
  management call is unauthenticated here (HTTP 401 swallowed). Routing itself
  works; the database and `create_combo.py list` show the real chain.
- Re-run `python create_combo.py sync` after a provider recovers. A model with
  a recent success is re-added automatically; a still-failing model stays out.
- `add` / `remove` are temporary. The next `sync` rebuilds from
  `VERIFIED_MODELS`.
- If a candidate should survive syncs, add it to `VERIFIED_MODELS` in
  `create_combo.py`.
