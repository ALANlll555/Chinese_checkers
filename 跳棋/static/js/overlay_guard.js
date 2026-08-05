(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.OverlayGuard = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  function key(position) { return `${Number(position[0])},${Number(position[1])}`; }
  function validPosition(value, validSet) {
    return Array.isArray(value) && value.length === 2 &&
      Number.isInteger(Number(value[0])) && Number.isInteger(Number(value[1])) &&
      validSet.has(key(value));
  }
  function ownerAt(state, position) {
    for (const [pid, pieces] of Object.entries(state?.pieces || {})) {
      if ((pieces || []).some(piece => key(piece) === key(position))) return Number(pid);
    }
    return null;
  }
  function occupied(state, position) { return ownerAt(state, position) !== null; }
  function stateToken(state) {
    const parts = [String(Number(state?.move_count || 0)), String(Number(state?.current_player || 0))];
    const active = [...(state?.active_players || Object.keys(state?.pieces || {}).map(Number))].sort((a,b)=>a-b);
    active.forEach(pid => {
      const positions = [...(state?.pieces?.[pid] || state?.pieces?.[String(pid)] || [])]
        .map(pos => [Number(pos[0]), Number(pos[1])])
        .sort((a,b) => a[0]-b[0] || a[1]-b[1])
        .map(pos => key(pos)).join(';');
      parts.push(`${pid}:${positions}`);
    });
    return parts.join('|');
  }
  function gridToPixel(row, col, geometry) {
    const r = Number(row), c = Number(col);
    const x = Number(geometry.centerX) + (c - 8) * Number(geometry.cellSize) + (r % 2 ? Number(geometry.cellSize) * 0.5 : 0);
    const y = Number(geometry.centerY) + (8 - r) * Number(geometry.cellSize) * 0.866;
    return { x, y };
  }
  function normalizePath(rawPath, from, to, validSet) {
    if (!Array.isArray(rawPath)) return null;
    const path = rawPath.map(pos => [Number(pos?.[0]), Number(pos?.[1])]);
    if (path.length < 2 || path.some(pos => !validPosition(pos, validSet))) return null;
    if (key(path[0]) !== key(from) || key(path[path.length - 1]) !== key(to)) return null;
    return path;
  }
  function validateOverlay(payload, state, validHoles, limit = 5) {
    const validSet = new Set((validHoles || []).map(key));
    const rejected = [];
    if (!payload || payload.read_only !== true) return { ok:false, reason:'not-read-only', moves:[], rejected };
    if (Number(payload.move_count) !== Number(state?.move_count)) return { ok:false, reason:'stale-move-count', moves:[], rejected };
    if (payload.state_token && payload.state_token !== stateToken(state)) return { ok:false, reason:'stale-state-token', moves:[], rejected };
    const expectedPlayer = Number(payload.player_id);
    if (!Number.isInteger(expectedPlayer)) return { ok:false, reason:'missing-player', moves:[], rejected };

    const moves = [];
    for (const [index, raw] of (payload.moves || []).entries()) {
      if (moves.length >= limit) break;
      const from = [Number(raw?.from?.[0]), Number(raw?.from?.[1])];
      const to = [Number(raw?.to?.[0]), Number(raw?.to?.[1])];
      const checks = {
        verified: raw?.verified === true,
        valid_from: validPosition(from, validSet),
        valid_to: validPosition(to, validSet),
        correct_player: Number(raw?.player_id) === expectedPlayer,
        source_owned: ownerAt(state, from) === expectedPlayer,
        target_empty: !occupied(state, to),
      };
      const path = normalizePath(raw?.path, from, to, validSet);
      checks.path_valid = Boolean(path);
      if (!Object.values(checks).every(Boolean)) {
        rejected.push({ index, checks, from, to });
        continue;
      }
      moves.push({
        id: String(raw.id || `candidate-${index + 1}`),
        from, to, path,
        jumpedOver: Array.isArray(raw.jumped_over) ? raw.jumped_over.filter(pos => validPosition(pos, validSet)).map(pos => [Number(pos[0]), Number(pos[1])]) : [],
        pathText: String(raw.path_text || path.map(pos => `(${pos[0]},${pos[1]})`).join(' → ')),
        moveType: String(raw.move_type || (path.length > 2 ? 'jump' : 'step')),
        jumpCount: Number(raw.jump_count || (path.length > 2 ? path.length - 1 : 0)),
        playerId: expectedPlayer,
        rank: Number(raw.rank || index + 1),
        fromLabel: `棋子 (${from[0]},${from[1]})`,
        targetLabel: `目标 (${to[0]},${to[1]})`,
        label: String(raw.label || `候选 ${index + 1}`),
        kind: String(raw.kind || (index === 0 ? 'recommendation' : 'candidate')),
        verified: true,
        validation: raw.validation || checks,
        score: raw.score == null ? null : Number(raw.score),
        scoreDelta: raw.score_delta == null ? null : Number(raw.score_delta),
      });
    }
    return { ok: moves.length > 0, reason: moves.length ? '' : 'no-valid-candidates', moves, rejected, expectedPlayer };
  }
  return { key, validPosition, ownerAt, occupied, stateToken, gridToPixel, validateOverlay };
});
