/**
 * 霓虹跳棋 — Canvas 渲染 + 交互
 */

// ═══════════════════════════════════════════════════
// 全局状态
// ═══════════════════════════════════════════════════

const cfg = {
  boardRows: 17, boardCols: 17,
  holeRadius: 10, pieceRadius: 13,
  cellSize: 32,
};

// 有效孔位（从后端同步）
let validHoles = [];
let holeSet = new Set();

// 棋盘数据像素坐标缓存
let holeCoords = {};  // "r,c" -> {x, y}

// 游戏状态
let gameState = null;
let selectedPiece = null;
let legalMoves = [];
let gameMode = 'pvp';
let difficulty = 2;
let victorySpawned = false;
let victoryParticles = [];

// 回放状态
let replayMode = false;
let replayStep = 0;
let replayHistory = [];
let replayBasePieces = {};
let replayOrigState = null;  // 回放前的 gameState 备份

// Canvas
let canvas, ctx;
let canvasW, canvasH;
let centerX, centerY;

// 玩家名称
const PLAYER_NAMES = {
  0: '红方', 1: '蓝方', 2: '绿方',
  3: '黄方', 4: '紫方', 5: '橙方',
};

// ═══════════════════════════════════════════════════
// Theme 桥接 — 从 CSS 变量读取颜色
// ═══════════════════════════════════════════════════

const Theme = {
  _cache: {},
  _version: 0,

  /** 读取 CSS 自定义属性（带缓存，主题切换时刷新） */
  get(name) {
    if (this._cache[name] !== undefined) return this._cache[name];
    const v = getComputedStyle(document.body).getPropertyValue(name);
    const val = (v || '').trim();
    this._cache[name] = val;
    return val;
  },

  /** 获取玩家棋子颜色 */
  playerColor(pid) {
    const k = `--player-${pid}`;
    if (this._cache[k]) return this._cache[k];
    return this.get(k) || _fallbackColors[pid] || '#999';
  },

  /** 刷新缓存（主题切换时调用） */
  refresh() { this._version++; this._cache = {}; },
};

// 兜底颜色（CSS 变量加载前使用）
const _fallbackColors = {
  0: '#e74c3c', 1: '#3498db', 2: '#2ecc71',
  3: '#f1c40f', 4: '#9b59b6', 5: '#e67e22',
};

// 兼容简写
function _pc(pid) { return Theme.playerColor(pid); }


// ═══════════════════════════════════════════════════
// 初始化
// ═══════════════════════════════════════════════════

function init() {
  canvas = document.getElementById('boardCanvas');
  ctx = canvas.getContext('2d');

  canvasW = 720;
  canvasH = 680;
  canvas.width = canvasW;
  canvas.height = canvasH;
  centerX = canvasW / 2;
  centerY = canvasH / 2;

  // 鼠标交互
  canvas.addEventListener('click', handleCanvasClick);

  // 初始化音频引擎
  AudioEngine.init();

  // 初始化主题
  initTheme();

  // 先构建孔位数据（同步，不依赖后端）
  buildHoleDataFromConfig();

  // 加载棋谱列表
  loadReplays();

  // 绘制空白棋盘
  draw();
}

function buildHoleDataFromConfig() {
  const ranges = [
    [8,8],[7,8],[7,9],[6,9],
    [2,14],[2,13],[3,13],[3,12],
    [4,12],[3,12],[3,13],[2,13],
    [2,14],[6,9],[7,9],[7,8],[8,8],
  ];
  validHoles = [];
  holeSet = new Set();
  holeCoords = {};

  for (let r = 0; r < ranges.length; r++) {
    const [s, e] = ranges[r];
    for (let c = s; c <= e; c++) {
      const key = `${r},${c}`;
      validHoles.push([r, c]);
      holeSet.add(key);
      holeCoords[key] = gridToPixel(r, c);
    }
  }
}


// ═══════════════════════════════════════════════════
// 坐标映射
// ═══════════════════════════════════════════════════

function gridToPixel(r, c) {
  const vertSpacing = cfg.cellSize * 0.866;
  let x = centerX + (c - 8) * cfg.cellSize;
  if (r % 2 === 1) x += cfg.cellSize * 0.5;
  // Y轴翻转：红方（row 0-3 原本在顶部）显示在屏幕下方
  let y = centerY + (8 - r) * vertSpacing;
  return { x, y };
}

function pixelToGrid(px, py) {
  let best = null;
  let bestDist = cfg.cellSize * 0.9;
  for (const [r, c] of validHoles) {
    const { x, y } = holeCoords[`${r},${c}`];
    const dist = Math.hypot(px - x, py - y);
    if (dist < bestDist) {
      bestDist = dist;
      best = [r, c];
    }
  }
  return best;
}


// ═══════════════════════════════════════════════════
// API 调用
// ═══════════════════════════════════════════════════

