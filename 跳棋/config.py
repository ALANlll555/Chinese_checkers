"""
跳棋 — 全局配置
"""

import os

# ── 棋盘 ────────────────────────────────────────────
BOARD_ROWS = 17
BOARD_COLS = 17
TOTAL_HOLES = 121
PIECES_PER_PLAYER = 10

ROW_HOLE_RANGES = [
    (8, 8), (7, 8), (7, 9), (6, 9),
    (2, 14), (2, 13), (3, 13), (3, 12),
    (4, 12), (3, 12), (3, 13), (2, 13),
    (2, 14), (6, 9), (7, 9), (7, 8), (8, 8),
]

PLAYER_HOME_ZONES = {
    0: [  # 顶部
        (0,8),
        (1,7),(1,8),
        (2,7),(2,8),(2,9),
        (3,6),(3,7),(3,8),(3,9),
    ],
    3: [  # 底部
        (13,6),(13,7),(13,8),(13,9),
        (14,7),(14,8),(14,9),
        (15,7),(15,8),
        (16,8),
    ],
    1: [  # 右上
        (4,11),(4,12),(4,13),(4,14),
        (5,11),(5,12),(5,13),
        (6,12),(6,13),
        (7,12),
    ],
    2: [  # 右下
        (9,12),
        (10,12),(10,13),
        (11,11),(11,12),(11,13),
        (12,11),(12,12),(12,13),(12,14),
    ],
    4: [  # 左下
        (9,3),
        (10,3),(10,4),
        (11,2),(11,3),(11,4),
        (12,2),(12,3),(12,4),(12,5),
    ],
    5: [  # 左上
        (4,2),(4,3),(4,4),(4,5),
        (5,2),(5,3),(5,4),
        (6,3),(6,4),
        (7,3),
    ],
}

PLAYER_COLORS = {
    0: "#ff3366", 1: "#00ccff", 2: "#33ff99",
    3: "#ffcc00", 4: "#cc66ff", 5: "#ff6600",
}
PLAYER_GLOW = {
    0: "#ff3366", 1: "#00ccff", 2: "#33ff99",
    3: "#ffcc00", 4: "#cc66ff", 5: "#ff6600",
}
PLAYER_NAMES = {0:"红方",1:"蓝方",2:"绿方",3:"黄方",4:"紫方",5:"橙方"}

# ── AI ──────────────────────────────────────────────
AI_SEARCH_DEPTH = 3
AI_TIME_LIMIT = 2.0
AI_SEARCH_BRANCH_LIMIT = 12
AI_HARD_ROOT_LIMIT = 14
AI_EVAL_CACHE_SIZE = 50000
AI_WIN_SCORE = 100000.0

# 规则驱动的五项局面评价
WEIGHT_GOAL_ASSIGNMENT = -10.0
WEIGHT_LAST_PIECE = -6.0
WEIGHT_FORWARD_JUMP = 4.0
WEIGHT_LADDER_POTENTIAL = 2.5
WEIGHT_HOME_DELAY = -8.0

# 梯子由对手棋子提供时较不稳定；连续第二段跳跃给予额外奖励
AI_OPPONENT_LADDER_STABILITY = 0.65
AI_LADDER_CHAIN_BONUS = 0.35
AI_HOME_BASE_DELAY = 0.25

# 近似最优候选窗口与 Softmax 温度
AI_EASY_MARGIN_RATIO = 0.35
AI_EASY_MARGIN_MIN = 8.0
AI_EASY_MARGIN_MAX = 60.0
AI_EASY_CANDIDATES = 8
AI_EASY_TEMPERATURE = 18.0

AI_MEDIUM_MARGIN_RATIO = 0.15
AI_MEDIUM_MARGIN_MIN = 4.0
AI_MEDIUM_MARGIN_MAX = 25.0
AI_MEDIUM_CANDIDATES = 5
AI_MEDIUM_TEMPERATURE = 7.0

AI_HARD_MARGIN_RATIO = 0.08
AI_HARD_MARGIN_MIN = 2.0
AI_HARD_MARGIN_MAX = 12.0
AI_HARD_CANDIDATES = 3
AI_HARD_TEMPERATURE = 3.0

