// OmniRoute free-coding-stable Combo Manager
// Usage:
//   node create_combo.js                                    (applies default list)
//   node create_combo.js add <provider> <model_slug>       (appends model automatically)
//   node create_combo.js remove <model_slug>               (removes model)
//   node create_combo.js list                              (shows current chain)

const Database = require('better-sqlite3');
const crypto = require('crypto');
const uuidv4 = () => crypto.randomUUID();

// Get provider connection ID dynamically
function getConnectionId(provider) {
  // We cannot access the database without knowing the path, so we'll return null and let the combo creation fail?
  // Instead, we will set the connectionId to null and let the OmniRoute server handle it?
  // But the combo creation requires a connectionId.
  // We will have to query the database for the connection id.
  // We will pass the database path as an environment variable or use the default.
  const dbPath = process.env.OMNIROUTE_DB_PATH ||
                 (process.platform === 'win32'
                     ? `${process.env.USERPROFILE}\\.omniroute\\storage.sqlite`
                     : `${process.env.HOME}/.omniroute/storage.sqlite`);
  try {
    const db = new Database(dbPath);
    const conn = db.prepare("SELECT id FROM provider_connections WHERE provider = ? AND is_active = 1 LIMIT 1").get(provider);
    db.close();
    return conn ? conn.id : null;
  } catch (e) {
    console.error('Error accessing OmniRoute database:', e.message);
    return null;
  }
}

// Get existing combo data or return default
function getExistingCombo() {
  const dbPath = process.env.OMNIROUTE_DB_PATH ||
                 (process.platform === 'win32'
                     ? `${process.env.USERPROFILE}\\.omniroute\\storage.sqlite`
                     : `${process.env.HOME}/.omniroute/storage.sqlite`);
  try {
    const db = new Database(dbPath);
    const existing = db.prepare("SELECT id, data FROM combos WHERE name = ?").get('free-coding-stable');
    db.close();
    if (existing) {
      try {
        return { dbId: existing.id, data: JSON.parse(existing.data) };
      } catch(e) {}
    }
    return null;
  } catch (e) {
    console.error('Error accessing OmniRoute database:', e.message);
    return null;
  }
}

// Save combo back to DB
function saveCombo(comboData) {
  const dbPath = process.env.OMNIROUTE_DB_PATH ||
                 (process.platform === 'win32'
                     ? `${process.env.USERPROFILE}\\.omniroute\\storage.sqlite`
                     : `${process.env.HOME}/.omniroute/storage.sqlite`);
  try {
    const db = new Database(dbPath);
    const now = new Date().toISOString();
    comboData.updatedAt = now;

    const existing = db.prepare("SELECT id FROM combos WHERE name = ?").get('free-coding-stable');
    const dbId = existing ? existing.id : (comboData.id || uuidv4());
    comboData.id = dbId;

    if (existing) {
      db.prepare("DELETE FROM combos WHERE name = ?").run('free-coding-stable');
      db.prepare("DELETE FROM model_combo_mappings WHERE combo_id = ?").run(dbId);
    }

    db.prepare(
      "INSERT INTO combos (id, name, data, sort_order, created_at, updated_at, context_cache_protection) VALUES (?, ?, ?, ?, ?, ?, ?)"
    ).run(dbId, 'free-coding-stable', JSON.stringify(comboData), 1, comboData.createdAt || now, now, 0);

    console.log(`\n✓ Successfully updated combo "free-coding-stable" in OmniRoute SQLite DB!`);
    console.log('  Current priority order:');
    comboData.models.forEach((m, i) => {
      console.log(`    #${i+1}: [${m.providerId}] ${m.model}`);
    });
    db.close();
  } catch (e) {
    console.error('Error saving combo:', e.message);
    process.exit(1);
  }
}

