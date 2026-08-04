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

// Canvas
let canvas, ctx;
let canvasW, canvasH;
let centerX, centerY;

// 颜色配置（高对比版）
const PLAYER_COLORS = {
  0: '#e74c3c', 1: '#3498db', 2: '#2ecc71',
  3: '#f1c40f', 4: '#9b59b6', 5: '#e67e22',
};
const PLAYER_NAMES = {
  0: '红方', 1: '蓝方', 2: '绿方',
  3: '黄方', 4: '紫方', 5: '橙方',
};


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
  gameMode = document.getElementById('modeSelect').value;
  difficulty = parseInt(document.getElementById('diffSelect').value);
  const numPlayers = parseInt(document.getElementById('playerCount').value);
  const apiKey = document.getElementById('apiKeyInput').value.trim();
  const humanFirst = document.getElementById('firstSelect').value === 'human';

  const resp = await fetch('/api/new_game', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ num_players: numPlayers, mode: gameMode, difficulty, api_key: apiKey, human_first: humanFirst }),
  });
  gameState = await resp.json();
  selectedPiece = null;
  legalMoves = [];
  victorySpawned = false;
  victoryParticles = [];

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
  const r = await fetch('/api/ai_move', { method: 'POST' });
  gameState = await r.json();
  updateUI();
  draw();

  // LLM 点评
  if (gameState.ai_move) {
    fetch('/api/comment').then(r => r.json()).then(data => {
      if (data.comment) {
        document.getElementById('commentCard').style.display = 'block';
        document.getElementById('commentText').textContent = data.comment;
      }
    }).catch(() => {});
  }
}

async function undoMove() {
  const resp = await fetch('/api/undo', { method: 'POST' });
  if (!resp.ok) return;
  gameState = await resp.json();
  selectedPiece = null;
  legalMoves = [];
  updateUI();
  draw();
}

async function aiHint() {
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

async function saveReplay() {
  const resp = await fetch('/api/save_replay', { method: 'POST' });
  const data = await resp.json();
  alert(`棋谱已保存: ${data.game_id}`);
  loadReplays();
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
    el.innerHTML = replays.map(r =>
      `<div class="replay-item" onclick="loadReplay('${r.game_id}')">
        📁 ${r.game_id} — ${r.mode} — ${r.saved_at?.slice(0,16) || ''}
      </div>`
    ).join('');
  } catch (e) {
    // ignore
  }
}

async function loadReplay(gid) {
  const resp = await fetch(`/api/load_replay/${gid}`);
  if (!resp.ok) return;
  const data = await resp.json();
  gameState = data.state;
  gameMode = data.mode;
  updateUI();
  draw();
}


// ═══════════════════════════════════════════════════
// UI 更新
// ═══════════════════════════════════════════════════

