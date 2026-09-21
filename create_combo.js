// OmniRoute free-coding Combo Manager
// Delegates to python create_combo.py (standard library sqlite3, zero dependencies)
// or uses better-sqlite3 if installed.

const { spawnSync } = require('child_process');
const path = require('path');
const fs = require('fs');

const pyScript = path.join(__dirname, 'create_combo.py');
const args = process.argv.slice(2);

// Check if Python is available
const pyCheck = spawnSync('python', ['--version'], { encoding: 'utf8' });
if (pyCheck.status === 0 && fs.existsSync(pyScript)) {
  const result = spawnSync('python', [pyScript, ...args], { stdio: 'inherit' });
  process.exit(result.status ?? 0);
}

// Fallback to better-sqlite3 if python is not available
try {
  const Database = require('better-sqlite3');
  const crypto = require('crypto');
  const uuidv4 = () => crypto.randomUUID();

  const dbPath = process.env.OMNIROUTE_DB_PATH ||
    (process.platform === 'win32'
      ? `${process.env.USERPROFILE}\\.omniroute\\storage.sqlite`
      : `${process.env.HOME}/.omniroute/storage.sqlite`);

  const db = new Database(dbPath);
  const command = args[0] ? args[0].toLowerCase() : 'sync';

  if (command === 'list') {
    const row = db.prepare("SELECT data FROM combos WHERE name = ?").get('free-coding');
    if (!row) {
      console.log('Combo "free-coding" does not exist yet.');
    } else {
      const data = JSON.parse(row.data);
      console.log(`\n--- Combo "free-coding" (${data.strategy}) ---`);
      (data.models || []).forEach((m, i) => {
        console.log(`  #${i + 1}: [${m.providerId}] ${m.model}`);
      });
    }
    db.close();
    process.exit(0);
  }

  // Sync / apply
  const now = new Date().toISOString();
  const existing = db.prepare("SELECT id, data FROM combos WHERE name = ?").get('free-coding');
  let comboData;
  if (existing) {
    comboData = JSON.parse(existing.data);
    comboData.updatedAt = now;
  } else {
    comboData = {
      id: uuidv4(),
      name: 'free-coding',
      models: [],
      strategy: 'priority',
      config: { maxRetries: 3, retryDelayMs: 500, trackMetrics: true },
      isHidden: false,
      sortOrder: 1,
      description: 'Deterministic priority fallback chain for free coding.',
      createdAt: now,
      updatedAt: now,
      version: 2,
      isActive: true
    };
  }

  const dbId = existing ? existing.id : comboData.id;
  comboData.id = dbId;
  if (existing) {
    db.prepare("DELETE FROM combos WHERE name = ?").run('free-coding');
    db.prepare("DELETE FROM model_combo_mappings WHERE combo_id = ?").run(dbId);
  }
  db.prepare(
    "INSERT INTO combos (id, name, data, sort_order, created_at, updated_at, context_cache_protection) VALUES (?, ?, ?, ?, ?, ?, ?)"
  ).run(dbId, 'free-coding', JSON.stringify(comboData), 1, comboData.createdAt || now, now, 0);

  console.log('\n✓ Successfully updated combo "free-coding" in OmniRoute SQLite DB!');
  (comboData.models || []).forEach((m, i) => {
    console.log(`  #${i + 1}: [${m.providerId}] ${m.model}`);
  });
  db.close();
} catch (err) {
  console.error('Error running combo manager:', err.message);
  console.error('Hint: Install Python (with built-in sqlite3) or run "npm install better-sqlite3".');
  process.exit(1);
}