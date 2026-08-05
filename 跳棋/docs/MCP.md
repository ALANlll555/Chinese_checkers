# MCP 服务

## 玩家发布版

双击根目录 `启动游戏.bat` 后，MCP 会与游戏一起启动：

```text
Transport: Streamable HTTP
Endpoint:  http://127.0.0.1:8765/mcp
```

无需再运行第二个 BAT。

## 外部宿主的 stdio 模式

需要由桌面 MCP 宿主自行管理进程时，可继续使用：

```bash
cd 跳棋
python mcp_server.py --transport stdio
```

# MCP 接口说明

## 设计目标

MCP 服务只读取 SQL 中已持久化的棋局，不直接替玩家落子。浏览器内 DeepSeek 对话与 MCP 服务共用 `game_tools.py`，因此合法走法、评价结果和推荐算法保持一致。

## 启动

```bash
pip install -r requirements.txt
python mcp_server.py --transport stdio
```

Streamable HTTP：

```bash
python mcp_server.py --transport streamable-http
```

默认数据库位于 `data/chinese_checkers.sqlite3`。可通过环境变量覆盖：

```bash
CHINESE_CHECKERS_DB=/absolute/path/game.sqlite3
```

## Tools

数据类：

- `list_games`
- `get_game_metadata`
- `get_game_state`
- `get_move_history`
- `get_ai_decisions`
- `get_evaluation_snapshots`
- `get_chat_history`
- `get_tool_audit_logs`
- `list_replays`
- `get_replay`
- `get_board_geometry`
- `get_game_statistics`

计算类：

- `get_legal_moves`
- `evaluate_position`
- `evaluate_move`
- `rank_candidate_moves`
- `recommend_move`
- `simulate_moves`

## Resources

- `game://{game_id}/state`
- `game://{game_id}/moves`
- `game://{game_id}/chat`
- `game://{game_id}/ai-decisions`
- `game://{game_id}/evaluations`

## Prompt

- `analyze_chinese_checkers_position`

## DeepSeek 接入方式

浏览器中的 AI 助手使用 DeepSeek Chat Completions 的工具调用格式，并把工具调用映射到同一套 `game_tools.py`。若使用支持 MCP 的外部宿主，则直接注册 `mcp_server.py`；示例见 `mcp_config.example.json`。

API Key 不写入 SQL、棋谱或 MCP 日志，只保存在当前 Flask 进程的对局内存中，或从 `DEEPSEEK_API_KEY` 环境变量读取。
