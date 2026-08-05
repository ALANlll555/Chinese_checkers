"""DeepSeek chat adapter with SQL history, tool grounding, and read-only board hints."""

from __future__ import annotations

import copy
import json
import re
import time
from typing import Any, Callable

import requests

import config as cfg
from board import VALID_HOLES
from database import GameDatabase, get_database
from game_tools import (
    CHAT_TOOL_DEFINITIONS,
    execute_chat_tool,
    explain_last_move,
    explain_position,
    get_game_metadata,
    state_token,
    validate_candidate_move,
)


SYSTEM_PROMPT = """你是跳棋游戏内的 AI Coach，并以可解释 AI 的标准帮助玩家理解局面、候选走法、连跳与梯子结构。

事实与工具：
- 系统会先提供一份由规则引擎生成的“可验证教练报告”；不得与该报告冲突。
- 需要补充真实数据时调用工具，不得编造棋子位置或合法走法。
- 推荐具体走法时必须调用 recommend_move、rank_candidate_moves 或 evaluate_move。
- 坐标统一写成（行,列），走法统一写成（起点行,起点列）→（终点行,终点列）。
- 前端显示方向为：行 0 在屏幕下方，行 16 在上方；列值从左向右增大。
- 评价只能基于五项特征：目标分配距离、最落后棋距离、有效向前连跳、梯子潜力、起始区滞留。
- 不得代替玩家执行走棋。棋盘标记只是只读建议层，不会自动落子。
- 给出多个候选时，要明确说明每个候选使用哪一颗棋、目标坐标、完整路径及单步/连跳段数。
- 解释必须区分：事实证据、结论、代价、反事实和置信度。
- 可解释证据来自五项特征变化；不要伪造或展示模型私有思维链。

输出：
- 使用简洁中文和标准 Markdown；不要输出装饰性的孤立 #、*、---。
- 默认使用“结论、证据、候选对比、风险/反事实、下一步”结构。
- 标题最多使用三级，列表使用标准短横线。
- 当用户启用推理显示时，系统可单独展示 API 返回的 reasoning_content；它只是模型过程记录，不得代替规则证据，也不得伪造或补全。
"""


_COORD = r"[\(\[（]\s*(\d{1,2})\s*[,，]\s*(\d{1,2})\s*[\)\]）]"
_MOVE_RE = re.compile(
    _COORD + r"\s*(?:→|➡|➜|->|=>|到|至|移动到|跳到|走到)\s*" + _COORD
)


def _normalize_text(value: Any) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\u200B-\u200D\uFEFF]", "", text).strip()
    text = re.sub(r"(?m)^(#{1,6})([^\s#])", r"\1 \2", text)
    return text


def _openai_base(base_url: str) -> str:
    url = (base_url or "https://api.deepseek.com").strip().rstrip("/")
    for suffix in ("/chat/completions", "/beta", "/v1"):
        if url.endswith(suffix):
            url = url[: -len(suffix)]
    return url or "https://api.deepseek.com"


def _option_bool(value: Any, default: bool) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enabled"}


def resolve_runtime_options(
    options: dict | None = None,
    game_settings: dict | None = None,
) -> dict:
    raw = dict(game_settings or {})
    raw.update({
        key: value
        for key, value in (options or {}).items()
        if value is not None
    })
    thinking = _option_bool(raw.get("thinking"), cfg.LLM_THINKING)
    show_reasoning = _option_bool(
        raw.get("show_reasoning"), cfg.LLM_SHOW_REASONING_DEFAULT
    )
    context_1m = _option_bool(
        raw.get("context_1m"), cfg.LLM_CONTEXT_1M_DEFAULT
    )
    strict_tools = _option_bool(
        raw.get("strict_tools"), cfg.LLM_STRICT_TOOLS
    )
    if show_reasoning:
        thinking = True
    effort = str(
        raw.get("reasoning_effort") or cfg.LLM_REASONING_EFFORT
    ).strip().lower()
    if effort not in {"low", "high", "xhigh", "max"}:
        effort = cfg.LLM_REASONING_EFFORT
    try:
        max_tokens = int(raw.get("max_tokens") or cfg.LLM_CHAT_MAX_TOKENS)
    except (TypeError, ValueError):
        max_tokens = cfg.LLM_CHAT_MAX_TOKENS
    return {
        "thinking": thinking,
        "show_reasoning": show_reasoning,
        "context_1m": context_1m,
        "strict_tools": strict_tools,
        "base_url": str(raw.get("base_url") or cfg.LLM_API_BASE).strip(),
        "model": str(raw.get("model") or cfg.LLM_MODEL).strip(),
        "reasoning_effort": effort,
        "max_tokens": max(256, min(32768, max_tokens)),
    }


def _bounded_reasoning(parts: list[str]) -> str:
    value = "\n\n---\n\n".join(part for part in parts if part).strip()
    if len(value) <= cfg.LLM_REASONING_MAX_CHARS:
        return value
    suffix = "\n\n（推理内容过长，已按本地显示上限截断。）"
    return value[: max(0, cfg.LLM_REASONING_MAX_CHARS - len(suffix))] + suffix


def _emit_event(
    callback: Callable[[dict], None] | None,
    event_type: str,
    **fields: Any,
) -> None:
    """Best-effort UI event delivery; display failures never affect the game."""
    if callback is None:
        return
    event = {"type": event_type, **fields}
    try:
        callback(event)
    except Exception:
        # The event stream is observational only. It must never change the
        # recommendation, persistence, legality checks, or fallback behavior.
        return


def _strict_schema(schema: dict) -> dict:
    result = copy.deepcopy(schema)
    if result.get("type") == "object":
        properties = result.get("properties") or {}
        result["additionalProperties"] = False
        result["required"] = list(properties.keys())
        for key, value in list(properties.items()):
            if isinstance(value, dict) and value.get("type") == "object":
                properties[key] = _strict_schema(value)
    return result


def _tool_definitions(strict: bool | None = None) -> list[dict]:
    use_strict = cfg.LLM_STRICT_TOOLS if strict is None else bool(strict)
    if not use_strict:
        return CHAT_TOOL_DEFINITIONS
    result = copy.deepcopy(CHAT_TOOL_DEFINITIONS)
    for item in result:
        function = item.get("function") or {}
        function["parameters"] = _strict_schema(function.get("parameters") or {})
        function["strict"] = True
    return result


