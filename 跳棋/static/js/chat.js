/**
 * Left-side DeepSeek chat panel.
 * AI output may add a temporary read-only board overlay; it never mutates game state.
 */
const AIChat = (() => {
  let busy = false;
  let active = false;
  let chatAutoFollow = true;
  let chatScrollLock = false;
  let preferences = {
    thinking: true,
    showReasoning: true,
    context1m: true,
  };

  function elements() {
    return {
      messages: document.getElementById('chatMessages'),
      input: document.getElementById('chatInput'),
      send: document.getElementById('chatSendBtn'),
      status: document.getElementById('chatStatus'),
      quick: Array.from(document.querySelectorAll('.chat-quick-row button')),
      deepThink: document.getElementById('deepThinkToggle'),
      context1m: document.getElementById('context1mToggle'),
    };
  }


function isChatNearBottom(messages, threshold = 36) {
  if (!messages) return true;
  const distance =
    messages.scrollHeight
    - messages.scrollTop
    - messages.clientHeight;
  return distance <= threshold;
}

function chatScrollButton(messages) {
  if (!messages) return null;
  const card = messages.closest('.chat-card') || messages.parentElement;
  if (!card) return null;

  let button = card.querySelector('.chat-scroll-bottom');
  if (button) return button;

  button = document.createElement('button');
  button.type = 'button';
  button.className = 'chat-scroll-bottom';
  button.textContent = '↓ 回到底部';
  button.hidden = true;
  button.addEventListener('click', () => {
    chatAutoFollow = true;
    scrollChatMessages(messages, { force: true });
  });
  card.appendChild(button);
  return button;
}

function updateChatScrollButton(messages) {
  const button = chatScrollButton(messages);
  if (!button) return;
  button.hidden = chatAutoFollow || isChatNearBottom(messages);
}

function ensureChatScrollTracking(messages = elements().messages) {
  if (!messages || messages.dataset.scrollTracking === '1') return;
  messages.dataset.scrollTracking = '1';
  chatScrollButton(messages);

  messages.addEventListener('scroll', () => {
    if (chatScrollLock) return;
    chatAutoFollow = isChatNearBottom(messages);
    updateChatScrollButton(messages);
  }, { passive: true });

  messages.addEventListener('wheel', event => {
    if (event.deltaY < 0) {
      chatAutoFollow = false;
      updateChatScrollButton(messages);
    }
  }, { passive: true });

  messages.addEventListener('touchmove', () => {
    if (!isChatNearBottom(messages)) {
      chatAutoFollow = false;
      updateChatScrollButton(messages);
    }
  }, { passive: true });
}

function scrollChatMessages(
  messages,
  { force = false } = {},
) {
  if (!messages) return;
  ensureChatScrollTracking(messages);

  if (force) chatAutoFollow = true;
  if (!chatAutoFollow) {
    updateChatScrollButton(messages);
    return;
  }

  chatScrollLock = true;
  requestAnimationFrame(() => {
    messages.scrollTop = messages.scrollHeight;
    requestAnimationFrame(() => {
      chatScrollLock = false;
      chatAutoFollow = isChatNearBottom(messages);
      updateChatScrollButton(messages);
    });
  });
}

  function readStoredBoolean(key) {
    try {
      const value = localStorage.getItem(key);
      if (value === null) return null;
      return value === '1';
    } catch (_) {
      return null;
    }
  }

  function savePreferences() {
    try {
      localStorage.setItem('cc-deepthink', preferences.thinking ? '1' : '0');
      localStorage.setItem('cc-context-1m', preferences.context1m ? '1' : '0');
    } catch (_) {}
  }

  function syncPreferenceControls() {
    const { deepThink, context1m } = elements();
    if (deepThink) deepThink.checked = preferences.thinking;
    if (context1m) context1m.checked = preferences.context1m;
    document.querySelectorAll(
      '.chat-reasoning, .chat-unit-reasoning'
    ).forEach(panel => {
      panel.hidden = !preferences.showReasoning;
    });
  }

  async function loadPreferences() {
    const storedThinking = readStoredBoolean('cc-deepthink');
    const storedContext = readStoredBoolean('cc-context-1m');
    try {
      const response = await fetch('/api/system/status');
      const status = await response.json();
      preferences.thinking = storedThinking === null
        ? Boolean(status.deepseek_thinking_default)
        : storedThinking;
      preferences.showReasoning = preferences.thinking;
      preferences.context1m = storedContext === null
        ? Boolean(status.deepseek_context_1m_default)
        : storedContext;
    } catch (_) {
      preferences.thinking = storedThinking === null ? true : storedThinking;
      preferences.showReasoning = preferences.thinking;
      preferences.context1m = storedContext === null ? true : storedContext;
    }
    syncPreferenceControls();
  }

function applyGameSettings(settings = {}) {
  if (settings.thinking !== undefined) {
    preferences.thinking = Boolean(settings.thinking);
  }
  if (settings.show_reasoning !== undefined) {
    preferences.showReasoning = Boolean(settings.show_reasoning);
  }
  if (settings.context_1m !== undefined) {
    preferences.context1m = Boolean(settings.context_1m);
  }
  syncPreferenceControls();
  savePreferences();
}

  function setStatus(text, state = '') {
    const { status } = elements();
    if (!status) return;
    status.textContent = text;
    status.dataset.state = state;
  }

  function setEnabled(enabled) {
    active = Boolean(enabled);
    const { input, send, quick } = elements();
    if (!input || !send) return;
    const disabled = !active || busy;
    input.disabled = disabled;
    send.disabled = disabled;
    quick.forEach(button => { button.disabled = disabled; });
    input.placeholder = active ? '询问当前局面、候选走法或策略…' : '请先开始一局游戏';
  }

  function enhanceCoordinateTokens(container) {
    if (!container || !window.ChatFormat || !window.BoardOverlay) return;
    const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) {
      const node = walker.currentNode;
      const parent = node.parentElement;
      if (!parent || parent.closest('code, pre, button, a')) continue;
      nodes.push(node);
    }

    const pattern = /[\(\[（]\s*(\d{1,2})\s*[,，]\s*(\d{1,2})\s*[\)\]）]/g;
    nodes.forEach(node => {
      const value = node.nodeValue || '';
      pattern.lastIndex = 0;
      let match;
      let cursor = 0;
      let changed = false;
      const fragment = document.createDocumentFragment();

      while ((match = pattern.exec(value)) !== null) {
        const row = Number(match[1]);
        const col = Number(match[2]);
        if (!window.BoardOverlay.isValidCoordinate(row, col)) continue;
        changed = true;
        fragment.appendChild(document.createTextNode(value.slice(cursor, match.index)));
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'coordinate-chip';
        button.textContent = `(${row},${col})`;
        button.title = `在棋盘定位坐标（${row},${col}）`;
        button.addEventListener('click', () => {
          window.BoardOverlay.focusCoordinate(row, col);
        });
        fragment.appendChild(button);
        cursor = match.index + match[0].length;
      }

      if (changed) {
        fragment.appendChild(document.createTextNode(value.slice(cursor)));
        node.replaceWith(fragment);
      }
    });
  }

  function showOverlay(overlay, selectedIndex = 0, showCoordinates = false) {
    if (!overlay || !window.BoardOverlay) return;
    const shown = window.BoardOverlay.showAnalysis(overlay);
    if (!shown) {
      setStatus('建议已过期或未通过规则校验，请重新分析', 'warning');
      return;
    }
    if (showCoordinates) window.BoardOverlay.setCoordinates(true);
    const index = Number.isInteger(selectedIndex) ? selectedIndex : 0;
    window.BoardOverlay.selectCandidate(index, { showCoordinates });
    setStatus(`首选：棋子与完整路径已显示（候选 ${index + 1}）`, 'ready');
  }

  function candidateTypeText(move) {
    if (!move.move_type && move.verified === false) return '文本坐标 · 路径待工具验证';
    const path = Array.isArray(move.path) ? move.path : [move.from, move.to];
    const jumpCount = Number(move.jump_count || Math.max(0, path.length - 1));
    if (move.move_type === 'jump' || jumpCount > 0) {
      return `${jumpCount || path.length - 1} 段连跳`;
    }
    return '单步移动';
  }

  function candidatePathText(move) {
    if (move.path_text) return String(move.path_text);
    const path = Array.isArray(move.path) && move.path.length >= 2
      ? move.path
      : [move.from, move.to];
    return path.map(position => `(${position[0]},${position[1]})`).join(' → ');
  }

  function featureDirectionText(feature) {
    return feature.better === 'lower' ? '越低越好' : '越高越好';
  }

  function renderCoachReport(item, report, overlay) {
    if (!item || !report) return;
    const section = document.createElement('section');
    section.className = 'coach-report';

    const header = document.createElement('div');
    header.className = 'coach-report-header';
    const titleWrap = document.createElement('div');
    const eyebrow = document.createElement('span');
    eyebrow.className = 'coach-eyebrow';
    eyebrow.textContent = `${report.phase?.label || '局面'} · 可验证分析`;
    const title = document.createElement('strong');
    title.textContent = report.headline || '局面诊断';
    titleWrap.append(eyebrow, title);
    const confidence = document.createElement('span');
    confidence.className = 'coach-confidence';
    const confidenceValue = Math.round(Number(report.confidence?.value || 0) * 100);
    confidence.textContent = `置信度 ${report.confidence?.label || '中'} ${confidenceValue}%`;
    confidence.title = report.confidence?.basis || '';
    header.append(titleWrap, confidence);
    section.appendChild(header);

    if (report.summary) {
      const summary = document.createElement('p');
      summary.className = 'coach-summary';
      summary.textContent = report.summary;
      section.appendChild(summary);
    }

    const race = document.createElement('div');
    race.className = 'coach-race';
    race.textContent = `竞速位置：第 ${report.race?.rank || '?'} / ${report.race?.total_players || '?'} · ${report.race?.label || ''}`;
    section.appendChild(race);

    const features = report.current?.features || [];
    if (features.length) {
      const grid = document.createElement('div');
      grid.className = 'coach-feature-grid';
      features.forEach(feature => {
        const card = document.createElement('div');
        card.className = 'coach-feature';
        const label = document.createElement('span');
        label.textContent = feature.label;
        const value = document.createElement('strong');
        value.textContent = String(feature.value);
        const direction = document.createElement('small');
        direction.textContent = featureDirectionText(feature);
        card.title = feature.meaning || '';
        card.append(label, value, direction);
        grid.appendChild(card);
      });
      section.appendChild(grid);
    }

    const diagnostics = report.diagnostics || [];
    if (diagnostics.length) {
      const list = document.createElement('div');
      list.className = 'coach-diagnostics';
      diagnostics.slice(0, 3).forEach(diagnostic => {
        const row = document.createElement('div');
        row.className = `coach-diagnostic ${diagnostic.level || 'info'}`;
        const heading = document.createElement('strong');
        heading.textContent = diagnostic.title;
        const evidence = document.createElement('span');
        evidence.textContent = diagnostic.evidence;
        const action = document.createElement('small');
        action.textContent = `下一步：${diagnostic.action}`;
        row.append(heading, evidence, action);
        list.appendChild(row);
      });
      section.appendChild(list);
    }

    if (report.counterfactual?.text) {
      const counter = document.createElement('div');
      counter.className = 'coach-counterfactual';
      counter.innerHTML = '<strong>反事实</strong>';
      const text = document.createElement('span');
      text.textContent = report.counterfactual.text;
      counter.appendChild(text);
      section.appendChild(counter);
    }

    const footer = document.createElement('div');
    footer.className = 'coach-evidence-footer';
    footer.textContent = `检查 ${report.evidence?.legal_moves_examined ?? 0} 条合法走法 · 五项规则评价 · 非私有思维链`;
    section.appendChild(footer);

    item.appendChild(section);
  }

  function renderCandidateDeck(item, overlay, coachReport = null) {
    if (!item || !overlay?.moves?.length) return;

    const section = document.createElement('section');
    section.className = 'chat-candidate-section';

    const heading = document.createElement('div');
    heading.className = 'chat-candidate-heading';
    heading.innerHTML = '<strong>已验证候选</strong><span>首选自动显示起点棋子、路径和目标；点击可切换</span>';
    section.appendChild(heading);

    const deck = document.createElement('div');
    deck.className = 'chat-candidate-deck';

    overlay.moves.slice(0, 5).forEach((move, index) => {
      const card = document.createElement('button');
      card.type = 'button';
      card.className = 'chat-candidate-card';
      if (move.kind === 'recommendation') card.classList.add('recommended');
      card.title = `查看候选 ${index + 1} 的棋子与路径`;

      const rank = document.createElement('span');
      rank.className = 'candidate-rank';
      rank.textContent = String(index + 1);

      const body = document.createElement('span');
      body.className = 'candidate-card-body';

      const target = document.createElement('strong');
      target.textContent = `目标 (${move.to[0]},${move.to[1]})`;

      const source = document.createElement('span');
      source.textContent = `棋子 (${move.from[0]},${move.from[1]})`;

      const meta = document.createElement('span');
      meta.className = 'candidate-card-meta';
      meta.textContent = `${candidateTypeText(move)} · 规则验证通过`;

      const candidate = coachReport?.candidates?.[index];
      const reason = document.createElement('span');
      reason.className = 'candidate-card-reason';
      reason.textContent = candidate?.reason || '';
      const tradeoff = document.createElement('small');
      tradeoff.className = 'candidate-card-tradeoff';
      tradeoff.textContent = candidate?.tradeoff ? `代价：${candidate.tradeoff}` : '';

      body.append(target, source, meta);
      if (reason.textContent) body.appendChild(reason);
      if (tradeoff.textContent) body.appendChild(tradeoff);
      card.append(rank, body);
      card.addEventListener('click', () => showOverlay(overlay, index));
      deck.appendChild(card);
    });

    section.appendChild(deck);

    const pathPreview = document.createElement('details');
    pathPreview.className = 'chat-candidate-paths';
    const summary = document.createElement('summary');
    summary.textContent = '展开全部路径文字';
    pathPreview.appendChild(summary);
    const list = document.createElement('ol');
    overlay.moves.slice(0, 5).forEach((move, index) => {
      const listItem = document.createElement('li');
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = `候选 ${index + 1}：${candidatePathText(move)}`;
      button.addEventListener('click', () => showOverlay(overlay, index, true));
      listItem.appendChild(button);
      list.appendChild(listItem);
    });
    pathPreview.appendChild(list);
    section.appendChild(pathPreview);
    item.appendChild(section);
  }


function createCollapsibleBubble({
  title,
  className = '',
  open = true,
  parent = null,
}) {
  const root = document.createElement('section');
  root.className = `chat-unit ${className}`.trim();

  const header = document.createElement('button');
  header.type = 'button';
  header.className = 'chat-unit-header';
  header.setAttribute('aria-expanded', open ? 'true' : 'false');

  const titleNode = document.createElement('span');
  titleNode.className = 'chat-unit-title';
  titleNode.textContent = title || '消息';

  const summaryNode = document.createElement('span');
  summaryNode.className = 'chat-unit-summary';

  const stateNode = document.createElement('span');
  stateNode.className = 'chat-unit-state';

  const chevron = document.createElement('span');
  chevron.className = 'chat-unit-chevron';
  chevron.textContent = '›';

  header.append(titleNode, summaryNode, stateNode, chevron);

  const body = document.createElement('div');
  body.className = 'chat-unit-body';
  root.append(header, body);

  function setCollapsed(collapsed) {
    const value = Boolean(collapsed);
    root.classList.toggle('is-collapsed', value);
    body.hidden = value;
    header.setAttribute('aria-expanded', value ? 'false' : 'true');
  }

  header.addEventListener('click', () => {
    setCollapsed(!root.classList.contains('is-collapsed'));
  });

  setCollapsed(!open);
  if (parent) parent.appendChild(root);

  return {
    root,
    header,
    body,
    summary: summaryNode,
    state: stateNode,
    setCollapsed,
    setTitle(value) {
      titleNode.textContent = value || '消息';
    },
    setSummary(value) {
      summaryNode.textContent = value || '';
    },
    setState(value, classNameValue = '') {
      stateNode.textContent = value || '';
      stateNode.className =
        `chat-unit-state ${classNameValue}`.trim();
    },
  };
}

function reasoningRoundsFromMetadata(metadata = {}) {
  const transcript = Array.isArray(metadata.agent_messages)
    ? metadata.agent_messages
    : [];
  const rounds = [];
  let round = 0;

  transcript.forEach(message => {
    if (message?.role !== 'assistant') return;
    const reasoning = String(message.reasoning_content || '');
    const processText = String(message.content || '');
    const toolCalls = Array.isArray(message.tool_calls)
      ? message.tool_calls
      : [];

    if (!reasoning && !toolCalls.length) return;
    round += 1;
    rounds.push({
      round,
      reasoning,
      processText: toolCalls.length ? processText : '',
      toolCalls,
    });
  });

  if (!rounds.length && metadata.reasoning_content) {
    rounds.push({
      round: 1,
      reasoning: String(metadata.reasoning_content),
      processText: '',
      toolCalls: [],
    });
  }
  return rounds;
}

function renderReasoning(item, reasoning, meta = {}) {
  if (!item) return [];
  const rounds = Array.isArray(meta.reasoningRounds)
    && meta.reasoningRounds.length
    ? meta.reasoningRounds
    : (
        reasoning
          ? [{
              round: 1,
              reasoning: String(reasoning),
              processText: '',
              toolCalls: [],
            }]
          : []
      );

  return rounds.map((roundData, index) => {
    const round = Number(roundData.round || index + 1);
    const reasoningText = String(roundData.reasoning || '');
    const processText = String(roundData.processText || '');
    const unit = createCollapsibleBubble({
      title: `第 ${round} 轮推理`,
      className: 'chat-unit-reasoning is-complete',
      open: false,
      parent: item,
    });
    unit.root.hidden = !preferences.showReasoning;
    unit.setState('✓', 'is-success');

    const toolCount = Array.isArray(roundData.toolCalls)
      ? roundData.toolCalls.length
      : 0;
    const summary = [];
    if (reasoningText) {
      summary.push(`${reasoningText.length.toLocaleString()} 字`);
    }
    if (toolCount) summary.push(`${toolCount} 个工具`);
    unit.setSummary(summary.join(' · '));

    if (reasoningText) {
      const node = document.createElement('div');
      node.className = 'chat-unit-reasoning-text';
      node.textContent = reasoningText;
      unit.body.appendChild(node);
    }

    if (processText) {
      const node = document.createElement('div');
      node.className = 'chat-unit-process-text';
      node.textContent = processText;
      unit.body.appendChild(node);
    }

    if (!reasoningText && !processText) {
      const node = document.createElement('div');
      node.className = 'chat-unit-empty';
      node.textContent = '本轮没有可显示的推理文字。';
      unit.body.appendChild(node);
    }

    const safetyNote = document.createElement('div');
    safetyNote.className = 'chat-unit-note chat-reasoning-safety';
    safetyNote.textContent =
      '推理过程不参与棋盘合法性与高亮判定。';
    unit.body.appendChild(safetyNote);

    return { unit, roundData };
  });
}

function renderMcpTrace(item, trace = []) {
  if (!item || !Array.isArray(trace) || !trace.length) return [];
  return trace.map((call, index) => {
    const modelRound = Number(call.model_round || 0);
    const title = modelRound
      ? `第 ${modelRound} 轮 MCP 工具调用 · ${call.label || call.name || '工具'}`
      : `MCP 工具调用 ${index + 1} · ${call.label || call.name || '工具'}`;

    const unit = createCollapsibleBubble({
      title,
      className: `chat-unit-tool ${call.success ? 'is-complete' : 'is-error'}`,
      open: false,
      parent: item,
    });
    unit.setState(
      call.success ? '✓' : '×',
      call.success ? 'is-success' : 'is-error'
    );
    unit.setSummary(`${Number(call.duration_ms || 0).toFixed(1)} ms`);

    const internal = document.createElement('div');
    internal.className = 'chat-unit-tool-internal';
    internal.textContent =
      `${call.name || ''} · ${call.source || 'mcp-shared-tool-registry'}`;

    const argsTitle = document.createElement('strong');
    argsTitle.className = 'chat-unit-subtitle';
    argsTitle.textContent = '参数';

    const args = document.createElement('pre');
    args.className = 'chat-unit-code';
    args.textContent = JSON.stringify(call.arguments || {}, null, 2);

    const resultTitle = document.createElement('strong');
    resultTitle.className = 'chat-unit-subtitle';
    resultTitle.textContent = call.success ? '结果' : '错误';

    const result = document.createElement('pre');
    result.className = 'chat-unit-code';
    result.textContent = call.success
      ? String(call.result_preview || '')
      : String(call.error || call.result_preview || '调用失败');

    unit.body.append(internal, argsTitle, args, resultTitle, result);
    return { unit, call };
  });
}

function renderMessage(role, content, meta = {}) {
  const { messages } = elements();
  if (!messages) return null;
  ensureChatScrollTracking(messages);

  const empty = messages.querySelector('.chat-empty');
  if (empty) empty.remove();

  const item = document.createElement('div');
  item.className = `chat-message ${role}`;

  const label = document.createElement('div');
  label.className = 'chat-message-label';
  label.textContent = role === 'user'
    ? '你'
    : role === 'assistant'
      ? 'AI'
      : '系统';
  item.appendChild(label);

  if (role !== 'assistant') {
    const bubble = document.createElement('div');
    bubble.className = 'chat-bubble';
    bubble.textContent = content == null ? '' : String(content);
    item.appendChild(bubble);
    messages.appendChild(item);
    scrollChatMessages(messages, {
      force: role === 'user' && !meta.historical,
    });
    return item;
  }

  const rounds = Array.isArray(meta.reasoningRounds)
    ? meta.reasoningRounds
    : [];
  const trace = Array.isArray(meta.toolTrace)
    ? meta.toolTrace
    : [];
  const renderedCalls = new Set();

  if (rounds.length) {
    rounds.forEach(roundData => {
      renderReasoning(item, '', {
        reasoningRounds: [roundData],
      });
      const callIds = new Set(
        (roundData.toolCalls || [])
          .map(call => call?.id)
          .filter(Boolean)
      );
      const matching = trace.filter(call => {
        if (callIds.has(call.call_id)) {
          renderedCalls.add(call.call_id);
          return true;
        }
        return false;
      });
      renderMcpTrace(item, matching);
    });
  } else {
    renderReasoning(item, meta.reasoning || '', meta);
  }

  renderMcpTrace(
    item,
    trace.filter(call => !renderedCalls.has(call.call_id))
  );

  const answerUnit = createCollapsibleBubble({
    title: '最终回答',
    className: 'chat-unit-answer is-complete',
    open: true,
    parent: item,
  });
  answerUnit.setState('✓', 'is-success');

  const answer = document.createElement('div');
  answer.className = 'chat-bubble chat-final-answer';
  if (window.ChatFormat) {
    answer.innerHTML = window.ChatFormat.renderMarkdown(content);
    enhanceCoordinateTokens(answer);
  } else {
    answer.textContent = content == null ? '' : String(content);
  }
  answerUnit.body.appendChild(answer);

  const answerSummary = [];
  if (Number(meta.elapsedSeconds || 0) > 0) {
    answerSummary.push(`${Number(meta.elapsedSeconds).toFixed(2)} 秒`);
  }
  if (String(content || '').length) {
    answerSummary.push(`${String(content).length.toLocaleString()} 字`);
  }
  answerUnit.setSummary(answerSummary.join(' · '));

  if (meta.historicalOverlayExpired) {
    const unit = createCollapsibleBubble({
      title: '历史局面提示',
      className: 'chat-unit-warning',
      open: false,
      parent: item,
    });
    const node = document.createElement('div');
    node.className = 'chat-unit-note';
    node.textContent =
      '这是历史局面的解释；当前棋盘已经变化，因此旧高亮不会重新显示。';
    unit.body.appendChild(node);
  }

  if (meta.contextUsage?.context_window_tokens) {
    const unit = createCollapsibleBubble({
      title: '上下文与运行信息',
      className: 'chat-unit-context',
      open: true,
      parent: item,
    });
    const used = Number(
      meta.contextUsage.estimated_input_tokens || 0
    ).toLocaleString();
    const windowSize = Number(
      meta.contextUsage.context_window_tokens || 0
    ).toLocaleString();
    const profile =
      meta.contextUsage.context_profile === '1m' ? '1M' : '标准';
    const node = document.createElement('div');
    node.className = 'chat-unit-note';
    node.textContent =
      `${profile} 上下文约 ${used} / ${windowSize} tokens · 规则解释独立校验`;
    unit.body.appendChild(node);
  }

  if (meta.coachReport) {
    const unit = createCollapsibleBubble({
      title: '可验证 Coach 报告',
      className: 'chat-unit-coach',
      open: true,
      parent: item,
    });
    renderCoachReport(unit.body, meta.coachReport, meta.overlay);
  }

  if (meta.overlay?.moves?.length) {
    const unit = createCollapsibleBubble({
      title: `已验证候选 · ${meta.overlay.moves.length} 条`,
      className: 'chat-unit-candidates',
      open: true,
      parent: item,
    });
    renderCandidateDeck(unit.body, meta.overlay, meta.coachReport);

    const actions = document.createElement('div');
    actions.className = 'chat-message-actions';

    const showButton = document.createElement('button');
    showButton.type = 'button';
    showButton.textContent = '显示候选目标';
    showButton.addEventListener(
      'click', () => showOverlay(meta.overlay)
    );

    const firstButton = document.createElement('button');
    firstButton.type = 'button';
    firstButton.textContent = '查看首选路径';
    firstButton.addEventListener(
      'click', () => showOverlay(meta.overlay, 0)
    );

    const coordinateButton = document.createElement('button');
    coordinateButton.type = 'button';
    coordinateButton.textContent = '显示清晰坐标';
    coordinateButton.addEventListener(
      'click', () => showOverlay(meta.overlay, null, true)
    );

    actions.append(showButton, firstButton, coordinateButton);
    unit.body.appendChild(actions);
  }

  messages.appendChild(item);
  scrollChatMessages(messages, {
    force: Boolean(meta.forceScroll),
  });
  return item;
}

function renderTyping() {
  const { messages } = elements();
  if (!messages) return null;
  ensureChatScrollTracking(messages);

  const empty = messages.querySelector('.chat-empty');
  if (empty) empty.remove();

  const item = document.createElement('div');
  item.className = 'chat-message assistant chat-process-turn';

  const label = document.createElement('div');
  label.className = 'chat-message-label';
  label.textContent = 'AI';
  item.appendChild(label);

  // Mount the live assistant turn before any SSE event arrives. Without this,
  // reasoning, MCP tools and the final answer update a detached DOM subtree.
  messages.appendChild(item);
  scrollChatMessages(messages, { force: true });

  const processStarted = performance.now();
  const roundUnits = new Map();
  const toolNodes = new Map();
  const toolDraftNodes = new Map();
  const seenEvents = new Set();

  let activeRound = 0;
  let finalResult = null;
  let answerBuffer = '';
  let answerUnit = null;
  let answerNode = null;
  let finishApplied = false;
  let errorShown = false;

  const taskUnit = createCollapsibleBubble({
    title: 'Agent 任务状态',
    className: 'chat-unit-task is-active',
    open: false,
    parent: item,
  });
  taskUnit.setState('●', 'is-running');
  taskUnit.summary.classList.add('chat-live-timer');
  taskUnit.setSummary('0.0 秒');

  const taskTimeline = document.createElement('div');
  taskTimeline.className = 'chat-process-phase-list';
  taskUnit.body.appendChild(taskTimeline);

  const taskTimer = window.setInterval(() => {
    taskUnit.setSummary(
      `${((performance.now() - processStarted) / 1000).toFixed(1)} 秒`
    );
  }, 100);

  function scroll() {
    scrollChatMessages(messages);
  }

  function setPhase(text) {
    if (!text) return;
    const last = taskTimeline.lastElementChild;
    if (last?.dataset?.label === text) return;

    const row = document.createElement('div');
    row.className = 'chat-process-phase';
    row.dataset.label = text;
    row.textContent =
      `${((performance.now() - processStarted) / 1000).toFixed(1)} 秒 · ${text}`;
    taskTimeline.appendChild(row);

    while (taskTimeline.children.length > 12) {
      taskTimeline.firstElementChild?.remove();
    }
    scroll();
  }

  function eventSignature(event) {
    if (!event || !event.type) return '';
    if (['reasoning', 'content_delta', 'tool_delta'].includes(event.type)) {
      return '';
    }
    return JSON.stringify([
      event.type,
      event.round,
      event.model_round,
      event.id,
      event.call_id,
      event.phase,
      event.label,
      event.finish_reason,
    ]);
  }

  function acceptEvent(event) {
    const signature = eventSignature(event);
    if (!signature) return true;
    if (seenEvents.has(signature)) return false;
    seenEvents.add(signature);
    return true;
  }

  function normalizeRound(value) {
    const parsed = Number(value || 0);
    return Number.isInteger(parsed) && parsed > 0
      ? parsed
      : (activeRound || 1);
  }

  function ensureRound(value) {
    const round = normalizeRound(value);
    activeRound = Math.max(activeRound, round);
    if (roundUnits.has(round)) return roundUnits.get(round);

    const unit = createCollapsibleBubble({
      title: `第 ${round} 轮推理`,
      className: 'chat-unit-reasoning is-active',
      open: false,
      parent: item,
    });
    unit.root.hidden = !preferences.showReasoning;
    unit.setState('●', 'is-running');
    unit.setSummary('0 字 · 0.0 秒');

    const status = document.createElement('div');
    status.className = 'chat-round-status';
    status.textContent = '等待 DeepSeek 增量';

    const reasoning = document.createElement('div');
    reasoning.className = 'chat-unit-reasoning-text';

    const draft = document.createElement('div');
    draft.className = 'chat-process-draft-text';
    draft.hidden = true;

    unit.body.append(status, reasoning, draft);

    const state = {
      round,
      unit,
      status,
      reasoning,
      draft,
      reasoningText: '',
      draftText: '',
      chunkCount: 0,
      completed: false,
      started: performance.now(),
    };

    state.timer = window.setInterval(() => {
      if (state.completed) return;
      unit.setSummary(
        `${state.reasoningText.length.toLocaleString()} 字 · `
        + `${((performance.now() - state.started) / 1000).toFixed(1)} 秒`
      );
    }, 100);

    roundUnits.set(round, state);
    return state;
  }

  function updateRoundStatus(value, text) {
    const state = ensureRound(value);
    if (text) state.status.textContent = text;
  }

  function addReasoning(text, value) {
    if (!text) return;
    const state = ensureRound(value);
    state.reasoningText += text;
    state.reasoning.textContent = state.reasoningText;
    state.chunkCount += 1;
    state.unit.setSummary(
      `${state.reasoningText.length.toLocaleString()} 字 · `
      + `${state.chunkCount} 个增量`
    );
    state.status.textContent = '正在接收 reasoning_content';
    scroll();
  }

  function addContentDelta(text, value) {
    if (!text) return;
    const state = ensureRound(value);
    state.draftText += text;
    state.draft.hidden = false;
    state.draft.textContent = state.draftText;
    state.status.textContent = '正在接收模型过程文字';
    scroll();
  }

  function completeRound(value, event = {}) {
    const state = ensureRound(value);
    if (state.completed) return;
    state.completed = true;
    window.clearInterval(state.timer);
    state.unit.root.classList.remove('is-active');
    state.unit.root.classList.add('is-complete');
    state.unit.setState('✓', 'is-success');

    const parts = [];
    if (state.reasoningText.length) {
      parts.push(`${state.reasoningText.length.toLocaleString()} 字`);
    }
    const elapsed = Number(event.elapsed_seconds || 0);
    if (elapsed > 0) parts.push(`${elapsed.toFixed(2)} 秒`);
    const chunks = Number(event.chunk_count || state.chunkCount || 0);
    if (chunks > 0) parts.push(`${chunks} 个增量`);
    state.unit.setSummary(parts.join(' · '));
    state.status.textContent =
      `本轮结束${event.finish_reason ? ` · ${event.finish_reason}` : ''}`;
  }

  function toolDraftKey(event) {
    return `${normalizeRound(event.round || event.model_round)}:${Number(event.index || 0)}`;
  }

  function toolDelta(event) {
    const modelRound = normalizeRound(event.round || event.model_round);
    ensureRound(modelRound);
    const key = toolDraftKey(event);
    let unit = toolDraftNodes.get(key);

    if (!unit) {
      unit = createCollapsibleBubble({
        title: `第 ${modelRound} 轮工具参数`,
        className: 'chat-process-tool is-planning chat-unit-tool',
        open: false,
        parent: item,
      });
      unit.setState('●', 'is-running');

      const name = document.createElement('div');
      name.className = 'chat-unit-tool-internal';
      name.textContent = '正在生成工具名称';

      const args = document.createElement('pre');
      args.className = 'chat-unit-code';

      unit.body.append(name, args);
      unit._name = name;
      unit._args = args;
      toolDraftNodes.set(key, unit);
    }

    if (event.name) {
      unit.setTitle(`第 ${modelRound} 轮工具参数 · ${event.name}`);
      unit._name.textContent = event.name;
    }
    unit._args.textContent = String(event.arguments || '');
    unit.setSummary(`${unit._args.textContent.length} 字符`);
    scroll();
  }

  function removeToolDraft(event) {
    const modelRound = normalizeRound(event.model_round || event.round);
    const index = Math.max(0, Number(event.tool_index || 1) - 1);
    const key = `${modelRound}:${index}`;
    const unit = toolDraftNodes.get(key);
    if (unit) unit.root.remove();
    toolDraftNodes.delete(key);
  }

  function toolKey(event) {
    const modelRound = normalizeRound(event.model_round || event.round);
    return String(
      event.call_id
      || event.id
      || `${modelRound}:${event.tool_index || 0}:${event.name || 'tool'}`
    );
  }

  function toolStart(event) {
    removeToolDraft(event);
    setPhase(`MCP 正在调用：${event.label || event.name || '工具'}`);

    const modelRound = normalizeRound(event.model_round || event.round);
    const key = toolKey(event);
    if (toolNodes.has(key)) return toolNodes.get(key);

    const unit = createCollapsibleBubble({
      title:
        `第 ${modelRound} 轮 MCP 工具调用 · ${event.label || event.name || '工具'}`,
      className: 'chat-process-tool is-running chat-unit-tool',
      open: false,
      parent: item,
    });
    unit.setState('●', 'is-running');
    unit.setSummary('运行中');

    const internal = document.createElement('div');
    internal.className = 'chat-unit-tool-internal';
    internal.textContent =
      `${event.name || ''} · ${event.source || 'mcp-shared-tool-registry'}`;

    const argsTitle = document.createElement('strong');
    argsTitle.className = 'chat-unit-subtitle';
    argsTitle.textContent = '参数';

    const args = document.createElement('pre');
    args.className = 'chat-unit-code';
    args.textContent = JSON.stringify(event.arguments || {}, null, 2);

    const resultTitle = document.createElement('strong');
    resultTitle.className = 'chat-unit-subtitle';
    resultTitle.textContent = '结果';
    resultTitle.hidden = true;

    const result = document.createElement('pre');
    result.className = 'chat-unit-code';
    result.hidden = true;

    unit.body.append(internal, argsTitle, args, resultTitle, result);
    const state = {
      unit,
      resultTitle,
      result,
      complete: false,
    };
    toolNodes.set(key, state);
    scroll();
    return state;
  }

  function toolEnd(event) {
    const state = toolNodes.get(toolKey(event)) || toolStart(event);
    if (state.complete) return;
    state.complete = true;

    state.unit.root.classList.remove('is-running');
    state.unit.root.classList.add(
      event.success ? 'is-complete' : 'is-error'
    );
    state.unit.setState(
      event.success ? '✓' : '×',
      event.success ? 'is-success' : 'is-error'
    );
    state.unit.setSummary(
      `${Number(event.duration_ms || 0).toFixed(1)} ms`
    );

    state.resultTitle.hidden = false;
    state.resultTitle.textContent = event.success ? '结果' : '错误';
    state.result.hidden = false;
    state.result.textContent = event.success
      ? String(event.result_preview || '')
      : String(event.error || event.result_preview || '调用失败');

    if (!event.success) state.unit.setCollapsed(false);
    setPhase(
      event.success
        ? `MCP 完成：${event.label || event.name || '工具'}`
        : `MCP 失败：${event.label || event.name || '工具'}`
    );
    scroll();
  }

  function ensureAnswerUnit() {
    if (answerUnit) return answerUnit;
    answerUnit = createCollapsibleBubble({
      title: '最终回答',
      className: 'chat-process-answer chat-unit-answer is-active',
      open: true,
      parent: item,
    });
    answerUnit.setState('●', 'is-running');
    answerNode = document.createElement('div');
    answerNode.className = 'chat-bubble chat-final-answer';
    answerUnit.body.appendChild(answerNode);
    return answerUnit;
  }

  function setAnswer(text) {
    if (text == null) return;
    answerBuffer = String(text);
    const unit = ensureAnswerUnit();

    if (window.ChatFormat) {
      answerNode.innerHTML =
        window.ChatFormat.renderMarkdown(answerBuffer);
      enhanceCoordinateTokens(answerNode);
    } else {
      answerNode.textContent = answerBuffer;
    }

    unit.root.classList.remove('is-active');
    unit.root.classList.add('is-complete');
    unit.setState('✓', 'is-success');
    unit.setSummary(`${answerBuffer.length.toLocaleString()} 字`);
    scroll();
  }

  function showError(message) {
    if (errorShown) return;
    errorShown = true;
    window.clearInterval(taskTimer);
    taskUnit.root.classList.remove('is-active');
    taskUnit.root.classList.add('is-error');
    taskUnit.setState('×', 'is-error');
    taskUnit.setSummary('失败');

    const unit = createCollapsibleBubble({
      title: '处理失败',
      className: 'chat-unit-error is-error',
      open: true,
      parent: item,
    });
    unit.setState('×', 'is-error');

    const node = document.createElement('div');
    node.className = 'chat-unit-note';
    node.textContent = message || 'AI 助手暂时不可用';
    unit.body.appendChild(node);
    scroll();
  }

  function ensureTrace(trace = []) {
    trace.forEach(call => {
      const key = toolKey(call);
      if (toolNodes.has(key)) return;
      toolStart({
        ...call,
        id: call.call_id,
        call_id: call.call_id,
        model_round: call.model_round,
        arguments: call.arguments || {},
      });
      toolEnd({
        ...call,
        id: call.call_id,
        call_id: call.call_id,
        model_round: call.model_round,
      });
    });
  }

  function appendFinalDetails(result, overlay) {
    if (result.context_usage?.context_window_tokens) {
      const unit = createCollapsibleBubble({
        title: '上下文与运行信息',
        className: 'chat-unit-context',
        open: true,
        parent: item,
      });
      const used = Number(
        result.context_usage.estimated_input_tokens || 0
      ).toLocaleString();
      const size = Number(
        result.context_usage.context_window_tokens || 0
      ).toLocaleString();
      const profile =
        result.context_usage.context_profile === '1m' ? '1M' : '标准';

      const node = document.createElement('div');
      node.className = 'chat-unit-note';
      node.textContent =
        `${profile} 上下文约 ${used} / ${size} tokens · 规则解释独立校验`;
      unit.body.appendChild(node);
    }

    if (result.coach_report) {
      const unit = createCollapsibleBubble({
        title: '可验证 Coach 报告',
        className: 'chat-unit-coach',
        open: true,
        parent: item,
      });
      renderCoachReport(unit.body, result.coach_report, overlay);
    }

    if (overlay?.moves?.length) {
      const unit = createCollapsibleBubble({
        title: `已验证候选 · ${overlay.moves.length} 条`,
        className: 'chat-unit-candidates',
        open: true,
        parent: item,
      });
      renderCandidateDeck(
        unit.body,
        overlay,
        result.coach_report || null
      );

      const actions = document.createElement('div');
      actions.className = 'chat-message-actions';

      const showButton = document.createElement('button');
      showButton.type = 'button';
      showButton.textContent = '显示候选目标';
      showButton.addEventListener(
        'click', () => showOverlay(overlay)
      );

      const firstButton = document.createElement('button');
      firstButton.type = 'button';
      firstButton.textContent = '查看首选路径';
      firstButton.addEventListener(
        'click', () => showOverlay(overlay, 0)
      );

      const coordinateButton = document.createElement('button');
      coordinateButton.type = 'button';
      coordinateButton.textContent = '显示清晰坐标';
      coordinateButton.addEventListener(
        'click', () => showOverlay(overlay, null, true)
      );

      actions.append(showButton, firstButton, coordinateButton);
      unit.body.appendChild(actions);
    }
  }

  function finish(result, overlay) {
    if (finishApplied) return;
    finishApplied = true;
    finalResult = result || {};

    if (!answerBuffer) {
      setAnswer(finalResult.answer || '没有返回内容');
    }
    ensureTrace(finalResult.tool_trace || []);

    window.clearInterval(taskTimer);
    taskUnit.root.classList.remove('is-active');
    taskUnit.root.classList.add('is-complete');
    taskUnit.setState('✓', 'is-success');

    const summary = [];
    const totalSeconds = Number(finalResult.elapsed_seconds || 0);
    if (totalSeconds > 0) {
      summary.push(`${totalSeconds.toFixed(2)} 秒`);
    }
    if (roundUnits.size) summary.push(`${roundUnits.size} 轮`);
    const toolCount = (finalResult.tool_trace || []).length;
    if (toolCount) summary.push(`${toolCount} 个工具`);
    taskUnit.setSummary(summary.join(' · '));

    roundUnits.forEach((state, round) => {
      if (state.completed) return;
      const metrics = (
        finalResult.context_usage?.upstream_rounds || []
      ).find(item => Number(item.round) === round) || {};
      completeRound(round, metrics);
    });

    appendFinalDetails(finalResult, overlay);
    scroll();
  }

  function handle(event) {
    if (!acceptEvent(event)) return;

    switch (event?.type) {
      case 'start':
        setPhase(
          event.thinking ? '启动思考模式' : '启动快速模式'
        );
        break;
      case 'phase':
        if (event.round) {
          updateRoundStatus(event.round, event.label);
        }
        setPhase(event.label);
        break;
      case 'heartbeat':
        if (activeRound) {
          updateRoundStatus(
            activeRound,
            event.label || '后台仍在处理，连接正常'
          );
        }
        break;
      case 'reasoning':
        addReasoning(event.text || '', event.round);
        break;
      case 'content_delta':
        addContentDelta(event.text || '', event.round);
        break;
      case 'tool_delta':
        toolDelta(event);
        break;
      case 'upstream_done':
        completeRound(event.round, event);
        setPhase(`第 ${event.round || '?'} 轮模型流完成`);
        break;
      case 'tool_start':
        toolStart(event);
        break;
      case 'tool_end':
        toolEnd(event);
        break;
      case 'text':
        setAnswer(event.text || '');
        break;
      case 'error':
        showError(event.message);
        break;
      default:
        break;
    }
  }

  function remove() {
    window.clearInterval(taskTimer);
    roundUnits.forEach(state => {
      window.clearInterval(state.timer);
    });
    item.remove();
  }

  // Compatibility marker for the earlier process-layout contract:
  // item.append(think, tools, bubble, footer)
  return {
    item,
    handle,
    finish,
    remove,
    showError,
    result: () => finalResult,
  };
}

  function overlayForText(text) {
    return null;
  }

  function currentOverlay(overlay) {
    if (!overlay || !window.BoardOverlay?.validateAnalysis) return null;
    const result = window.BoardOverlay.validateAnalysis(overlay);
    return result?.ok ? overlay : null;
  }

  async function loadHistory() {
    const { messages } = elements();
    if (!messages || !active) return;
    try {
      const response = await fetch('/api/chat/history');
      const data = await response.json();
      messages.innerHTML = '';
      const visible = (data.messages || []).filter(
        item => item.role === 'user' || item.role === 'assistant'
      );
      if (!visible.length) {
        messages.innerHTML =
          '<div class="chat-empty">对话已连接。AI 会读取真实棋局；候选目标与路径只是视觉覆盖，不会自动落子。</div>';
        return;
      }
      visible.forEach(item => {
        const metadata = item.metadata || {};
        const persistedOverlay = item.role === 'assistant'
          ? (metadata.board_overlay || null) : null;
        const overlay = currentOverlay(persistedOverlay);
        renderMessage(item.role, item.content, {
          historical: true,
          overlay,
          coachReport: item.role === 'assistant' ? (metadata.coach_report || null) : null,
          historicalOverlayExpired: Boolean(persistedOverlay && !overlay),
          contextUsage: metadata.context_usage || null,
          reasoning: metadata.reasoning_content || '',
          reasoningRounds: reasoningRoundsFromMetadata(metadata),
          reasoningSeconds: Number(metadata.reasoning_seconds || 0),
          elapsedSeconds: Number(metadata.elapsed_seconds || 0),
          thinkingEnabled: Boolean(metadata.thinking_enabled),
          toolTrace: metadata.tool_trace || [],
        });
      });
      chatAutoFollow = true;
      scrollChatMessages(messages, { force: true });
    } catch (_) {
      messages.innerHTML =
        '<div class="chat-empty">对话历史加载失败，棋局不受影响。</div>';
    }
  }


async function consumeChatStream(response, view) {
  if (!response.ok) {
    let message = `请求失败（HTTP ${response.status}）`;
    try {
      const payload = await response.json();
      message = payload.error || message;
    } catch (_) {}
    throw new Error(message);
  }
  if (!response.body) {
    throw new Error('浏览器未提供流式响应体');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let result = null;

  while (true) {
    const chunk = await reader.read();
    if (chunk.done) break;
    buffer += decoder.decode(chunk.value, { stream: true });

    const packets = buffer.split('\n\n');
    buffer = packets.pop() || '';

    packets.forEach(packet => {
      packet.split('\n').forEach(line => {
        if (!line.startsWith('data:')) return;
        const raw = line.slice(5).trim();
        if (!raw) return;
        try {
          const event = JSON.parse(raw);
          if (event.type === 'done') {
            result = event.result || null;
          } else {
            view.handle(event);
          }
        } catch (_) {
          // A malformed observational packet must not affect the game.
        }
      });
    });
  }

  if (!result) {
    throw new Error('AI 流结束，但未收到完整结果');
  }
  return result;
}
  async function send(textOverride = null) {
    const { input } = elements();
    const text = (textOverride == null ? input.value : textOverride).trim();
    if (!active || busy || !text) return;

    busy = true;
    setEnabled(true);
    renderMessage('user', text);
    if (textOverride == null) input.value = '';

    const processView = renderTyping();
    setStatus('正在建立 DeepSeek 事件流', 'busy');

    try {
      const response = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream',
        },
        body: JSON.stringify({
          message: text,
          thinking: preferences.thinking,
          show_reasoning: preferences.showReasoning,
          context_1m: preferences.context1m,
        }),
      });

      const data = await consumeChatStream(response, processView);
      const persistedOverlay = data.board_overlay || null;
      const overlay = currentOverlay(persistedOverlay);

      processView.finish(data, overlay);
      if (overlay?.moves?.length) showOverlay(overlay);

      if (data.configured === false) {
        setStatus(
          '本地可解释教练已启用 · 填 Key 可增强语言互动',
          'ready'
        );
      } else if (data.error) {
        setStatus('DeepSeek 已降级，本地解释仍有效', 'ready');
      } else {
        setStatus('推理、工具与棋局证据已同步', 'ready');
      }
    } catch (error) {
      processView?.showError(
        error.message || 'AI 助手暂时不可用'
      );
      setStatus('连接失败', 'error');
    } finally {
      busy = false;
      setEnabled(true);
      input?.focus();
    }
  }

  async function clear() {
    if (!active || busy) return;
    try {
      await fetch('/api/chat/clear', { method: 'POST' });
      window.BoardOverlay?.clearAnalysis();
      chatAutoFollow = true;
      const { messages } = elements();
      messages.innerHTML =
        '<div class="chat-empty">对话已清空。棋局和计算记录仍保留。</div>';
    } catch (_) {
      renderMessage('system', '清空失败，请稍后重试。');
    }
  }

  function ask(prompt) {
    if (!active || busy) return;
    send(prompt);
  }

  function onGameStarted(state) {
    applyGameSettings(state?.deepseek_settings || {});
    window.BoardOverlay?.onGameStateChanged();
    setEnabled(true);
    setStatus(
      state?.deepseek_configured
        ? `DeepSeek ${preferences.thinking ? '推理' : '快速'} + 本地可解释教练`
        : '本地可解释教练已启用',
      'ready'
    );
    loadHistory();
  }

  function onGameClosed() {
    busy = false;
    chatAutoFollow = true;
    window.BoardOverlay?.onGameStateChanged();
    setEnabled(false);
    setStatus('等待开始游戏');
    const { messages } = elements();
    if (messages) {
      messages.innerHTML =
        '<div class="chat-empty">开始游戏后，可让 DeepSeek 读取真实局面并调用计算工具。</div>';
    }
  }

  function onGameStateChanged() {
    window.BoardOverlay?.onGameStateChanged();
    if (active && !busy) setStatus('棋局已同步', 'ready');
  }

  function init() {
    const { messages, input, deepThink, context1m } = elements();
    ensureChatScrollTracking(messages);
    input?.addEventListener('keydown', event => {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        send();
      }
    });
    deepThink?.addEventListener('change', () => {
      preferences.thinking = Boolean(deepThink.checked);
      preferences.showReasoning = preferences.thinking;
      savePreferences();
      syncPreferenceControls();
      setStatus(
        preferences.thinking ? 'DeepSeek 推理与推理过程已开启' : 'DeepSeek 快速模式',
        'ready'
      );
    });
    context1m?.addEventListener('change', () => {
      preferences.context1m = Boolean(context1m.checked);
      savePreferences();
      setStatus(
        preferences.context1m ? '1M 上下文已开启' : '标准上下文已开启',
        'ready'
      );
    });
    loadPreferences();
    setEnabled(false);
  }

  window.addEventListener('DOMContentLoaded', init);
  return { send, ask, clear, applyGameSettings, onGameStarted, onGameClosed, onGameStateChanged };
})();

window.AIChat = AIChat;