async function newGame() {
  // 弹出开局弹窗
  document.getElementById('startModal').style.display = 'flex';
  document.getElementById('archiveNameInput').value = '';
  document.getElementById('archiveNameError').style.display = 'none';
}

function closeStartModal() {
  document.getElementById('startModal').style.display = 'none';
}

function startWithArchive() {
  document.getElementById('startModal').style.display = 'none';
  document.getElementById('archiveNameInput').value = '';
  document.getElementById('archiveNameError').style.display = 'none';
  document.getElementById('archiveNameModal').style.display = 'flex';
  setTimeout(() => document.getElementById('archiveNameInput').focus(), 100);
}

function closeArchiveNameModal() {
  document.getElementById('archiveNameModal').style.display = 'none';
  document.getElementById('startModal').style.display = 'flex';
}

async function confirmArchiveStart() {
  const name = document.getElementById('archiveNameInput').value.trim();
  if (!name) {
    document.getElementById('archiveNameError').textContent = '请输入存档名称';
    document.getElementById('archiveNameError').style.display = 'block';
    return;
  }
  // 检查重名
  const check = await fetch(`/api/archive/check/${encodeURIComponent(name)}`);
  const cd = await check.json();
  if (cd.exists) {
    document.getElementById('archiveNameError').textContent = '该名称已存在，请换一个';
    document.getElementById('archiveNameError').style.display = 'block';
    return;
  }
  document.getElementById('archiveNameModal').style.display = 'none';
  _doStartGame(name);
}

async function startQuickGame() {
  document.getElementById('startModal').style.display = 'none';
  _doStartGame('');
}

async function _doStartGame(saveName) {
  AudioEngine.playClick();
  gameMode = document.getElementById('modeSelect').value;
  difficulty = parseInt(document.getElementById('diffSelect').value);
  const numPlayers = parseInt(document.getElementById('playerCount').value);
  const apiKey = document.getElementById('apiKeyInput').value.trim();
  const humanFirst = document.getElementById('firstSelect').value === 'human';

  const resp = await fetch('/api/new_game', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ num_players: numPlayers, mode: gameMode, difficulty, api_key: apiKey, human_first: humanFirst, save_name: saveName }),
  });
  gameState = await resp.json();
  gameState._saveName = saveName;  // 挂载存档名用于前端判断
  selectedPiece = null;
  legalMoves = [];
  victorySpawned = false;
  victoryParticles = [];
  replayMode = false;
  replayStep = 0;
  replayHistory = [];
  replayBasePieces = {};
  replayOrigState = null;
  document.getElementById('replayControls').style.display = 'none';
  document.getElementById('btnInGameReplay').style.display = saveName ? '' : 'none';

  document.getElementById('setupCard').style.display = 'none';
  document.getElementById('infoCard').style.display = 'block';
  document.getElementById('commentCard').style.display = 'none';
  updateUI();
  draw();

  // AI 先手：自动触发 AI 走棋
  if (gameMode === 'pve' && !humanFirst) {
    triggerAIMove();
  }
}

function backToSetup() {
  // 返回设置面板
  document.getElementById('setupCard').style.display = 'block';
  document.getElementById('infoCard').style.display = 'none';
  document.getElementById('commentCard').style.display = 'none';
  selectedPiece = null;
  legalMoves = [];
  draw();
}

async function doMove(from, to) {
  const resp = await fetch('/api/move', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ from, to }),
  });
  if (!resp.ok) {
    const err = await resp.json();
    console.warn(err.error);
    return;
  }
  gameState = await resp.json();
  selectedPiece = null;
  legalMoves = [];
  updateUI();
  draw();

  // 人机模式：等人类走完后再请求 AI 走棋
  if (gameState.need_ai) {
    setTimeout(triggerAIMove, 1000);
  }
}

async function triggerAIMove() {
  document.getElementById('turnInfo').textContent = '🤔 AI 思考中...';
  const t0 = performance.now();
  const r = await fetch('/api/ai_move', { method: 'POST' });
  const newState = await r.json();
  // 三类独立放大倍数，严格 1.5 ~ 2.5s，难度递增：1.5s / 2.0s / 2.5s
  const configs = {
    1: { m: 37500, floor: 1500, cap: 1550 },  // 随机  ~0ms → cap 1.55s
    2: { m:  2700, floor: 2000, cap: 2050 },  // 贪心 0.74ms × 2700 ≈ 2.0s
    3: { m:    42, floor: 2450, cap: 2500 },  // Minimax 60ms × 42 ≈ 2.5s
  };
  const c = configs[difficulty] || { m: 42, floor: 2450, cap: 2500 };
  const elapsed = performance.now() - t0;
  const delay = Math.min(c.cap, Math.max(c.floor, elapsed * c.m));
  await new Promise(resolve => setTimeout(resolve, delay - elapsed));
  // 思考结束 → 清空提示 → 短暂停顿 → 落子 → 切换回合
  document.getElementById('turnInfo').textContent = '';
  await new Promise(resolve => setTimeout(resolve, 250));
  gameState = newState;
  draw();
  updateUI();

  // LLM 点评
  if (gameState.ai_move) {
    fetch('/api/comment').then(r => r.json()).then(data => {
      if (data.comment) {
        document.getElementById('commentCard').style.display = 'block';
        document.getElementById('commentText').textContent = data.comment;
      }
    }).catch(() => {});
  }

  // 多人 PVE：链式触发下一个 AI 直到轮到人类
  if (gameState.current_player !== 0 && gameMode === 'pve' && !gameState.is_terminal) {
    setTimeout(triggerAIMove, 1000);
  }
}