def _valid_position(value: Any) -> list[int] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        position = [int(value[0]), int(value[1])]
    except (TypeError, ValueError):
        return None
    return position if tuple(position) in VALID_HOLES else None


def _raw_move(value: Any) -> tuple[list[int], list[int]] | None:
    if isinstance(value, dict):
        start = _valid_position(value.get("from"))
        end = _valid_position(value.get("to"))
    elif isinstance(value, (list, tuple)) and len(value) >= 2:
        start = _valid_position(value[0])
        end = _valid_position(value[1])
    else:
        return None
    if start is None or end is None:
        return None
    return start, end


def _new_overlay(game: dict, player_id: int, purpose: str = "recommendation") -> dict:
    state = game["state"]
    return {
        "title": "AI 建议",
        "purpose": purpose,
        "player_id": int(player_id),
        "game_id": game.get("game_id"),
        "move_count": len(state.move_history),
        "state_token": state_token(state),
        "moves": [],
        "rejected": [],
        "source_tools": [],
        "coordinate_format": "（行,列）",
        "read_only": True,
        "verification_policy": "rule-engine-only",
    }


def _append_overlay_move(
    overlay: dict,
    raw: Any,
    *,
    label: str,
    kind: str,
    game: dict,
    expected_player_id: int,
    rank: int | None = None,
    score: float | None = None,
    score_delta: float | None = None,
) -> bool:
    detail = raw.get("move_detail") if isinstance(raw, dict) and raw.get("move_detail") else raw
    move_value = detail.get("move") if isinstance(detail, dict) and detail.get("move") else detail
    parsed = _raw_move(move_value)
    if parsed is None:
        overlay["rejected"].append({"reason": "unparseable-move", "label": label})
        return False
    start, end = parsed
    validation = validate_candidate_move(
        game, start, end, player_id=expected_player_id
    )
    if not validation.get("valid"):
        overlay["rejected"].append({
            "reason": "candidate-invariant-failed",
            "label": label,
            "move": {"from": start, "to": end},
            "checks": validation.get("checks"),
        })
        return False

    canonical = validation["move_detail"]
    key = tuple(start + end)
    existing = {tuple(item["from"] + item["to"]) for item in overlay["moves"]}
    if key in existing or len(overlay["moves"]) >= cfg.LLM_BOARD_OVERLAY_LIMIT:
        return False

    if isinstance(detail, dict):
        if rank is None and detail.get("rank") is not None:
            rank = int(detail["rank"])
        if score is None and detail.get("score") is not None:
            score = float(detail["score"])
        if score_delta is None and detail.get("score_delta") is not None:
            score_delta = float(detail["score_delta"])

    overlay["moves"].append({
        "id": f"candidate-{len(overlay['moves']) + 1}",
        "from": canonical["move"]["from"],
        "to": canonical["move"]["to"],
        "path": canonical["path"],
        "jumped_over": canonical["jumped_over"],
        "path_text": canonical["path_text"],
        "move_type": canonical["move_type"],
        "jump_count": canonical["jump_count"],
        "player_id": int(expected_player_id),
        "rank": rank or len(overlay["moves"]) + 1,
        "label": label,
        "kind": kind,
        "verified": True,
        "validation": validation["checks"],
        "score": score,
        "score_delta": score_delta,
        "components": detail.get("components") if isinstance(detail, dict) else None,
    })
    return True


def _merge_tool_overlay(
    overlay: dict,
    tool_name: str,
    result: Any,
    game: dict,
    expected_player_id: int,
) -> None:
    if not isinstance(result, dict):
        return
    result_player = result.get("player_id")
    if result_player is not None and int(result_player) != int(expected_player_id):
        overlay["rejected"].append({
            "reason": "wrong-player-tool-result",
            "tool": tool_name,
            "reported_player": result_player,
            "expected_player": expected_player_id,
        })
        return
    if tool_name not in overlay["source_tools"]:
        overlay["source_tools"].append(tool_name)

    if tool_name == "recommend_move":
        details = result.get("candidate_details") or []
        for index, detail in enumerate(details[: cfg.LLM_BOARD_OVERLAY_LIMIT]):
            _append_overlay_move(
                overlay, detail,
                label="推荐" if index == 0 else f"候选 {index + 1}",
                kind="recommendation" if index == 0 else "candidate",
                game=game, expected_player_id=expected_player_id, rank=index + 1,
            )
        return

    if tool_name == "rank_candidate_moves":
        for item in (result.get("candidates") or [])[: cfg.LLM_BOARD_OVERLAY_LIMIT]:
            _append_overlay_move(
                overlay, item.get("move_detail") or item.get("move"),
                label=f"候选 {item.get('rank', '')}".strip(), kind="candidate",
                game=game, expected_player_id=expected_player_id,
                rank=item.get("rank"), score=item.get("score"),
                score_delta=item.get("score_delta"),
            )
        return

    if tool_name == "evaluate_move":
        _append_overlay_move(
            overlay, result.get("move_detail") or result.get("move"),
            label="分析走法", kind="analysis", game=game,
            expected_player_id=expected_player_id, score_delta=result.get("score_delta"),
        )
        return

    if tool_name == "get_legal_moves" and result.get("from_position"):
        for index, move in enumerate((result.get("moves") or [])[:3]):
            _append_overlay_move(
                overlay, move, label=f"合法 {index + 1}", kind="candidate",
                game=game, expected_player_id=expected_player_id, rank=index + 1,
            )


def _merge_text_overlay(overlay: dict, answer: str, game: dict) -> None:
    # Model prose is never trusted as a board command.  Coordinates remain
    # clickable in chat, but visual move overlays require rule-engine evidence.
    if _MOVE_RE.search(answer):
        overlay["rejected"].append({"reason": "untrusted-text-overlay-disabled"})


def _final_overlay(overlay: dict) -> dict | None:
    if not overlay["moves"]:
        return None
    if any(item["kind"] == "recommendation" for item in overlay["moves"]):
        overlay["title"] = "AI 推荐"
    overlay["rejected_count"] = len(overlay.get("rejected") or [])
    return overlay


