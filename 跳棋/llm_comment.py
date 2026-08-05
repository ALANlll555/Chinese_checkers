"""
跳棋 — LLM 点评（DeepSeek）
"""

import json
import config as cfg


def _build_prompt(state_dict: dict, move_desc: str, eval_before: float,
                  eval_after: float, player_name: str) -> str:
    """构建送给 LLM 的 prompt。"""
    scores = state_dict.get("scores", {})
    progress = ", ".join(
        f"{cfg.PLAYER_NAMES.get(int(k), k)}: {v}/{cfg.PIECES_PER_PLAYER}"
        for k, v in scores.items()
    )
    return f"""你是跳棋比赛的专业解说。请用一句话（不超过40字）点评以下这一步棋。

当前局面：
- 走棋方：{player_name}
- 各玩家进度：{progress}
- 步数：{state_dict.get('move_count', 0)}

这一步：{move_desc}
走棋前评估分：{eval_before:.1f}
走棋后评估分：{eval_after:.1f}
分数变化：{eval_after - eval_before:+.1f}

请用中文给出犀利、有趣的点评，风格参考电竞解说。"""


def get_comment(state_dict: dict, move: tuple, eval_before: float,
                eval_after: float, player_pid: int, api_key: str | None = None) -> str:
    """
    获取 LLM 对一步棋的点评。

    Args:
        state_dict: 当前局面（BoardState.to_dict()）
        move: ((fr,fc), (tr,tc))
        eval_before: 走棋前评估分
        eval_after: 走棋后评估分
        player_pid: 走棋方编号

    Returns:
        点评文字，或空字符串（API 不可用时）
    """
    api_key = api_key or cfg.LLM_API_KEY
    if not api_key:
        return ""  # 无 API key 时静默跳过

    player_name = cfg.PLAYER_NAMES.get(player_pid, f"玩家{player_pid}")
    (fr, fc), (tr, tc) = move
    move_desc = f"从({fr},{fc})走到({tr},{tc})"

    prompt = _build_prompt(state_dict, move_desc, eval_before, eval_after,
                          player_name)

    try:
        import requests
        resp = requests.post(
            f"{cfg.LLM_API_BASE}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": cfg.LLM_MODEL,
                "messages": [
                    {"role": "system", "content": "你是跳棋解说员，点评风格犀利有趣。"},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": 80,
                "temperature": 0.8,
            },
            timeout=cfg.LLM_TIMEOUT_SECONDS,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
    except Exception:
        pass

    return ""
