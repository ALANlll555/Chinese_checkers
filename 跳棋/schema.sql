PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

INSERT OR IGNORE INTO schema_meta(key, value) VALUES ('schema_version', '3');
UPDATE schema_meta SET value='3' WHERE key='schema_version';

CREATE TABLE IF NOT EXISTS games (
    game_id TEXT PRIMARY KEY,
    mode TEXT NOT NULL,
    difficulty INTEGER NOT NULL,
    num_players INTEGER NOT NULL,
    human_first INTEGER NOT NULL DEFAULT 1,
    save_name TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    winner INTEGER,
    current_player INTEGER NOT NULL,
    state_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS moves (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id TEXT NOT NULL REFERENCES games(game_id) ON DELETE CASCADE,
    move_index INTEGER NOT NULL,
    player_id INTEGER NOT NULL,
    actor TEXT NOT NULL CHECK(actor IN ('human', 'ai', 'system')),
    from_row INTEGER NOT NULL,
    from_col INTEGER NOT NULL,
    to_row INTEGER NOT NULL,
    to_col INTEGER NOT NULL,
    state_before_json TEXT NOT NULL,
    state_after_json TEXT NOT NULL,
    eval_before REAL,
    eval_after REAL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(game_id, move_index)
);

CREATE TABLE IF NOT EXISTS ai_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id TEXT NOT NULL REFERENCES games(game_id) ON DELETE CASCADE,
    move_index INTEGER NOT NULL,
    player_id INTEGER NOT NULL,
    difficulty INTEGER NOT NULL,
    selected_move_json TEXT NOT NULL,
    candidates_json TEXT NOT NULL DEFAULT '[]',
    elapsed_ms REAL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(game_id, move_index)
);

CREATE TABLE IF NOT EXISTS evaluation_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id TEXT NOT NULL REFERENCES games(game_id) ON DELETE CASCADE,
    move_index INTEGER NOT NULL,
    player_id INTEGER NOT NULL,
    context TEXT NOT NULL,
    score REAL NOT NULL,
    components_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id TEXT NOT NULL REFERENCES games(game_id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK(role IN ('system', 'user', 'assistant', 'tool')),
    content TEXT NOT NULL,
    model TEXT,
    tool_name TEXT,
    tool_call_id TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS mcp_audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id TEXT NOT NULL,
    game_id TEXT,
    source TEXT NOT NULL DEFAULT 'mcp',
    operation TEXT NOT NULL,
    arguments_json TEXT NOT NULL DEFAULT '{}',
    result_json TEXT,
    success INTEGER NOT NULL,
    error TEXT,
    duration_ms REAL NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_moves_game ON moves(game_id, move_index);
CREATE INDEX IF NOT EXISTS idx_ai_decisions_game ON ai_decisions(game_id, move_index);
CREATE INDEX IF NOT EXISTS idx_evaluations_game ON evaluation_snapshots(game_id, move_index);
CREATE INDEX IF NOT EXISTS idx_chat_game ON chat_messages(game_id, id);
CREATE INDEX IF NOT EXISTS idx_mcp_game ON mcp_audit_logs(game_id, id);
CREATE INDEX IF NOT EXISTS idx_games_updated ON games(updated_at DESC);