// Default models if initializing from scratch
const DEFAULT_MODELS = [
  { provider: 'openrouter', model: 'nvidia/nemotron-3-super-120b-a12b:free', label: 'NVIDIA Nemotron 3 Super 120B (OpenRouter Free)' },
  { provider: 'openrouter', model: 'poolside/laguna-s-2.1:free', label: 'Poolside Laguna S 2.1 (OpenRouter Free)' },
  { provider: 'openrouter', model: 'google/gemma-4-31b-it:free', label: 'Google Gemma 4 31B IT (OpenRouter Free)' },
  { provider: 'openrouter', model: 'openrouter/free', label: 'OpenRouter Free Auto-Router' }
];

// CLI Handler
const args = process.argv.slice(2);
const command = args[0] ? args[0].toLowerCase() : 'sync';

if (command === 'list') {
  const current = getExistingCombo();
  if (!current) {
    console.log(`Combo "free-coding-stable" does not exist yet.`);
  } else {
    console.log(`\n--- Combo "free-coding-stable" (${current.data.strategy}) ---`);
    current.data.models.forEach((m, i) => {
      console.log(`  #${i+1}: [${m.providerId}] ${m.model}`);
    });
  }
  process.exit(0);
}

if (command === 'add') {
  const provider = args[1];
  const modelSlug = args[2];

  if (!provider || !modelSlug) {
    console.log('Usage: node create_combo.js add <provider> <model_slug>');
    console.log('Example: node create_combo.js add openrouter openrouter/deepseek/deepseek-r1:free');
    process.exit(1);
  }

  let current = getExistingCombo();
  if (!current) {
    // initialize
    const now = new Date().toISOString();
    current = {
      data: {
        id: uuidv4(),
        name: 'free-coding-stable',
        models: [],
        strategy: 'priority',
        config: {},
        isHidden: false,
        sortOrder: 1,
        description: 'Deterministic free coding combo',
        createdAt: now,
        updatedAt: now,
        schemaVersion: 2
      }
    };
  }

  const connId = getConnectionId(provider);
  const stepId = `${provider}-${modelSlug.replace(/[^a-zA-Z0-9]/g, '-')}`.toLowerCase();

  // Check if model already exists
  const existingIdx = current.data.models.findIndex(m => m.model === modelSlug);
  if (existingIdx !== -1) {
    console.log(`Model "${modelSlug}" already exists at position #${existingIdx + 1}. Updating...`);
    current.data.models[existingIdx].providerId = provider;
    current.data.models[existingIdx].connectionId = connId;
  } else {
    current.data.models.push({
      id: stepId,
      kind: 'model',
      model: modelSlug,
      providerId: provider,
      connectionId: connId,
      weight: 1,
      label: `${modelSlug} (${provider})`,
      tags: ['free', 'coding']
    });
  }

  saveCombo(current.data);
  process.exit(0);
}

if (command === 'remove') {
  const modelSlug = args[1];
  if (!modelSlug) {
    console.log('Usage: node create_combo.js remove <model_slug>');
    process.exit(1);
  }

  const current = getExistingCombo();
  if (!current) {
    console.log(`Combo "free-coding-stable" does not exist.`);
    process.exit(1);
  }

  const initialLen = current.data.models.length;
  current.data.models = current.data.models.filter(m => m.model !== modelSlug && !m.model.includes(modelSlug));

  if (current.data.models.length === initialLen) {
    console.log(`Model matching "${modelSlug}" not found in combo.`);
  } else {
    saveCombo(current.data);
  }
  process.exit(0);
}

// Default: sync/reset combo with DEFAULT_MODELS
const now = new Date().toISOString();
const modelsList = DEFAULT_MODELS.map(m => ({
  id: `${m.provider}-${m.model.replace(/[^a-zA-Z0-9]/g, '-')}`.toLowerCase(),
  kind: 'model',
  model: m.model,
  providerId: m.provider,
  connectionId: getConnectionId(m.provider),
  weight: 1,
  label: m.label,
  tags: ['free', 'coding']
}));

const comboData = {
  id: uuidv4(),
  name: 'free-coding-stable',
  models: modelsList,
  strategy: 'priority',
  config: {},
  isHidden: false,
  sortOrder: 1,
  description: 'Deterministic priority fallback chain using verified free models.',
  createdAt: now,
  updatedAt: now,
  schemaVersion: 2
};

saveCombo(comboData);