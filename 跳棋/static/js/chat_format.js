/**
 * Safe, dependency-free Markdown formatter for AI chat.
 * HTML from the model is always escaped before formatting.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.ChatFormat = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const COORD_SOURCE =
    '[\\(\\[（]\\s*(\\d{1,2})\\s*[,，]\\s*(\\d{1,2})\\s*[\\)\\]）]';
  const COORD_RE = new RegExp(COORD_SOURCE, 'g');
  const MOVE_RE = new RegExp(
    COORD_SOURCE + '\\s*(?:→|➡|➜|->|=>|到|至|移动到|跳到|走到)\\s*' + COORD_SOURCE,
    'g'
  );

  function normalizeText(value) {
    let text = value == null ? '' : String(value);
    text = text
      .replace(/\r\n?/g, '\n')
      .replace(/[\u200B-\u200D\uFEFF]/g, '')
      .trim();

    // DeepSeek occasionally emits headings without the required space.
    text = text
      .split('\n')
      .map(line => line.replace(/^(#{1,6})([^\s#])/, '$1 $2'))
      .join('\n');

    return text;
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function renderInline(raw) {
    const codeSlots = [];
    let value = String(raw).replace(/`([^`\n]+)`/g, function (_, code) {
      const index = codeSlots.length;
      codeSlots.push('<code>' + escapeHtml(code) + '</code>');
      return '\u0000CODE' + index + '\u0000';
    });

    value = escapeHtml(value)
      .replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
      .replace(/__([^_\n]+)__/g, '<strong>$1</strong>')
      .replace(/~~([^~\n]+)~~/g, '<del>$1</del>')
      .replace(/\*([^*\n]+)\*/g, '<em>$1</em>')
      .replace(/_([^_\n]+)_/g, '<em>$1</em>');

    value = value.replace(/\u0000CODE(\d+)\u0000/g, function (_, index) {
      return codeSlots[Number(index)] || '';
    });
    return value;
  }

  function splitTableRow(line) {
    let value = String(line).trim();
    if (value.startsWith('|')) value = value.slice(1);
    if (value.endsWith('|')) value = value.slice(0, -1);
    return value.split('|').map(cell => cell.trim());
  }

  function isTableSeparator(line) {
    const cells = splitTableRow(line);
    return cells.length > 1 && cells.every(cell => /^:?-{3,}:?$/.test(cell));
  }

  function renderMarkdown(input) {
    const text = normalizeText(input);
    if (!text) return '';

    const lines = text.split('\n');
    const out = [];
    let paragraph = [];
    let listType = '';
    let listItems = [];
    let codeMode = false;
    let codeLanguage = '';
    let codeLines = [];

    function flushParagraph() {
      if (!paragraph.length) return;
      out.push('<p>' + paragraph.map(renderInline).join('<br>') + '</p>');
      paragraph = [];
    }

    function flushList() {
      if (!listItems.length) return;
      const tag = listType === 'ol' ? 'ol' : 'ul';
      out.push('<' + tag + '>' + listItems.map(
        item => '<li>' + renderInline(item) + '</li>'
      ).join('') + '</' + tag + '>');
      listItems = [];
      listType = '';
    }

    function flushCode() {
      if (!codeLines.length && !codeMode) return;
      const lang = codeLanguage ? ' data-language="' + escapeHtml(codeLanguage) + '"' : '';
      out.push('<pre' + lang + '><code>' + escapeHtml(codeLines.join('\n')) + '</code></pre>');
      codeLines = [];
      codeLanguage = '';
    }

    for (let i = 0; i < lines.length; i += 1) {
      const line = lines[i];

      const fence = line.match(/^\s*```([\w+-]*)\s*$/);
      if (fence) {
        if (codeMode) {
          codeMode = false;
          flushCode();
        } else {
          flushParagraph();
          flushList();
          codeMode = true;
          codeLanguage = fence[1] || '';
          codeLines = [];
        }
        continue;
      }

      if (codeMode) {
        codeLines.push(line);
        continue;
      }

      if (
        line.includes('|') &&
        i + 1 < lines.length &&
        isTableSeparator(lines[i + 1])
      ) {
        flushParagraph();
        flushList();
        const headers = splitTableRow(line);
        const rows = [];
        i += 2;
        while (i < lines.length && lines[i].includes('|') && lines[i].trim()) {
          rows.push(splitTableRow(lines[i]));
          i += 1;
        }
        i -= 1;
        out.push(
          '<div class="chat-table-wrap"><table><thead><tr>' +
          headers.map(cell => '<th>' + renderInline(cell) + '</th>').join('') +
          '</tr></thead><tbody>' +
          rows.map(row => '<tr>' + headers.map(
            (_, index) => '<td>' + renderInline(row[index] || '') + '</td>'
          ).join('') + '</tr>').join('') +
          '</tbody></table></div>'
        );
        continue;
      }

      if (!line.trim()) {
        flushParagraph();
        flushList();
        continue;
      }

      const heading = line.match(/^\s*(#{1,4})\s+(.+)$/);
      if (heading) {
        flushParagraph();
        flushList();
        const level = Math.min(4, heading[1].length);
        out.push('<h' + level + '>' + renderInline(heading[2]) + '</h' + level + '>');
        continue;
      }

      const unordered = line.match(/^\s*[-*+]\s+(.+)$/);
      if (unordered) {
        flushParagraph();
        if (listType && listType !== 'ul') flushList();
        listType = 'ul';
        listItems.push(unordered[1]);
        continue;
      }

      const ordered = line.match(/^\s*\d+[.)]\s+(.+)$/);
      if (ordered) {
        flushParagraph();
        if (listType && listType !== 'ol') flushList();
        listType = 'ol';
        listItems.push(ordered[1]);
        continue;
      }

      const quote = line.match(/^\s*>\s?(.*)$/);
      if (quote) {
        flushParagraph();
        flushList();
        out.push('<blockquote>' + renderInline(quote[1]) + '</blockquote>');
        continue;
      }

      if (/^\s*(?:---+|\*\*\*+|___+)\s*$/.test(line)) {
        flushParagraph();
        flushList();
        out.push('<hr>');
        continue;
      }

      flushList();
      paragraph.push(line);
    }

    if (codeMode) {
      codeMode = false;
      flushCode();
    }
    flushParagraph();
    flushList();
    return out.join('');
  }

  function extractCoordinates(input) {
    const text = normalizeText(input);
    const result = [];
    const seen = new Set();
    COORD_RE.lastIndex = 0;
    let match;
    while ((match = COORD_RE.exec(text)) !== null) {
      const row = Number(match[1]);
      const col = Number(match[2]);
      const key = row + ',' + col;
      if (row >= 0 && row <= 16 && col >= 0 && col <= 16 && !seen.has(key)) {
        seen.add(key);
        result.push({ row, col, raw: match[0] });
      }
    }
    return result;
  }

  function extractMoves(input, limit) {
    const text = normalizeText(input);
    const result = [];
    const seen = new Set();
    const max = Math.max(1, Math.min(Number(limit) || 4, 8));
    MOVE_RE.lastIndex = 0;
    let match;
    while ((match = MOVE_RE.exec(text)) !== null && result.length < max) {
      const from = [Number(match[1]), Number(match[2])];
      const to = [Number(match[3]), Number(match[4])];
      const key = from.join(',') + '>' + to.join(',');
      if (
        from.every(value => value >= 0 && value <= 16) &&
        to.every(value => value >= 0 && value <= 16) &&
        !seen.has(key)
      ) {
        seen.add(key);
        result.push({
          from,
          to,
          label: result.length ? '分析 ' + (result.length + 1) : '文本建议',
          kind: 'text',
          verified: false,
        });
      }
    }
    return result;
  }

  function overlayFromText(input) {
    // Coordinates in prose remain clickable, but prose is never trusted as a
    // move command.  Only persisted rule-engine metadata may create overlays.
    return null;
  }

  return {
    normalizeText,
    escapeHtml,
    renderMarkdown,
    extractCoordinates,
    extractMoves,
    overlayFromText,
  };
});