function updateUI() {
  if (!gameState) return;

  const cur = gameState.current_player;
  const turnEl = document.getElementById('turnInfo');
  turnEl.textContent = `🎯 ${PLAYER_NAMES[cur]}回合`;
  turnEl.style.color = PLAYER_COLORS[cur];

  document.getElementById('moveCount').textContent =
    `步数: ${gameState.move_count}`;

  // 进度条
  const barsEl = document.getElementById('progressBars');
  const active = gameState.active_players || [0, 3];
  barsEl.innerHTML = active.map(pid => {
    const score = gameState.scores[pid] || 0;
    const pct = Math.round(score / 10 * 100);
    const color = PLAYER_COLORS[pid];
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
    turnEl.style.color = PLAYER_COLORS[gameState.winner];
    turnEl.style.fontWeight = '900';
    if (!victorySpawned) {
      victorySpawned = true;
      spawnVictoryParticles(PLAYER_COLORS[gameState.winner]);
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
  ctx.fillStyle = '#1a1a2e';
  ctx.fillRect(0, 0, canvasW, canvasH);

  // 起点三角区域标记
  if (gameState && gameState.active_players) {
    const zoneAlphas = {0:0.18, 1:0.14, 2:0.14, 3:0.18, 4:0.14, 5:0.14};
    const zones = {
      0: [[0,8],[1,7],[1,8],[2,7],[2,8],[2,9],[3,6],[3,7],[3,8],[3,9]],
      1: [[4,11],[4,12],[4,13],[4,14],[5,11],[5,12],[5,13],[6,12],[6,13],[7,12]],
      2: [[9,12],[10,12],[10,13],[11,11],[11,12],[11,13],[12,11],[12,12],[12,13],[12,14]],
      3: [[13,6],[13,7],[13,8],[13,9],[14,7],[14,8],[14,9],[15,7],[15,8],[16,8]],
      4: [[9,3],[10,3],[10,4],[11,3],[11,4],[11,5],[12,2],[12,3],[12,4],[12,5]],
      5: [[4,2],[4,3],[4,4],[4,5],[5,2],[5,3],[5,4],[6,3],[6,4],[7,3]],
    };
    for (const pid of gameState.active_players) {
      if (!zones[pid]) continue;
      const c = PLAYER_COLORS[pid];
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
  ctx.strokeStyle = 'rgba(255,255,255,0.04)';
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
  ctx.strokeStyle = 'rgba(255,255,255,0.18)';
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
    ctx.fillStyle = '#2a2a44';
    ctx.fill();
    ctx.strokeStyle = 'rgba(255,255,255,0.3)';
    ctx.lineWidth = 1.2;
    ctx.stroke();

    // 内圈
    ctx.beginPath();
    ctx.arc(x, y, cfg.holeRadius - 2, 0, Math.PI * 2);
    ctx.fillStyle = '#1e1e35';
    ctx.fill();
  }
}

function drawPieces() {
  if (!gameState || !gameState.pieces) return;

  const pieces = gameState.pieces;
  for (const pidStr in pieces) {
    const pid = parseInt(pidStr);
    const color = PLAYER_COLORS[pid];

    for (const [r, c] of pieces[pidStr]) {
      const key = `${r},${c}`;
      if (!holeCoords[key]) continue;
      const { x, y } = holeCoords[key];

      // 棋子阴影
      ctx.beginPath();
      ctx.arc(x + 2, y + 3, cfg.pieceRadius, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(0,0,0,0.4)';
      ctx.fill();

      // 棋子主体
      const grad = ctx.createRadialGradient(x - 3, y - 4, 2, x, y, cfg.pieceRadius);
      grad.addColorStop(0, '#ffffff');
      grad.addColorStop(0.35, color);
      grad.addColorStop(1, '#111111');
      ctx.beginPath();
      ctx.arc(x, y, cfg.pieceRadius, 0, Math.PI * 2);
      ctx.fillStyle = grad;
      ctx.fill();
      ctx.strokeStyle = 'rgba(255,255,255,0.4)';
      ctx.lineWidth = 1.5;
      ctx.stroke();

      // 高光点
      ctx.beginPath();
      ctx.arc(x - 3, y - 4, 3, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(255,255,255,0.6)';
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
    ctx.strokeStyle = '#ffffff';
    ctx.lineWidth = 3;
    ctx.stroke();

    // 外发光环
    ctx.beginPath();
    ctx.arc(x, y, cfg.pieceRadius + 8, 0, Math.PI * 2);
    ctx.strokeStyle = 'rgba(255,255,255,0.3)';
    ctx.lineWidth = 2;
    ctx.stroke();
  }

  // 合法走法
  for (const [tr, tc] of legalMoves) {
    const key = `${tr},${tc}`;
    if (!holeCoords[key]) continue;
    const { x, y } = holeCoords[key];

    const pulse = 0.6 + 0.4 * Math.sin(Date.now() / 300);
    ctx.beginPath();
    ctx.arc(x, y, cfg.pieceRadius, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(46,204,113,${0.35 * pulse})`;
    ctx.fill();
    ctx.strokeStyle = `rgba(46,204,113,${0.7 * pulse})`;
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
  if (!gameState || gameState.is_terminal) return;

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
    spawnParticles(x, y, PLAYER_COLORS[curPlayer]);
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
// 启动
// ═══════════════════════════════════════════════════

window.addEventListener('DOMContentLoaded', () => {
  init();
  animate();
});
