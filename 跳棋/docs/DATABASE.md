# SQL 存储组件

## 默认引擎

使用 Python 标准库 `sqlite3`，默认开启：

- Foreign Keys
- WAL 日志
- 10 秒 Busy Timeout
- 每次操作独立连接

数据库位置：`data/chinese_checkers.sqlite3`。

## 表结构

### `games`

保存模式、难度、玩家数、当前玩家、胜负状态和最新完整棋局 JSON。

### `moves`

保存每一步的玩家、来源、坐标、走棋前后状态和 AI 评价分。

### `ai_decisions`

保存 AI 难度、最终动作、局部近似最优候选和计算耗时。

### `evaluation_snapshots`

保存五项局面特征及总分，可用于消融实验和后续训练。

### `chat_messages`

保存用户与 AI 助手的对话。API Key 不保存。

### `mcp_audit_logs`

保存 MCP 或 DeepSeek 工具调用的参数、结果、成功状态和耗时。

## 一致性

- 新游戏：写入 `games`。
- 人类/AI 落子：同一数据库操作中写入 `moves` 并更新 `games.state_json`。
- AI 落子：同时写入 `ai_decisions` 与前后评价快照。
- 悔棋：删除被撤销步数之后的走法、AI 决策和评价快照，并更新最新状态。
- 对话：每条用户和助手消息独立入库。

## 备份

停止服务后复制 SQLite 文件即可。运行中建议使用 SQLite 原生备份命令，避免只复制 WAL 主文件。