def _intent_kind(text: str) -> str:
    lowered = text.lower()
    if any(word in text for word in ("复盘", "最近一步", "上一步", "刚才")):
        return "review"
    if any(word in text for word in (
        "推荐", "下一步", "怎么走", "候选", "走哪", "方案", "路线", "推进",
        "布局", "建议", "选择", "该走", "如何走", "帮我走",
    )):
        return "recommend"
    if any(word in text for word in ("分析", "局面", "形势", "诊断", "为什么")):
        return "analysis"
    return "general"


def _build_coach_report(game: dict, text: str) -> dict:
    report = explain_position(game, limit=cfg.LLM_BOARD_OVERLAY_LIMIT)
    report["intent"] = _intent_kind(text)
    if report["intent"] == "review":
        report["last_move_analysis"] = explain_last_move(game)
    return report


def _overlay_from_coach_report(report: dict, game: dict) -> dict | None:
    pid = int(report["player_id"])
    overlay = _new_overlay(game, pid)
    for index, candidate in enumerate(report.get("candidates") or []):
        _append_overlay_move(
            overlay, candidate,
            label="推荐" if index == 0 else f"候选 {index + 1}",
            kind="recommendation" if index == 0 else "candidate",
            game=game, expected_player_id=pid, rank=index + 1,
            score=candidate.get("score"), score_delta=candidate.get("score_delta"),
        )
    return _final_overlay(overlay)


def _format_feature_change(change: dict) -> str:
    arrow = "↑" if change.get("delta", 0) > 0 else "↓" if change.get("delta", 0) < 0 else "→"
    effect = float(change.get("score_effect", 0.0))
    sign = "+" if effect > 0 else ""
    return (
        f"{change.get('label')} {change.get('before')} {arrow} {change.get('after')} "
        f"（评分影响 {sign}{effect:.1f}）"
    )


def _local_coach_answer(report: dict, *, note: str = "") -> str:
    lines = ["### 结论", report.get("headline", "当前局面分析完成。")]
    if report.get("summary"):
        lines.append(report["summary"])
    phase = report.get("phase") or {}
    race = report.get("race") or {}
    lines.extend([
        "",
        "### 可验证证据",
        f"- 阶段：{phase.get('label', '未知')}；{phase.get('reason', '')}",
        f"- 竞速位置：第 {race.get('rank', '?')}/{race.get('total_players', '?')}；{race.get('label', '')}",
    ])
    for diagnostic in (report.get("diagnostics") or [])[:3]:
        lines.append(
            f"- {diagnostic.get('title')}：{diagnostic.get('evidence')}；"
            f"建议：{diagnostic.get('action')}"
        )
    candidates = report.get("candidates") or []
    if candidates:
        lines.extend(["", "### 候选对比"])
        for candidate in candidates[:5]:
            detail = candidate.get("move_detail") or {}
            path = detail.get("path_text") or ""
            lines.append(
                f"- 候选 {candidate.get('rank')}：{path}。"
                f"理由：{candidate.get('reason')}；代价：{candidate.get('tradeoff')}。"
            )
    last = report.get("last_move_analysis") or {}
    if last.get("available"):
        lines.extend([
            "",
            "### 最近一步复盘",
            f"- {last.get('headline')}；总评分变化 {last.get('score_delta', 0):+.2f}",
            f"- {last.get('summary')}；风险：{last.get('risk')}",
        ])
    confidence = report.get("confidence") or {}
    lines.extend([
        "",
        "### 置信度与反事实",
        f"- 置信度：{confidence.get('label', '中')}（{float(confidence.get('value', 0)) * 100:.0f}%）；{confidence.get('basis', '')}",
    ])
    counter = report.get("counterfactual")
    if counter:
        lines.append(f"- 反事实：{counter.get('text')}")
    lines.extend([
        "",
        "以上是规则引擎可复核的证据摘要，不是模型私有思维链。",
    ])
    if note:
        lines.append(note)
    return "\n".join(lines)


def _answer_move_pairs(answer: str) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    pairs = []
    for match in _MOVE_RE.finditer(answer or ""):
        pairs.append(((int(match.group(1)), int(match.group(2))),
                      (int(match.group(3)), int(match.group(4)))))
    return pairs


def _finalize_coach_output(
    game: dict,
    text: str,
    report: dict,
    answer: str,
    overlay: dict | None,
    mode: str,
) -> tuple[dict, str, dict | None, str, dict]:
    guard = {"state_refreshed": False, "model_move_rejected": False}
    if report.get("state_token") != state_token(game["state"]):
        report = _build_coach_report(game, text)
        overlay = (
            _overlay_from_coach_report(report, game)
            if report.get("intent") in {"analysis", "recommend", "review"}
            else None
        )
        answer = _local_coach_answer(
            report, note="分析期间棋局发生了变化，已自动刷新为当前局面。"
        )
        mode = "local-refreshed"
        guard["state_refreshed"] = True
        return report, answer, overlay, mode, guard

    if report.get("intent") in {"analysis", "recommend", "review"}:
        allowed = {
            (tuple(item["move"]["from"]), tuple(item["move"]["to"]))
            for item in (report.get("candidates") or [])
        }
        mentioned = _answer_move_pairs(answer)
        if mentioned and any(pair not in allowed for pair in mentioned):
            answer = _local_coach_answer(
                report,
                note="模型文字中的坐标与规则引擎候选不一致，已改用可验证教练报告。",
            )
            mode = "local-consistency-fallback"
            guard["model_move_rejected"] = True
    return report, answer, overlay, mode, guard


def _compact_report_for_model(report: dict) -> dict:
    return {
        "player_id": report.get("player_id"),
        "phase": report.get("phase"),
        "headline": report.get("headline"),
        "summary": report.get("summary"),
        "confidence": report.get("confidence"),
        "race": report.get("race"),
        "diagnostics": report.get("diagnostics"),
        "current_features": (report.get("current") or {}).get("features"),
        "candidates": [
            {
                "rank": item.get("rank"),
                "move_detail": item.get("move_detail"),
                "score_delta": item.get("score_delta"),
                "feature_changes": item.get("feature_changes"),
                "reason": item.get("reason"),
                "tradeoff": item.get("tradeoff"),
            }
            for item in (report.get("candidates") or [])
        ],
        "counterfactual": report.get("counterfactual"),
        "last_move_analysis": report.get("last_move_analysis"),
        "evidence": report.get("evidence"),
    }