async function undoMove() {
  if (replayMode) return;
  const resp = await fetch('/api/undo', { method: 'POST' });
  if (!resp.ok) return;
  AudioEngine.playUndo();
  gameState = await resp.json();
  selectedPiece = null;
  legalMoves = [];
  updateUI();
  draw();
}

async function aiHint() {
  if (replayMode) return;
  AudioEngine.playClick();
  const resp = await fetch('/api/hint', { method: 'POST' });
  if (!resp.ok) return;
  const hint = await resp.json();
  if (hint.from) {
    selectedPiece = hint.from;
    // 高亮提示走法
    legalMoves = [hint.to];
    draw();
  }
}

async function loadReplays() {
  try {
    const resp = await fetch('/api/replays');
    const replays = await resp.json();
    const el = document.getElementById('replayList');
    if (replays.length === 0) {
      el.innerHTML = '<div style="color:#555;padding:8px">暂无存档</div>';
      return;
    }
    el.innerHTML = replays.map(r => {
      const name = r.name || r.game_id;
      const escaped = name.replace(/'/g, "\\'");
      return `<div class="replay-item">
        <span class="archive-name" style="cursor:pointer" onclick="loadReplay('${escaped}')">📁 ${escaped}</span>
        <span style="color:#666;font-size:0.75em;margin-left:6px">${r.mode} · ${r.saved_at?.slice(0,16) || ''}</span>
        <span class="replay-actions">
          <button onclick="event.stopPropagation();renameArchive('${escaped}')" title="重命名">✏</button>
          <button class="danger" onclick="event.stopPropagation();deleteArchive('${escaped}')" title="删除">🗑</button>
        </span>
      </div>`;
    }).join('');
  } catch (e) { /* ignore */ }
}

async function deleteArchive(name) {
  if (!confirm(`确定删除存档「${name}」？`)) return;
  await fetch(`/api/archive/${encodeURIComponent(name)}`, { method: 'DELETE' });
  loadReplays();
}

async function renameArchive(oldName) {
  const newName = prompt('输入新名称:', oldName);
  if (!newName || newName === oldName) return;
  const resp = await fetch(`/api/archive/${encodeURIComponent(oldName)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: newName }),
  });
  if (!resp.ok) {
    const err = await resp.json();
    alert(err.error || '重命名失败');
    return;
  }
  loadReplays();
}

async function loadReplay(gid) {
  const resp = await fetch(`/api/load_replay/${gid}`);
  if (!resp.ok) return;
  const data = await resp.json();
  const mh = data.state?.move_history;

  if (mh && mh.length > 0) {
    startReplay(data);
  } else {
    // 旧格式兼容
    gameState = data.state;
    gameMode = data.mode;
    updateUI();
    draw();
  }
}

// ═══════════════════════════════════════════════════
// 回放引擎
// ═══════════════════════════════════════════════════

function computeBasePieces(pieces, history) {
  // 从终局棋子位置反推初始布局
  const basePieces = {};
  const piecesCopy = JSON.parse(JSON.stringify(pieces));
  for (const pid in piecesCopy) {
    const posMap = {};
    for (const [r, c] of piecesCopy[pid]) {
      posMap[`${r},${c}`] = true;
    }
    for (let i = history.length - 1; i >= 0; i--) {
      const [from, to, p] = history[i];
      if (p !== parseInt(pid)) continue;
      const toKey = `${to[0]},${to[1]}`;
      const fromKey = `${from[0]},${from[1]}`;
      if (posMap[toKey]) {
        delete posMap[toKey];
        posMap[fromKey] = true;
      }
    }
    basePieces[pid] = Object.keys(posMap).map(k => {
      const [r, c] = k.split(',').map(Number);
      return [r, c];
    });
  }
  return basePieces;
}

function startReplay(data) {
  // 保存当前局面（如正在游戏中）
  if (gameState && !replayMode) {
    replayOrigState = JSON.parse(JSON.stringify(gameState));
  }

  replayMode = true;
  const st = data.state;
  replayHistory = st.move_history;
  gameMode = data.mode;

  replayBasePieces = computeBasePieces(st.pieces, replayHistory);

  // 初始 scores
  const baseScores = {};
  for (const pidStr in replayBasePieces) {
    baseScores[pidStr] = 0;
  }

  // 显示第一步（初始布局）
  gameState = {
    current_player: replayHistory[0]?.[2] ?? st.current_player,
    active_players: st.active_players,
    pieces: JSON.parse(JSON.stringify(replayBasePieces)),
    scores: baseScores,
    move_count: 0,
    winner: null,
    is_terminal: false,
  };
  replayStep = 0;

  document.getElementById('infoCard').style.display = 'block';
  document.getElementById('replayControls').style.display = 'block';
  document.getElementById('commentCard').style.display = 'none';
  selectedPiece = null;
  legalMoves = [];
  victorySpawned = false;
  victoryParticles = [];
  updateUI();
  draw();
}

function startInGameReplay() {
  if (replayMode) return;
  if (!gameState || !gameState.move_history || gameState.move_history.length === 0) {
    alert('暂无走棋记录');
    return;
  }

  replayOrigState = JSON.parse(JSON.stringify(gameState));
  replayHistory = JSON.parse(JSON.stringify(gameState.move_history));
  replayBasePieces = computeBasePieces(gameState.pieces, replayHistory);

  replayMode = true;
  document.getElementById('infoCard').style.display = 'block';
  document.getElementById('replayControls').style.display = 'block';
  selectedPiece = null;
  legalMoves = [];
  victorySpawned = false;
  victoryParticles = [];
  replayStepTo(replayHistory.length);
}

function replayStepTo(n) {
  if (!replayMode || !replayHistory.length) return;
  n = Math.max(0, Math.min(n, replayHistory.length));
  replayStep = n;

  // 从 base 重建
  const pieces = JSON.parse(JSON.stringify(replayBasePieces));
  const lastState = replayOrigState || gameState;
  const activePlayers = lastState.active_players;
  const goalSetsByPid = {
    0: new Set([[13,6],[13,7],[13,8],[13,9],[14,7],[14,8],[14,9],[15,7],[15,8],[16,8]].map(p=>`${p[0]},${p[1]}`)),
    1: new Set([[9,3],[10,3],[10,4],[11,3],[11,4],[11,5],[12,2],[12,3],[12,4],[12,5]].map(p=>`${p[0]},${p[1]}`)),
    2: new Set([[4,2],[4,3],[4,4],[4,5],[5,2],[5,3],[5,4],[6,3],[6,4],[7,3]].map(p=>`${p[0]},${p[1]}`)),
    3: new Set([[0,8],[1,7],[1,8],[2,7],[2,8],[2,9],[3,6],[3,7],[3,8],[3,9]].map(p=>`${p[0]},${p[1]}`)),
    4: new Set([[4,11],[4,12],[4,13],[4,14],[5,11],[5,12],[5,13],[6,12],[6,13],[7,12]].map(p=>`${p[0]},${p[1]}`)),
    5: new Set([[9,12],[10,12],[10,13],[11,11],[11,12],[11,13],[12,11],[12,12],[12,13],[12,14]].map(p=>`${p[0]},${p[1]}`)),
  };

  // 用 Set 追踪每个玩家的棋子位置，方便 O(1) 更新
  const pieceSets = {};
  for (const pid in pieces) {
    pieceSets[pid] = new Set(pieces[pid].map(p => `${p[0]},${p[1]}`));
  }

  const scores = {};
  for (const pid in pieces) scores[pid] = 0;

  // 执行前 n 步
  for (let i = 0; i < n; i++) {
    const [from, to, p] = replayHistory[i];
    const pid = String(p);
    const fromKey = `${from[0]},${from[1]}`;
    const toKey = `${to[0]},${to[1]}`;
    if (pieceSets[pid]) {
      pieceSets[pid].delete(fromKey);
      pieceSets[pid].add(toKey);
    }
  }

  // 计算每个玩家的分数
  for (const pid in pieceSets) {
    const goalSet = goalSetsByPid[parseInt(pid)];
    if (!goalSet) continue;
    let sc = 0;
    for (const posKey of pieceSets[pid]) {
      if (goalSet.has(posKey)) sc++;
    }
    scores[pid] = sc;
  }

  // 转换回数组
  const resultPieces = {};
  for (const pid in pieceSets) {
    resultPieces[pid] = Array.from(pieceSets[pid]).map(k => {
      const [r, c] = k.split(',').map(Number);
      return [r, c];
    });
  }

  const lastMove = n > 0 ? replayHistory[n - 1] : null;
  const curPlayer = n < replayHistory.length
    ? replayHistory[n][2]
    : (lastMove ? ((lastMove[2] + 3) % 6) : 0);

  // 检查胜利
  let winner = null;
  for (const pid of activePlayers) {
    if ((scores[pid] || 0) >= 10) { winner = parseInt(pid); break; }
  }

  gameState = {
    current_player: curPlayer,
    active_players: activePlayers,
    pieces: resultPieces,
    scores: scores,
    move_count: n,
    winner: winner,
    is_terminal: winner !== null,
  };

  selectedPiece = null;
  legalMoves = [];
  if (n === replayHistory.length && winner !== null && !victorySpawned) {
    const wcolor = _pc(winner);
    spawnVictoryParticles(wcolor);
    victorySpawned = true;
  }
  if (n < replayHistory.length) {
    victorySpawned = false;
    victoryParticles = [];
  }

  updateUI();
  draw();
}

function replayNext() {
  if (replayStep < replayHistory.length) {
    replayStepTo(replayStep + 1);
  }
}

function replayPrev() {
  if (replayStep > 0) {
    replayStepTo(replayStep - 1);
  }
}

function exitReplay() {
  replayMode = false;
  replayStep = 0;
  replayHistory = [];
  replayBasePieces = {};
  document.getElementById('replayControls').style.display = 'none';

  if (replayOrigState) {
    gameState = replayOrigState;
    replayOrigState = null;
    updateUI();
    draw();
  }
}


// ═══════════════════════════════════════════════════
// UI 更新
// ═══════════════════════════════════════════════════

function updateUI() {
  if (!gameState) return;

  const cur = gameState.current_player;
  const turnEl = document.getElementById('turnInfo');
  turnEl.textContent = `🎯 ${PLAYER_NAMES[cur]}回合`;
  turnEl.style.color = _pc(cur);

  document.getElementById('moveCount').textContent =
    replayMode
      ? `回放: 第 ${replayStep} / ${replayHistory.length} 步`
      : `步数: ${gameState.move_count}`;

  // 回放步数标签
  const rsl = document.getElementById('replayStepLabel');
  if (rsl && replayMode) {
    rsl.textContent = `第 ${replayStep} / ${replayHistory.length} 步`;
  }

  // 进度条
  const barsEl = document.getElementById('progressBars');
  const active = gameState.active_players || [0, 3];
  barsEl.innerHTML = active.map(pid => {
    const score = gameState.scores[pid] || 0;
    const pct = Math.round(score / 10 * 100);
    const color = _pc(pid);
    return `<div class="progress-row">
      <span class="progress-dot" style="background:${color};box-shadow:0 0 8px ${color}"></span>
      <span class="progress-name">${PLAYER_NAMES[pid]}</span>
      <div class="progress-bar-bg">
        <div class="progress-bar-fill" style="width:${pct}%;background:${color};color:${color}"></div>
      </div>
      <span style="font-size:0.7em">${score}/10</span>
    </div>`;
  }).join('');

  // 胜负
  if (gameState.winner !== null) {
    turnEl.textContent = `🏆 ${PLAYER_NAMES[gameState.winner]}获胜!`;
    turnEl.style.color = _pc(gameState.winner);
    turnEl.style.fontWeight = '900';
    if (!victorySpawned) {
      victorySpawned = true;
      AudioEngine.playVictory();
      spawnVictoryParticles(_pc(gameState.winner));
    }
  }
}


// ═══════════════════════════════════════════════════
// Canvas 渲染
// ═══════════════════════════════════════════════════

function draw() {
  if (!ctx) return;
  ctx.clearRect(0, 0, canvasW, canvasH);

  // ── 背景网格 ──
  drawBackground();

  // ── 连线（棋盘骨架） ──
  drawConnections();

  // ── 孔位 ──
  drawHoles();

  // ── 棋子 ──
  drawPieces();

  // ── 高亮 ──
  drawHighlights();

  // ── 粒子 ──
  drawParticles();

  // ── 胜利粒子 ──
  drawVictoryParticles();
}

function drawBackground() {
  ctx.fillStyle = Theme.get('--bg-canvas') || '#1a1a2e';
  ctx.fillRect(0, 0, canvasW, canvasH);

  // 起点三角区域标记
  if (gameState && gameState.active_players) {
    const zoneAlphas = {0:0.18, 1:0.14, 2:0.14, 3:0.18, 4:0.14, 5:0.14};
    const zones = {
      0: [[0,8],[1,7],[1,8],[2,7],[2,8],[2,9],[3,6],[3,7],[3,8],[3,9]],
      1: [[4,11],[4,12],[4,13],[4,14],[5,11],[5,12],[5,13],[6,12],[6,13],[7,12]],
      2: [[9,12],[10,12],[10,13],[11,11],[11,12],[11,13],[12,11],[12,12],[12,13],[12,14]],
      3: [[13,6],[13,7],[13,8],[13,9],[14,7],[14,8],[14,9],[15,7],[15,8],[16,8]],
      4: [[9,3],[10,3],[10,4],[11,2],[11,3],[11,4],[12,2],[12,3],[12,4],[12,5]],
      5: [[4,2],[4,3],[4,4],[4,5],[5,2],[5,3],[5,4],[6,3],[6,4],[7,3]],
    };
    for (const pid of gameState.active_players) {
      if (!zones[pid]) continue;
      const c = _pc(pid);
      const rgb = hexToRgb(c);
      ctx.fillStyle = `rgba(${rgb.r},${rgb.g},${rgb.b},${zoneAlphas[pid]||0.06})`;
      for (const [r, col] of zones[pid]) {
        const key = `${r},${col}`;
        if (holeCoords[key]) {
          const {x, y} = holeCoords[key];
          ctx.beginPath();
          ctx.arc(x, y, cfg.holeRadius + 4, 0, Math.PI * 2);
          ctx.fill();
        }
      }
    }
  }

  // 六边形网格纹理
  ctx.strokeStyle = Theme.get('--board-hex') || 'rgba(255,255,255,0.04)';
  ctx.lineWidth = 0.5;
  for (let x = 0; x < canvasW; x += 40) {
    for (let y = 0; y < canvasH; y += 35) {
      ctx.beginPath();
      for (let i = 0; i < 6; i++) {
        const angle = Math.PI / 3 * i - Math.PI / 6;
        const hx = x + 12 * Math.cos(angle);
        const hy = y + 12 * Math.sin(angle);
        i === 0 ? ctx.moveTo(hx, hy) : ctx.lineTo(hx, hy);
      }
      ctx.closePath();
      ctx.stroke();
    }
  }
}

function drawConnections() {
  ctx.strokeStyle = Theme.get('--board-line') || 'rgba(255,255,255,0.18)';
  ctx.lineWidth = 1;
  for (const [r, c] of validHoles) {
    const { x: x1, y: y1 } = holeCoords[`${r},${c}`];
    const evenDirs = [[-1,-1],[-1,0],[0,-1],[0,1],[1,-1],[1,0]];
    const oddDirs = [[-1,0],[-1,1],[0,-1],[0,1],[1,0],[1,1]];
    const dirs = r % 2 === 0 ? evenDirs : oddDirs;
    for (const [dr, dc] of dirs) {
      const nr = r + dr, nc = c + dc;
      const key = `${nr},${nc}`;
      if (holeSet.has(key)) {
        const { x: x2, y: y2 } = holeCoords[key];
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();
      }
    }
  }
}

function drawHoles() {
  for (const [r, c] of validHoles) {
    const { x, y } = holeCoords[`${r},${c}`];

    // 孔位（深色底 + 亮色边框）
    ctx.beginPath();
    ctx.arc(x, y, cfg.holeRadius + 2, 0, Math.PI * 2);
    ctx.fillStyle = Theme.get('--hole-outer') || '#2a2a44';
    ctx.fill();
    ctx.strokeStyle = Theme.get('--hole-stroke') || 'rgba(255,255,255,0.3)';
    ctx.lineWidth = 1.2;
    ctx.stroke();

    // 内圈
    ctx.beginPath();
    ctx.arc(x, y, cfg.holeRadius - 2, 0, Math.PI * 2);
    ctx.fillStyle = Theme.get('--hole-inner') || '#1e1e35';
    ctx.fill();
  }
}

function drawPieces() {
  if (!gameState || !gameState.pieces) return;

  const pieces = gameState.pieces;
  for (const pidStr in pieces) {
    const pid = parseInt(pidStr);
    const color = _pc(pid);

    for (const [r, c] of pieces[pidStr]) {
      const key = `${r},${c}`;
      if (!holeCoords[key]) continue;
      const { x, y } = holeCoords[key];

      // 棋子阴影
      ctx.beginPath();
      ctx.arc(x + 2, y + 3, cfg.pieceRadius, 0, Math.PI * 2);
      ctx.fillStyle = Theme.get('--piece-shadow') || 'rgba(0,0,0,0.4)';
      ctx.fill();

      // 棋子主体
      const grad = ctx.createRadialGradient(x - 3, y - 4, 2, x, y, cfg.pieceRadius);
      grad.addColorStop(0, Theme.get('--piece-highlight') || '#ffffff');
      grad.addColorStop(0.35, color);
      grad.addColorStop(1, Theme.get('--piece-grad-dark') || '#111111');
      ctx.beginPath();
      ctx.arc(x, y, cfg.pieceRadius, 0, Math.PI * 2);
      ctx.fillStyle = grad;
      ctx.fill();
      ctx.strokeStyle = Theme.get('--piece-stroke') || 'rgba(255,255,255,0.4)';
      ctx.lineWidth = 1.5;
      ctx.stroke();

      // 高光点
      ctx.beginPath();
      ctx.arc(x - 3, y - 4, 3, 0, Math.PI * 2);
      ctx.fillStyle = Theme.get('--piece-highlight') || 'rgba(255,255,255,0.6)';
      ctx.fill();
    }
  }
}

function drawHighlights() {
  // 选中的棋子
  if (selectedPiece) {
    const [r, c] = selectedPiece;
    const key = `${r},${c}`;
    if (!holeCoords[key]) return;
    const { x, y } = holeCoords[key];
    ctx.beginPath();
    ctx.arc(x, y, cfg.pieceRadius + 5, 0, Math.PI * 2);
    ctx.strokeStyle = Theme.get('--text-primary') || '#ffffff';
    ctx.lineWidth = 3;
    ctx.stroke();

    // 外发光环
    ctx.beginPath();
    ctx.arc(x, y, cfg.pieceRadius + 8, 0, Math.PI * 2);
    ctx.strokeStyle = Theme.get('--selection-glow') || 'rgba(255,255,255,0.3)';
    ctx.lineWidth = 2;
    ctx.stroke();
  }

  // 合法走法
  for (const [tr, tc] of legalMoves) {
    const key = `${tr},${tc}`;
    if (!holeCoords[key]) continue;
    const { x, y } = holeCoords[key];

    const pulse = 0.6 + 0.4 * Math.sin(Date.now() / 300);
    const legalColor = Theme.get('--legal-move') || '#2ecc71';
    const legalAlpha = parseFloat(Theme.get('--legal-move-alpha') || '0.35');
    ctx.beginPath();
    ctx.arc(x, y, cfg.pieceRadius, 0, Math.PI * 2);
    ctx.fillStyle = legalColor.startsWith('#')
      ? `rgba(${hexToRgb(legalColor).r},${hexToRgb(legalColor).g},${hexToRgb(legalColor).b},${legalAlpha * pulse})`
      : legalColor;
    ctx.fill();
    ctx.strokeStyle = legalColor.startsWith('#')
      ? `rgba(${hexToRgb(legalColor).r},${hexToRgb(legalColor).g},${hexToRgb(legalColor).b},${(legalAlpha + 0.35) * pulse})`
      : legalColor;
    ctx.lineWidth = 2.5;
    ctx.stroke();
  }
}

// 粒子系统
let particles = [];
function spawnParticles(x, y, color) {
  for (let i = 0; i < 8; i++) {
    particles.push({
      x, y,
      vx: (Math.random() - 0.5) * 3,
      vy: (Math.random() - 0.5) * 3,
      life: 1.0,
      decay: 0.02 + Math.random() * 0.04,
      color,
    });
  }
}

function drawParticles() {
  for (let i = particles.length - 1; i >= 0; i--) {
    const p = particles[i];
    p.x += p.vx;
    p.y += p.vy;
    p.life -= p.decay;
    if (p.life <= 0) {
      particles.splice(i, 1);
      continue;
    }
    ctx.beginPath();
    ctx.arc(p.x, p.y, 2 * p.life, 0, Math.PI * 2);
    ctx.fillStyle = p.color.replace(')', `,${p.life * 0.8})`).replace('rgb', 'rgba');
    ctx.fill();
  }
}

// ── 胜利粒子 ──────────────────────────────────────

function spawnVictoryParticles(color) {
  for (let i = 0; i < 80; i++) {
    victoryParticles.push({
      x: centerX + (Math.random() - 0.5) * 500,
      y: centerY + (Math.random() - 0.5) * 400,
      vx: (Math.random() - 0.5) * 10,
      vy: (Math.random() - 0.5) * 10 - 3,
      life: 1,
      decay: 0.004 + Math.random() * 0.012,
      size: 2 + Math.random() * 5,
      color,
    });
  }
}

function drawVictoryParticles() {
  for (let i = victoryParticles.length - 1; i >= 0; i--) {
    const p = victoryParticles[i];
    p.x += p.vx;
    p.y += p.vy;
    p.vy += 0.06;
    p.life -= p.decay;
    if (p.life <= 0) { victoryParticles.splice(i, 1); continue; }
    ctx.beginPath();
    ctx.arc(p.x, p.y, p.size * p.life, 0, Math.PI * 2);
    const rgb = hexToRgb(p.color);
    ctx.fillStyle = `rgba(${rgb.r},${rgb.g},${rgb.b},${p.life})`;
    ctx.fill();
  }
}

// ── 颜色工具 ──────────────────────────────────────

function hexToRgb(hex) {
  const r = parseInt(hex.slice(1,3), 16);
  const g = parseInt(hex.slice(3,5), 16);
  const b = parseInt(hex.slice(5,7), 16);
  return {r, g, b};
}


// ═══════════════════════════════════════════════════
// 鼠标交互
// ═══════════════════════════════════════════════════

function handleCanvasClick(e) {
  if (!gameState || gameState.is_terminal || replayMode) return;

  const rect = canvas.getBoundingClientRect();
  const scaleX = canvasW / rect.width;
  const scaleY = canvasH / rect.height;
  const px = (e.clientX - rect.left) * scaleX;
  const py = (e.clientY - rect.top) * scaleY;

  const grid = pixelToGrid(px, py);
  if (!grid) {
    selectedPiece = null;
    legalMoves = [];
    draw();
    return;
  }

  const [r, c] = grid;
  const curPlayer = gameState.current_player;
  const pieces = gameState.pieces[curPlayer] || [];

  // 点击己方棋子
  const isOwn = pieces.some(([pr, pc]) => pr === r && pc === c);
  if (isOwn) {
    selectedPiece = [r, c];
    AudioEngine.playSelect();
    fetchLegalMoves(r, c);
    draw();
    return;
  }

  // 点击合法目标
  const isLegal = legalMoves.some(([mr, mc]) => mr === r && mc === c);
  if (isLegal && selectedPiece) {
    const from = selectedPiece;
    selectedPiece = null;
    legalMoves = [];
    const { x, y } = holeCoords[`${r},${c}`];
    AudioEngine.playMove();
    spawnParticles(x, y, _pc(curPlayer));
    doMove(from, [r, c]);
    return;
  }

  // 其他：取消选中
  selectedPiece = null;
  legalMoves = [];
  draw();
}

async function fetchLegalMoves(r, c) {
  try {
    const resp = await fetch(`/api/legal_moves?r=${r}&c=${c}`);
    if (!resp.ok) { legalMoves = []; return; }
    const data = await resp.json();
    legalMoves = data.targets || [];
  } catch (e) {
    legalMoves = [];
  }
}


// ═══════════════════════════════════════════════════
// 动画循环
// ═══════════════════════════════════════════════════

function animate() {
  draw();
  requestAnimationFrame(animate);
}


// ═══════════════════════════════════════════════════
// 主题管理
// ═══════════════════════════════════════════════════

const THEMES = ['minimal-dark', 'minimal-light', 'ios-dark', 'ios-light', 'cartoon-dark', 'cartoon-light'];
const THEME_LABELS = {
  'minimal-dark': '极简·暗', 'minimal-light': '极简·亮',
  'ios-dark': 'iOS·暗', 'ios-light': 'iOS·亮',
  'cartoon-dark': '卡通·暗', 'cartoon-light': '卡通·亮',
};

function initTheme() {
  // 从 localStorage 恢复主题
  let saved = null;
  try { saved = localStorage.getItem('cc-theme'); } catch(e){}
  if (saved && THEMES.includes(saved)) {
    applyTheme(saved);
  } else {
    applyTheme('minimal-dark');
  }
  // 刷新主题选择器高亮
  updateThemePickerUI();
  // 刷新 BGM 风格选择器高亮
  updateBgmStyleUI();
}

function applyTheme(name) {
  document.body.setAttribute('data-theme', name);
  Theme.refresh();
  try { localStorage.setItem('cc-theme', name); } catch(e){}
  // BGM 已解耦，不再随主题切换
  updateThemePickerUI();
}

function updateThemePickerUI() {
  const current = document.body.getAttribute('data-theme') || 'minimal-dark';
  document.querySelectorAll('.theme-dot').forEach(dot => {
    dot.classList.toggle('active', dot.dataset.theme === current);
  });
}

// 暴露到全局供 HTML onclick 使用
window.applyTheme = applyTheme;
window.toggleBGM = toggleBGM_global;
window.setBGMVolume_global = setBGMVolume_global;
window.setBgmStyle = setBgmStyle_global;

function toggleBGM_global() {
  if (AudioEngine.isBGMPlaying()) {
    AudioEngine.stopBGM();
  } else {
    AudioEngine.startBGM(AudioEngine.getBgmStyle());
  }
  updateAudioUI();
}

function setBgmStyle_global(style) {
  AudioEngine.setBgmStyle(style);
  updateBgmStyleUI();
}

function updateBgmStyleUI() {
  const cur = AudioEngine.getBgmStyle();
  document.querySelectorAll('.bgm-style-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.style === cur);
  });
}

function setBGMVolume_global(v) {
  AudioEngine.setBGMVolume(parseFloat(v));
}

function updateAudioUI() {
  const btn = document.getElementById('bgmToggle');
  if (btn) {
    const on = AudioEngine.isBGMPlaying();
    btn.textContent = on ? '🔊' : '🔇';
    btn.classList.toggle('on', on);
  }
  const vol = document.getElementById('bgmVolume');
  if (vol) vol.value = AudioEngine.getBGMVolume();
}

// ═══════════════════════════════════════════════════
// 启动
// ═══════════════════════════════════════════════════

window.addEventListener('DOMContentLoaded', () => {
  init();
  animate();
  updateAudioUI();
});