# ── LLM ─────────────────────────────────────────────
LLM_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
LLM_API_BASE = os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com")
LLM_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
LLM_TIMEOUT_SECONDS = float(os.environ.get("DEEPSEEK_TIMEOUT", "60"))
LLM_CHAT_MAX_TOKENS = int(os.environ.get("DEEPSEEK_CHAT_MAX_TOKENS", "4096"))
LLM_CHAT_TEMPERATURE = float(os.environ.get("DEEPSEEK_CHAT_TEMPERATURE", "0.25"))
LLM_MAX_TOOL_ROUNDS = int(os.environ.get("DEEPSEEK_MAX_TOOL_ROUNDS", "6"))
LLM_HISTORY_LIMIT = int(os.environ.get("DEEPSEEK_HISTORY_LIMIT", "500"))
LLM_MAX_USER_CHARS = int(os.environ.get("DEEPSEEK_MAX_USER_CHARS", "12000"))
# DeepSeek V4 supports a 1M-token context window. The UI can switch between
# a conservative standard profile and the extended 1M profile per request.
LLM_STANDARD_CONTEXT_WINDOW_TOKENS = int(
    os.environ.get("DEEPSEEK_STANDARD_CONTEXT_WINDOW_TOKENS", "131072")
)
LLM_STANDARD_INPUT_BUDGET_TOKENS = int(
    os.environ.get("DEEPSEEK_STANDARD_INPUT_BUDGET_TOKENS", "100000")
)
LLM_CONTEXT_WINDOW_TOKENS = int(
    os.environ.get("DEEPSEEK_CONTEXT_WINDOW_TOKENS", "1000000")
)
LLM_INPUT_BUDGET_TOKENS = int(
    os.environ.get("DEEPSEEK_INPUT_BUDGET_TOKENS", "900000")
)
LLM_CONTEXT_RESERVE_TOKENS = int(
    os.environ.get("DEEPSEEK_CONTEXT_RESERVE_TOKENS", "24000")
)
LLM_CONTEXT_1M_DEFAULT = os.environ.get(
    "DEEPSEEK_CONTEXT_1M_DEFAULT", "1"
).strip().lower() in {"1", "true", "yes", "on"}
LLM_THINKING = os.environ.get(
    "DEEPSEEK_THINKING", "1"
).strip().lower() in {"1", "true", "yes", "on"}
LLM_SHOW_REASONING_DEFAULT = os.environ.get(
    "DEEPSEEK_SHOW_REASONING_DEFAULT", "1"
).strip().lower() in {"1", "true", "yes", "on"}
LLM_REASONING_EFFORT = os.environ.get(
    "DEEPSEEK_REASONING_EFFORT", "high"
).strip().lower()
if LLM_REASONING_EFFORT not in {"low", "high", "xhigh", "max"}:
    LLM_REASONING_EFFORT = "high"
LLM_REASONING_MAX_CHARS = int(
    os.environ.get("DEEPSEEK_REASONING_MAX_CHARS", "120000")
)
LLM_STRICT_TOOLS = os.environ.get("DEEPSEEK_STRICT_TOOLS", "0").strip().lower() in {"1", "true", "yes", "on"}
LLM_BOARD_OVERLAY_LIMIT = int(os.environ.get("DEEPSEEK_BOARD_OVERLAY_LIMIT", "5"))

# ── 路径 ────────────────────────────────────────────
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
REPLAY_DIR = os.path.join(PROJECT_DIR, "replays")
DATA_DIR = os.environ.get("CHINESE_CHECKERS_DATA_DIR", os.path.join(PROJECT_DIR, "data"))
DATABASE_PATH = os.environ.get("CHINESE_CHECKERS_DB", os.path.join(DATA_DIR, "chinese_checkers.sqlite3"))
DATABASE_SCHEMA_PATH = os.path.join(PROJECT_DIR, "schema.sql")

# ── MCP ──────────────────────────────────────────────
# Local release endpoints. They bind to loopback only by default.
APP_HOST = os.environ.get("APP_HOST", "127.0.0.1")
APP_PORT = int(os.environ.get("APP_PORT", "5000"))
APP_URL = os.environ.get("APP_URL", f"http://{APP_HOST}:{APP_PORT}")

MCP_SERVER_NAME = os.environ.get("MCP_SERVER_NAME", "Chinese Checkers")
MCP_TRANSPORT = os.environ.get("MCP_TRANSPORT", "stdio")
MCP_HOST = os.environ.get("MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.environ.get("MCP_PORT", "8765"))
MCP_STREAMABLE_HTTP_PATH = os.environ.get(
    "MCP_STREAMABLE_HTTP_PATH", "/mcp"
)
if not MCP_STREAMABLE_HTTP_PATH.startswith("/"):
    MCP_STREAMABLE_HTTP_PATH = "/" + MCP_STREAMABLE_HTTP_PATH
MCP_URL = os.environ.get(
    "MCP_URL",
    f"http://{MCP_HOST}:{MCP_PORT}{MCP_STREAMABLE_HTTP_PATH}",
)
MCP_AUDIT_RESULT_MAX_CHARS = int(os.environ.get("MCP_AUDIT_RESULT_MAX_CHARS", "20000"))
RELEASE_SERVICE_START_TIMEOUT = float(
    os.environ.get("RELEASE_SERVICE_START_TIMEOUT", "10")
)