_TOOL_LABELS = {
    item["function"]["name"]: item["function"]["description"].split("。", 1)[0]
    for item in CHAT_TOOL_DEFINITIONS
}


def _tool_preview(value: Any, limit: int = 2400) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, default=str, indent=2)
    except Exception:
        text = str(value)
    if len(text) <= limit:
        return text
    return text[:limit] + "\n…（结果已截断）"

class DeepSeekChatService:
    def __init__(self, database: GameDatabase | None = None, http_post=None):
        self.database = database or get_database()
        self.http_post = http_post or requests.post

    def _endpoint(self, runtime: dict | None = None) -> str:
        settings = runtime or {}
        base = _openai_base(settings.get("base_url") or cfg.LLM_API_BASE)
        if settings.get("strict_tools", cfg.LLM_STRICT_TOOLS):
            return f"{base}/beta/chat/completions"
        return f"{base}/chat/completions"

    @staticmethod
    def _estimate_tokens(value: Any) -> int:
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        cjk = sum(1 for char in text if "\u3400" <= char <= "\u9fff")
        other = max(0, len(text) - cjk)
        return max(1, int(cjk * 0.65 + other * 0.34) + 8)

    def _history_messages(
        self,
        game_id: str,
        available_tokens: int,
    ) -> tuple[list[dict], dict]:
        """Build protocol-valid history, including prior tool-call reasoning."""
        rows = self.database.get_chat_history(
            game_id, cfg.LLM_HISTORY_LIMIT
        )

        def clean_agent_message(value: Any) -> dict | None:
            if not isinstance(value, dict):
                return None
            role = value.get("role")
            if role == "assistant":
                message: dict[str, Any] = {
                    "role": "assistant",
                    "content": str(value.get("content") or ""),
                }
                reasoning = value.get("reasoning_content")
                if reasoning is not None:
                    message["reasoning_content"] = str(reasoning)
                tool_calls = value.get("tool_calls")
                if isinstance(tool_calls, list) and tool_calls:
                    message["tool_calls"] = tool_calls
                return message
            if role == "tool" and value.get("tool_call_id"):
                return {
                    "role": "tool",
                    "tool_call_id": str(value["tool_call_id"]),
                    "content": str(value.get("content") or ""),
                }
            return None

        turns: list[list[dict]] = []
        current_turn: list[dict] = []
        expanded_messages = 0

        for row in rows:
            role = row.get("role")
            content = str(row.get("content") or "").strip()

            if role == "user":
                if current_turn:
                    turns.append(current_turn)
                current_turn = []
                if content:
                    current_turn.append({
                        "role": "user",
                        "content": content,
                    })
                    expanded_messages += 1
                continue

            if role != "assistant":
                continue

            metadata = row.get("metadata") or {}
            transcript = metadata.get("agent_messages")
            expanded: list[dict] = []
            if isinstance(transcript, list):
                for raw_message in transcript:
                    message = clean_agent_message(raw_message)
                    if message is not None:
                        expanded.append(message)

            if not expanded and content:
                expanded = [{
                    "role": "assistant",
                    "content": content,
                }]

            current_turn.extend(expanded)
            expanded_messages += len(expanded)
            if current_turn:
                turns.append(current_turn)
                current_turn = []

        if current_turn:
            turns.append(current_turn)

        selected_reversed: list[list[dict]] = []
        used = 0
        for turn in reversed(turns):
            cost = sum(self._estimate_tokens(item) for item in turn)
            if selected_reversed and used + cost > available_tokens:
                break
            selected_reversed.append(turn)
            used += cost
            if used >= available_tokens:
                break

        selected_turns = list(reversed(selected_reversed))
        selected = [
            message
            for turn in selected_turns
            for message in turn
        ]

        while selected and selected[0].get("role") in {"assistant", "tool"}:
            selected.pop(0)

        return selected, {
            "history_messages_included": len(selected),
            "history_messages_available": expanded_messages,
            "history_turns_included": len(selected_turns),
            "estimated_history_tokens": used,
            "tool_reasoning_history_enabled": True,
        }

    def _build_messages(
        self,
        game_id: str,
        context: str,
        *,
        context_1m: bool | None = None,
    ) -> tuple[list[dict], dict]:
        use_1m = cfg.LLM_CONTEXT_1M_DEFAULT if context_1m is None else bool(context_1m)
        fixed = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "system", "content": context},
        ]
        fixed_tokens = sum(self._estimate_tokens(item) for item in fixed)
        if use_1m:
            window = max(32768, int(cfg.LLM_CONTEXT_WINDOW_TOKENS))
            configured_budget = int(cfg.LLM_INPUT_BUDGET_TOKENS)
            profile = "1m"
        else:
            window = max(32768, int(cfg.LLM_STANDARD_CONTEXT_WINDOW_TOKENS))
            configured_budget = int(cfg.LLM_STANDARD_INPUT_BUDGET_TOKENS)
            profile = "standard"
        input_budget = min(
            window - int(cfg.LLM_CONTEXT_RESERVE_TOKENS),
            configured_budget,
        )
        available = max(0, input_budget - fixed_tokens)
        history, history_usage = self._history_messages(game_id, available)
        messages = [*fixed, *history]
        estimated = fixed_tokens + history_usage["estimated_history_tokens"]
        usage = {
            "context_profile": profile,
            "context_1m_enabled": use_1m,
            "context_window_tokens": window,
            "input_budget_tokens": input_budget,
            "estimated_input_tokens": estimated,
            "fixed_prefix_tokens": fixed_tokens,
            "cache_prefix_stable": True,
            **history_usage,
        }
        return messages, usage

    def _request(
        self,
        api_key: str,
        messages: list[dict],
        *,
        thinking: bool,
        runtime: dict | None = None,
        event_callback: Callable[[dict], None] | None = None,
        round_index: int = 0,
    ) -> dict:
        """Call DeepSeek; use true upstream SSE when an event sink exists."""
        settings = runtime or {}
        upstream_stream = event_callback is not None

        payload: dict[str, Any] = {
            "model": settings.get("model") or cfg.LLM_MODEL,
            "messages": messages,
            "tools": _tool_definitions(settings.get("strict_tools")),
            "max_tokens": (
                settings.get("max_tokens")
                or cfg.LLM_CHAT_MAX_TOKENS
            ),
            "thinking": {
                "type": "enabled" if thinking else "disabled"
            },
        }
        if thinking:
            payload["reasoning_effort"] = (
                settings.get("reasoning_effort")
                or cfg.LLM_REASONING_EFFORT
            )
        else:
            payload["tool_choice"] = "auto"
            payload["temperature"] = cfg.LLM_CHAT_TEMPERATURE

        if upstream_stream:
            payload["stream"] = True
            payload["stream_options"] = {"include_usage": True}

        request_kwargs: dict[str, Any] = {
            "headers": {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            "json": payload,
            "timeout": cfg.LLM_TIMEOUT_SECONDS,
        }
        if upstream_stream:
            request_kwargs["stream"] = True

        response = self.http_post(
            self._endpoint(settings),
            **request_kwargs,
        )
        response.raise_for_status()

        if not upstream_stream or not hasattr(response, "iter_lines"):
            data = response.json()
            choices = data.get("choices") or []
            if not choices:
                raise RuntimeError("DeepSeek response has no choices")
            assistant = choices[0].get("message") or {}
            assistant["_stream_metrics"] = {
                "upstream_stream": False,
                "elapsed_seconds": 0.0,
                "reasoning_seconds": 0.0,
                "chunk_count": 0,
                "finish_reason": choices[0].get("finish_reason"),
                "usage": data.get("usage"),
            }
            return assistant

        started = time.perf_counter()
        first_delta_at: float | None = None
        last_reasoning_at: float | None = None
        reasoning_parts: list[str] = []
        content_parts: list[str] = []
        tool_accumulator: dict[int, dict] = {}
        finish_reason = None
        usage = None
        chunk_count = 0
        malformed_chunks = 0

        try:
            for raw_line in response.iter_lines(
                chunk_size=1,
                decode_unicode=True,
            ):
                if raw_line is None:
                    continue
                if isinstance(raw_line, bytes):
                    line = raw_line.decode(
                        "utf-8", errors="replace"
                    )
                else:
                    line = str(raw_line)
                line = line.strip()
                if not line or line.startswith(":"):
                    continue
                if not line.startswith("data:"):
                    continue

                data_text = line[5:].strip()
                if data_text == "[DONE]":
                    break
                if not data_text:
                    continue

                try:
                    chunk = json.loads(data_text)
                except json.JSONDecodeError:
                    malformed_chunks += 1
                    continue

                if chunk.get("usage") is not None:
                    usage = chunk.get("usage")

                choices = chunk.get("choices") or []
                if not choices:
                    continue

                chunk_count += 1
                now = time.perf_counter()
                if first_delta_at is None:
                    first_delta_at = now

                choice = choices[0]
                if choice.get("finish_reason") is not None:
                    finish_reason = choice.get("finish_reason")
                delta = choice.get("delta") or {}

                reasoning_delta = delta.get("reasoning_content")
                if reasoning_delta:
                    text = str(reasoning_delta)
                    reasoning_parts.append(text)
                    last_reasoning_at = now
                    _emit_event(
                        event_callback,
                        "reasoning",
                        text=text,
                        delta=True,
                        round=round_index + 1,
                        elapsed_seconds=round(
                            now - started, 3
                        ),
                    )

                content_delta = delta.get("content")
                if content_delta:
                    text = str(content_delta)
                    content_parts.append(text)
                    _emit_event(
                        event_callback,
                        "content_delta",
                        text=text,
                        round=round_index + 1,
                        elapsed_seconds=round(
                            now - started, 3
                        ),
                    )

                for raw_tool_delta in (
                    delta.get("tool_calls") or []
                ):
                    try:
                        index = int(
                            raw_tool_delta.get("index", 0)
                        )
                    except (TypeError, ValueError):
                        index = 0

                    entry = tool_accumulator.setdefault(
                        index,
                        {
                            "id": "",
                            "type": "function",
                            "function": {
                                "name": "",
                                "arguments": "",
                            },
                        },
                    )
                    call_id = raw_tool_delta.get("id")
                    if call_id:
                        if not entry["id"]:
                            entry["id"] = str(call_id)
                        elif str(call_id) != entry["id"]:
                            entry["id"] += str(call_id)

                    if raw_tool_delta.get("type"):
                        entry["type"] = raw_tool_delta["type"]

                    function_delta = (
                        raw_tool_delta.get("function") or {}
                    )
                    name_delta = function_delta.get("name")
                    arguments_delta = function_delta.get(
                        "arguments"
                    )
                    if name_delta:
                        entry["function"]["name"] += str(
                            name_delta
                        )
                    if arguments_delta:
                        entry["function"]["arguments"] += str(
                            arguments_delta
                        )

                    _emit_event(
                        event_callback,
                        "tool_delta",
                        index=index,
                        id=entry["id"],
                        name=entry["function"]["name"],
                        arguments=entry["function"][
                            "arguments"
                        ],
                        name_delta=str(name_delta or ""),
                        arguments_delta=str(
                            arguments_delta or ""
                        ),
                        round=round_index + 1,
                    )
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()

        elapsed = time.perf_counter() - started
        reasoning_seconds = (
            last_reasoning_at - started
            if last_reasoning_at is not None
            else 0.0
        )
        tool_calls = [
            tool_accumulator[index]
            for index in sorted(tool_accumulator)
        ]

        assistant = {
            "role": "assistant",
            "content": "".join(content_parts),
            "reasoning_content": "".join(reasoning_parts),
            "tool_calls": tool_calls,
            "_streamed_reasoning": bool(reasoning_parts),
            "_streamed_content": bool(content_parts),
            "_stream_metrics": {
                "upstream_stream": True,
                "elapsed_seconds": round(elapsed, 3),
                "reasoning_seconds": round(
                    reasoning_seconds, 3
                ),
                "first_delta_seconds": round(
                    (
                        first_delta_at - started
                        if first_delta_at is not None
                        else elapsed
                    ),
                    3,
                ),
                "chunk_count": chunk_count,
                "malformed_chunks": malformed_chunks,
                "finish_reason": finish_reason,
                "usage": usage,
            },
        }
        _emit_event(
            event_callback,
            "upstream_done",
            round=round_index + 1,
            finish_reason=finish_reason,
            chunk_count=chunk_count,
            elapsed_seconds=round(elapsed, 3),
            reasoning_seconds=round(
                reasoning_seconds, 3
            ),
            usage=usage,
        )
        return assistant

    def _finish(
        self,
        *,
        game_id: str,
        answer: str,
        model: str,
        tool_trace: list[dict],
        board_overlay: dict | None,
        coach_report: dict,
        coach_mode: str,
        configured: bool,
        coach_guard: dict | None = None,
        context_usage: dict | None = None,
        reasoning_content: str = "",
        thinking_enabled: bool = False,
        context_1m: bool = False,
        elapsed_seconds: float = 0.0,
        reasoning_seconds: float = 0.0,
        runtime_settings: dict | None = None,
        agent_messages: list[dict] | None = None,
        event_callback: Callable[[dict], None] | None = None,
        error: str | None = None,
    ) -> dict:
        result = {
            "answer": answer,
            "model": model,
            "tool_trace": tool_trace,
            "board_overlay": board_overlay,
            "coach_report": coach_report,
            "coach_mode": coach_mode,
            "coach_guard": coach_guard or {},
            "context_usage": context_usage or {},
            "reasoning_content": reasoning_content,
            "thinking_enabled": bool(thinking_enabled),
            "context_1m": bool(context_1m),
            "elapsed_seconds": round(float(elapsed_seconds), 3),
            "reasoning_seconds": round(float(reasoning_seconds), 3),
            "deepseek_settings": {
                key: value
                for key, value in (runtime_settings or {}).items()
                if key not in {"api_key"}
            },
            "configured": configured,
        }
        if error:
            result["error"] = error
        self.database.append_chat_message(
            game_id,
            "assistant",
            answer,
            model=model,
            metadata={
                "board_overlay": board_overlay,
                "coach_report": coach_report,
                "coach_mode": coach_mode,
                "coach_guard": coach_guard or {},
                "context_usage": context_usage or {},
                "reasoning_content": reasoning_content,
                "thinking_enabled": bool(thinking_enabled),
                "context_1m": bool(context_1m),
                "elapsed_seconds": round(float(elapsed_seconds), 3),
                "reasoning_seconds": round(float(reasoning_seconds), 3),
                "tool_trace": tool_trace,
                "agent_messages": agent_messages or [],
                "deepseek_settings": {
                    key: value
                    for key, value in (runtime_settings or {}).items()
                    if key not in {"api_key"}
                },
            },
        )
        _emit_event(event_callback, "text", text=answer)
        _emit_event(
            event_callback,
            "done",
            result=result,
            elapsed_seconds=result["elapsed_seconds"],
            reasoning_seconds=result["reasoning_seconds"],
        )
        return result

    def reply(
        self,
        game: dict,
        user_message: str,
        options: dict | None = None,
        event_callback: Callable[[dict], None] | None = None,
    ) -> dict:
        game_id = game["game_id"]
        request_started = time.perf_counter()
        runtime = resolve_runtime_options(
            options, game.get("deepseek_settings")
        )
        thinking_enabled = bool(runtime["thinking"])
        show_reasoning = bool(runtime["show_reasoning"])
        context_1m = bool(runtime["context_1m"])
        reasoning_parts: list[str] = []
        agent_messages: list[dict] = []
        upstream_rounds: list[dict] = []
        model_elapsed_seconds = 0.0
        reasoning_elapsed_seconds = 0.0
        text = _normalize_text(user_message)
        if not text:
            raise ValueError("message is empty")
        if len(text) > cfg.LLM_MAX_USER_CHARS:
            raise ValueError(f"message exceeds {cfg.LLM_MAX_USER_CHARS} characters")

        _emit_event(
            event_callback,
            "start",
            model=runtime["model"],
            thinking=thinking_enabled,
            show_reasoning=show_reasoning,
            context_1m=context_1m,
        )
        _emit_event(
            event_callback,
            "phase",
            label="正在生成本地规则证据",
            phase="local-evidence",
        )

        self.database.append_chat_message(game_id, "user", text)
        coach_report = _build_coach_report(game, text)
        _emit_event(
            event_callback,
            "phase",
            label="本地规则证据已就绪",
            phase="local-evidence-ready",
        )
        base_overlay = (
            _overlay_from_coach_report(coach_report, game)
            if coach_report.get("intent") in {"analysis", "recommend", "review"}
            else None
        )
        api_key = game.get("api_key") or cfg.LLM_API_KEY
        if not api_key:
            answer = _local_coach_answer(
                coach_report,
                note="当前使用本地可解释教练；填写 DeepSeek Key 后可获得更自然的语言互动。",
            )
            return self._finish(
                game_id=game_id, answer=answer, model="local-xai-coach",
                tool_trace=[], board_overlay=base_overlay, coach_report=coach_report,
                coach_mode="local", configured=False,
                context_usage={
                    "context_profile": "1m" if context_1m else "standard",
                    "context_1m_enabled": context_1m,
                    "context_window_tokens": (
                        cfg.LLM_CONTEXT_WINDOW_TOKENS
                        if context_1m
                        else cfg.LLM_STANDARD_CONTEXT_WINDOW_TOKENS
                    ),
                    "estimated_input_tokens": 0,
                    "history_messages_included": 0,
                    "thinking_enabled": thinking_enabled,
                },
                reasoning_content="",
                thinking_enabled=thinking_enabled,
                context_1m=context_1m,
                elapsed_seconds=time.perf_counter() - request_started,
                reasoning_seconds=0.0,
                runtime_settings=runtime,
                agent_messages=agent_messages,
                event_callback=event_callback,
            )

        metadata = get_game_metadata(game)
        context = (
            "当前对局元数据：" + json.dumps(metadata, ensure_ascii=False)
            + "\n规则引擎已生成以下可验证教练报告；请基于它解释，"
            "不要与其中合法性、坐标、分差或五项特征冲突。"
            "无论是否调用工具，最终回答必须包含结论、首选理由、至少一个代价/风险和下一步："
            + json.dumps(_compact_report_for_model(coach_report), ensure_ascii=False)
        )
        messages, context_usage = self._build_messages(
            game_id, context, context_1m=context_1m
        )
        context_usage["thinking_enabled"] = thinking_enabled
        context_usage["show_reasoning"] = show_reasoning
        tool_trace: list[dict] = []
        coach_player_id = int(coach_report["player_id"])
        overlay = _new_overlay(game, coach_player_id)

        try:
            for round_index in range(cfg.LLM_MAX_TOOL_ROUNDS):
                _emit_event(
                    event_callback,
                    "phase",
                    label=(
                        f"DeepSeek 正在推理（第 {round_index + 1} 轮）"
                        if thinking_enabled
                        else f"DeepSeek 正在生成（第 {round_index + 1} 轮）"
                    ),
                    phase="model",
                    round=round_index + 1,
                )
                model_started = time.perf_counter()
                assistant = self._request(
                    api_key,
                    messages,
                    thinking=thinking_enabled,
                    runtime=runtime,
                    event_callback=event_callback,
                    round_index=round_index,
                )
                measured_elapsed = (
                    time.perf_counter() - model_started
                )
                stream_metrics = assistant.pop(
                    "_stream_metrics", {}
                ) or {}
                streamed_reasoning = bool(
                    assistant.pop(
                        "_streamed_reasoning", False
                    )
                )
                assistant.pop("_streamed_content", None)

                round_elapsed = float(
                    stream_metrics.get(
                        "elapsed_seconds",
                        measured_elapsed,
                    )
                )
                model_elapsed_seconds += round_elapsed

                reasoning_piece = _normalize_text(
                    assistant.get("reasoning_content")
                )
                round_reasoning_seconds = float(
                    stream_metrics.get(
                        "reasoning_seconds"
                    ) or 0.0
                )
                if (
                    not round_reasoning_seconds
                    and reasoning_piece
                ):
                    round_reasoning_seconds = (
                        measured_elapsed
                    )
                reasoning_elapsed_seconds += (
                    round_reasoning_seconds
                )

                upstream_rounds.append({
                    "round": round_index + 1,
                    **stream_metrics,
                })
                context_usage["upstream_rounds"] = (
                    upstream_rounds
                )
                context_usage[
                    "upstream_stream_enabled"
                ] = bool(
                    stream_metrics.get(
                        "upstream_stream"
                    )
                )

                if reasoning_piece:
                    reasoning_parts.append(
                        reasoning_piece
                    )
                    if (
                        show_reasoning
                        and not streamed_reasoning
                    ):
                        _emit_event(
                            event_callback,
                            "reasoning",
                            text=reasoning_piece,
                            delta=False,
                            round=round_index + 1,
                            elapsed_seconds=round(
                                round_elapsed, 3
                            ),
                        )
                tool_calls = assistant.get("tool_calls") or []
                if not tool_calls:
                    final_agent_message = {
                        "role": "assistant",
                        "content": (
                            assistant.get("content")
                            or ""
                        ),
                    }
                    if (
                        thinking_enabled
                        and assistant.get(
                            "reasoning_content"
                        ) is not None
                    ):
                        final_agent_message[
                            "reasoning_content"
                        ] = assistant.get(
                            "reasoning_content"
                        )
                    agent_messages.append(
                        final_agent_message
                    )

                    _emit_event(
                        event_callback,
                        "phase",
                        label="模型草稿已返回，正在复核规则证据与棋盘高亮",
                        phase="final-validation",
                        round=round_index + 1,
                    )
                    answer = _normalize_text(assistant.get("content"))
                    if not answer:
                        answer = _local_coach_answer(
                            coach_report,
                            note="模型未返回可用文字，已补充本地可验证解释。",
                        )
                    _merge_text_overlay(overlay, answer, game)
                    selected_overlay = base_overlay or _final_overlay(overlay)
                    coach_report, answer, selected_overlay, coach_mode, guard = _finalize_coach_output(
                        game, text, coach_report, answer, selected_overlay, "deepseek+xai"
                    )
                    _emit_event(
                        event_callback,
                        "phase",
                        label="规则复核完成，正在组装最终回答与交互候选",
                        phase="final-assembly",
                        round=round_index + 1,
                    )
                    return self._finish(
                        game_id=game_id, answer=answer, model=runtime["model"],
                        tool_trace=tool_trace, board_overlay=selected_overlay,
                        coach_report=coach_report, coach_mode=coach_mode,
                        coach_guard=guard,
                        context_usage=context_usage,
                        reasoning_content=(
                            _bounded_reasoning(reasoning_parts)
                            if show_reasoning
                            else ""
                        ),
                        thinking_enabled=thinking_enabled,
                        context_1m=context_1m,
                        elapsed_seconds=time.perf_counter() - request_started,
                        reasoning_seconds=reasoning_elapsed_seconds,
                        runtime_settings=runtime,
                        agent_messages=agent_messages,
                        event_callback=event_callback,
                        configured=True,
                    )

                _emit_event(
                    event_callback,
                    "phase",
                    label=f"模型已选择 {len(tool_calls)} 个工具，正在执行",
                    phase="tool-plan",
                    round=round_index + 1,
                    tool_count=len(tool_calls),
                )
                assistant_tool_message = {
                    "role": "assistant",
                    "content": assistant.get("content") or "",
                    "tool_calls": tool_calls,
                }
                if thinking_enabled and assistant.get("reasoning_content") is not None:
                    assistant_tool_message["reasoning_content"] = assistant.get(
                        "reasoning_content"
                    )
                messages.append(assistant_tool_message)
                agent_messages.append(
                    copy.deepcopy(assistant_tool_message)
                )
                for tool_index, call in enumerate(tool_calls, start=1):
                    call_id = call.get("id") or "tool-call"
                    function = call.get("function") or {}
                    name = function.get("name") or ""
                    raw_arguments = function.get("arguments") or "{}"
                    try:
                        arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
                    except json.JSONDecodeError:
                        arguments = {}

                    locked_player_tools = {
                        "get_legal_moves", "evaluate_position", "evaluate_move",
                        "rank_candidate_moves", "recommend_move", "explain_position",
                    }
                    if name in locked_player_tools:
                        arguments["player_id"] = coach_player_id

                    _emit_event(
                        event_callback,
                        "tool_start",
                        id=call_id,
                        call_id=call_id,
                        round=len(tool_trace) + 1,
                        name=name,
                        label=_TOOL_LABELS.get(name, name),
                        arguments=arguments,
                        source="mcp-shared-tool-registry",
                        tool_index=tool_index,
                        tool_total=len(tool_calls),
                        model_round=round_index + 1,
                    )
                    started = time.perf_counter()
                    success = True
                    error = None
                    try:
                        result = execute_chat_tool(name, arguments, game)
                    except Exception as exc:
                        success = False
                        error = str(exc)
                        result = {"error": error}
                    duration_ms = (time.perf_counter() - started) * 1000
                    self.database.log_tool_call(
                        game_id=game_id, source="deepseek", operation=name,
                        arguments=arguments, result=result, success=success,
                        error=error, duration_ms=duration_ms, request_id=call_id,
                    )
                    if success:
                        _merge_tool_overlay(overlay, name, result, game, coach_player_id)
                    trace_entry = {
                        "round": len(tool_trace) + 1,
                        "model_round": round_index + 1,
                        "call_id": call_id,
                        "source": "mcp-shared-tool-registry",
                        "name": name,
                        "label": _TOOL_LABELS.get(name, name),
                        "arguments": arguments,
                        "success": success,
                        "duration_ms": round(duration_ms, 2),
                        "error": error,
                        "result_preview": _tool_preview(result),
                    }
                    tool_trace.append(trace_entry)
                    _emit_event(
                        event_callback,
                        "tool_end",
                        id=call_id,
                        tool_index=tool_index,
                        tool_total=len(tool_calls),
                        **trace_entry,
                    )
                    _emit_event(
                        event_callback,
                        "phase",
                        label=(
                            f"工具 {tool_index}/{len(tool_calls)} 已完成，"
                            "正在整理返回结果"
                        ),
                        phase="tool-result",
                        round=round_index + 1,
                    )
                    tool_message = {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": json.dumps(
                            result,
                            ensure_ascii=False,
                        ),
                    }
                    messages.append(tool_message)
                    agent_messages.append(
                        copy.deepcopy(tool_message)
                    )

                _emit_event(
                    event_callback,
                    "phase",
                    label=(
                        "MCP 结果已汇总，DeepSeek 正在综合工具证据"
                        f"（下一轮 {round_index + 2}）"
                    ),
                    phase="post-tool-synthesis",
                    round=round_index + 1,
                )

            _emit_event(
                event_callback,
                "phase",
                label="工具轮次达到上限，正在生成本地可验证回答",
                phase="tool-limit-fallback",
            )
            answer = _local_coach_answer(
                coach_report,
                note="工具调用达到上限，已使用规则引擎给出完整解释。",
            )
            selected_overlay = base_overlay or _final_overlay(overlay)
            coach_report, answer, selected_overlay, coach_mode, guard = _finalize_coach_output(
                game, text, coach_report, answer, selected_overlay, "local-tool-limit"
            )
            return self._finish(
                game_id=game_id, answer=answer, model=runtime["model"],
                tool_trace=tool_trace, board_overlay=selected_overlay,
                coach_report=coach_report, coach_mode=coach_mode,
                coach_guard=guard,
                context_usage=context_usage,
                reasoning_content=(
                    _bounded_reasoning(reasoning_parts)
                    if show_reasoning
                    else ""
                ),
                thinking_enabled=thinking_enabled,
                context_1m=context_1m,
                elapsed_seconds=time.perf_counter() - request_started,
                reasoning_seconds=reasoning_elapsed_seconds,
                runtime_settings=runtime,
                agent_messages=agent_messages,
                event_callback=event_callback,
                configured=True,
            )
        except requests.RequestException as exc:
            answer = _local_coach_answer(
                coach_report,
                note="DeepSeek 暂时不可用，本次已自动切换到本地可解释教练。",
            )
            selected_overlay = base_overlay or _final_overlay(overlay)
            coach_report, answer, selected_overlay, coach_mode, guard = _finalize_coach_output(
                game, text, coach_report, answer, selected_overlay, "local-fallback"
            )
            return self._finish(
                game_id=game_id, answer=answer, model=runtime["model"],
                tool_trace=tool_trace, board_overlay=selected_overlay,
                coach_report=coach_report, coach_mode=coach_mode,
                coach_guard=guard,
                context_usage=context_usage,
                reasoning_content=(
                    _bounded_reasoning(reasoning_parts)
                    if show_reasoning
                    else ""
                ),
                thinking_enabled=thinking_enabled,
                context_1m=context_1m,
                elapsed_seconds=time.perf_counter() - request_started,
                reasoning_seconds=reasoning_elapsed_seconds,
                runtime_settings=runtime,
                agent_messages=agent_messages,
                event_callback=event_callback,
                configured=True,
                error=str(exc),
            )
        except Exception as exc:
            answer = _local_coach_answer(
                coach_report,
                note="语言模型处理异常，本次已自动切换到本地可解释教练。",
            )
            selected_overlay = base_overlay or _final_overlay(overlay)
            coach_report, answer, selected_overlay, coach_mode, guard = _finalize_coach_output(
                game, text, coach_report, answer, selected_overlay, "local-fallback"
            )
            return self._finish(
                game_id=game_id, answer=answer, model=runtime["model"],
                tool_trace=tool_trace, board_overlay=selected_overlay,
                coach_report=coach_report, coach_mode=coach_mode,
                coach_guard=guard,
                context_usage=context_usage,
                reasoning_content=(
                    _bounded_reasoning(reasoning_parts)
                    if show_reasoning
                    else ""
                ),
                thinking_enabled=thinking_enabled,
                context_1m=context_1m,
                elapsed_seconds=time.perf_counter() - request_started,
                reasoning_seconds=reasoning_elapsed_seconds,
                runtime_settings=runtime,
                agent_messages=agent_messages,
                event_callback=event_callback,
                configured=True,
                error=str(exc),
            )
