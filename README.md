# 跳棋 · Chinese Checkers (3rd Edition)

六角星棋盘跳棋，支持 2/3/4/6 人对战、人机对弈、DeepSeek 局面助手、MCP 工具服务和 SQLite 全量记录。

## 系统要求

- Python 3.10+
- Windows / macOS / Linux
- Chrome / Edge / Firefox

## 快速开始

### Windows

双击 `启动跳棋.bat`，浏览器打开 `http://127.0.0.1:5000`。

### macOS / Linux

```bash
cd 跳棋
pip install -r requirements.txt
python app.py
```

## 主要功能

| 功能 | 说明 |
|---|---|
| 游戏模式 | PVP / PVE，支持 2、3、4、6 人 |
| 三档 AI | 受控随机、近似最优采样、Alpha-Beta/Paranoid |
| 左侧 AI 助手 | 与右侧栏等宽，不改变棋盘尺寸；可询问局面、推荐与复盘 |
| DeepSeek 工具调用 | 对话通过真实棋局工具读取状态、合法走法和评价，不直接落子 |
| MCP 服务 | Tools、Resources、Prompt；支持 stdio 和 Streamable HTTP |
| SQL 存储 | 保存棋局、走法、AI 决策、评价、对话和工具审计日志 |
| 回放与存档 | 文件棋谱继续保留，与 SQL 记录并行 |
| 主题与音频 | 原有 6 套主题、4 种 BGM 和全部音效保持不变 |

## DeepSeek 配置

可在右侧设置栏输入 Key，或设置环境变量：

```bash
DEEPSEEK_API_KEY=your-key
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_API_BASE=https://api.deepseek.com
```

浏览器输入的 Key 只保存在当前 Flask 进程内存中，不进入 SQL、棋谱或 MCP 日志。

## MCP 使用

玩家无需单独启动 MCP；`启动游戏.bat` 会自动提供本地 Streamable HTTP 端点：

```text
http://127.0.0.1:8765/mcp
```

需要由外部 MCP 宿主使用 stdio 时，仍可直接配置：

```bash
cd 跳棋
python mcp_server.py --transport stdio
```

外部宿主示例见 `跳棋/mcp_config.example.json`，工具清单见 `跳棋/docs/MCP.md`。


## SQL 数据库

默认文件：

```text
跳棋/data/chinese_checkers.sqlite3
```

可通过 `CHINESE_CHECKERS_DB` 指定其他路径。表结构与备份说明见 `跳棋/docs/DATABASE.md`。

## 文件结构

```text
跳棋/
├── app.py                 # Flask API 与会话协调
├── board.py               # 原有规则引擎
├── ai.py                  # 原有三档 AI 与五项评价
├── database.py            # SQLite 数据访问组件
├── schema.sql             # SQL 表结构
├── state_codec.py         # SQL JSON 与 BoardState 转换
├── game_tools.py          # DeepSeek/MCP 共用工具层
├── deepseek_chat.py       # DeepSeek 工具调用适配器
├── mcp_server.py          # 独立 MCP 服务
├── llm_comment.py         # 原有 AI 走棋点评
├── replay.py              # 原有文件棋谱
├── docs/
│   ├── MCP.md
│   └── DATABASE.md
├── static/
│   ├── css/style.css
│   └── js/
│       ├── audio.js
│       ├── game.js
│       └── chat.js
└── templates/index.html
```

## 测试

```bash
cd 跳棋
python -m unittest discover -s tests -v
```

## 许可

仅限个人娱乐与研究使用。


## 坐标与 AI 棋盘标记

- 棋盘左上角的“⌖ 坐标”按钮可随时开启或关闭坐标层，默认关闭。
- 坐标格式为 `(行,列)`；由于前端保持红方在下方，`行 0` 显示在屏幕下方，`行 16` 在上方。
- AI 回复中的坐标会显示为可点击胶囊；点击后会在棋盘定位该孔位。
- DeepSeek 调用推荐、候选排序、走法评价或模拟工具后，结果会以箭头覆盖在棋盘上。
- 所有坐标、箭头和标签均为只读视觉层，不写入棋局状态，不触发落子；真实局面变化后旧标记自动清除。

## AI 回复格式

AI 回复使用安全的轻量 Markdown 渲染。`#` 标题、`*` 列表、`**粗体**`、代码块与表格会被正确显示，不再以原始符号直接出现。模型返回的 HTML 会先转义，避免脚本注入。

## 高清坐标与候选路径交互

- Canvas 会按设备像素比进行高 DPI 渲染，逻辑尺寸仍为 720 × 680，因此布局、点击坐标和棋局规则均不变；高分屏上的棋子边缘与文字更清晰。
- 坐标层增加“空位优先 / 全部孔位”两种显示方式：空位优先不会把坐标压在棋子上；全部孔位会将有棋子的坐标移到棋子旁边并用引线连接。
- DeepSeek 推荐后，棋盘先显示最多 5 个编号目标。点击某个目标或顶部候选按钮后，才展开该候选的具体棋子、完整落点路径、跳板位置与目标。
- 当玩家已经选中真实棋子准备落子时，原有落子点击拥有更高优先级，AI 覆盖层不会阻止正常操作。
- AI 回复内会同时生成候选卡片，直接显示“目标、使用的棋子、单步/连跳段数”，并可点击“查看路径”。


## 发布版启动说明

- 根目录只保留一个 Windows 启动按钮：`启动游戏.bat`。
- `.venv`、运行数据库和日志均在首次启动时本地生成，不包含在发布压缩包中。
- 启动日志位于 `跳棋/logs/launcher.log`，MCP 日志位于 `跳棋/logs/mcp.log`。
- 游戏和 MCP 默认仅监听 `127.0.0.1`，不会直接向局域网或公网开放。


## 启动器修复版

请先完整解压 ZIP，再双击 `启动游戏.bat`。不要在 Windows 压缩包预览窗口中直接运行 BAT。

新版启动器：

- BAT 使用纯 ASCII、无 BOM，避免 Windows CMD 编码导致首行解析异常；
- 启动失败或服务退出后窗口一定保留，不再闪退；
- 根目录自动生成 `startup.log`；
- MCP 改为独立 Uvicorn 绑定，并更新稳定版 SDK 约束；
- MCP 启动失败不再阻止游戏和 DeepSeek 助手启动；
- 如果 5000 端口已有游戏实例，会直接打开现有页面。


## Explainable AI Coach 与大棋盘恢复版

- AI Coach 默认从人类玩家视角分析，不再因当前轮到 AI 而误分析对手。
- 即使没有 DeepSeek Key、网络异常或 MCP 不可用，本地规则引擎仍会输出完整分析。
- 每份分析包含：局面阶段、五项特征、诊断、最多五个候选、完整路径、收益、代价、反事实和置信度。
- 这些内容是可核验的特征证据，不是语言模型私有思维链。
- 棋盘逻辑尺寸由 720×680 放大至 820×760，孔距与棋子同步放大；页面会响应式缩放并保留四周安全边距。


## 推荐系统完整审计修复

- 人机对战中的 AI Coach 推荐被锁定为人类红方，DeepSeek 不能通过工具参数切换到对手。
- 每个候选必须同时满足：起点是己方真实棋子、终点为空、坐标为有效孔位、走法属于规则引擎合法集合。
- 棋盘覆盖层不再信任模型文字坐标，只显示规则引擎验证通过的结构化走法。
- 首选候选会自动显示起点棋子、完整路径和终点，避免把空目标孔误认为要操作的棋子。
- 多候选共用同一目标时，目标圆环始终位于孔位中心；编号徽标通过引线区分，不再把目标点画在棋格之间。
- 覆盖层携带 move_count 与 state_token，过期建议会被前端拒绝并要求重新分析。


## 中局空跳与解释完整性修复

- AI 文字中的坐标不再生成走法覆盖层；只有规则引擎元数据可以高亮。
- 每次绘制前重新校验局面令牌、起点棋子和空终点，任何过期覆盖层立即移除。
- 回放、重载和退出回放都统一清除旧建议。
- 连跳路径以“同一颗棋”的半透明落点显示，不再看起来像多个空点之间有不存在的棋子。
- Coach 报告、候选和覆盖层写入 SQLite 元数据，刷新页面后仍可恢复解释；过期高亮只保留历史说明，不会作用于当前棋盘。
- DeepSeek V4 默认启用 1,000,000-token 上下文配置，输入预算为 900,000 tokens，并进行近似 token 裁剪。
- 1M 上下文用于保留长对话和稳定系统前缀；合法性和高亮仍由本地规则引擎决定。


## DeepSeek 推理过程与 1M 开关

AI 教练左侧新增两个开关：

- **🧠 推理过程**：启用 DeepSeek 思考模式，并在回答下方显示 API 返回的 `reasoning_content`。内容默认折叠，不参与合法走法和棋盘高亮判定。
- **1M 上下文**：开启时使用 1,000,000-token 上下文与 900,000-token 安全输入预算；关闭时使用 131,072-token 标准档与 100,000-token 输入预算。

两个选项保存在浏览器本地，下次打开时继续使用。思考模式的工具调用轮次会完整回传 `reasoning_content`，避免 DeepSeek 在连续工具调用时拒绝请求。


## DeepSeek 完整设置与可观测性

开始游戏前可配置：

- API Key
- Base URL
- 模型名
- 思考模式
- 推理过程显示
- 1M 上下文
- Strict Tools
- reasoning effort（high / max）
- 最大输出 tokens

除 API Key 外，其余设置保存到浏览器本地。API Key 只进入当前服务内存，不写入 SQLite、棋谱或浏览器本地存储。

AI 对话新增：

- 请求期间实时秒表；
- DeepSeek 推理内容及推理耗时；
- 总请求耗时；
- MCP 共享工具注册表的完整调用时间线；
- 每次调用的工具名、参数、成功状态、耗时和结果摘要；
- 刷新后从 SQL 元数据恢复上述记录。


## 推理与 MCP 过程的事件流展示

AI Coach 的单条回复现在按以下顺序实时更新：

```text
推理过程（实时计时，可折叠）
    ↓
MCP 共享工具调用（运行中 / 成功 / 失败）
    ↓
DeepSeek 最终回答
    ↓
思考耗时 / 总耗时 / 工具次数
    ↓
本地 Coach 证据与棋盘候选
```

工具行可展开查看参数和返回结果。该事件流仅负责显示；规则、三级 AI、候选校验、数据库结构、棋盘覆盖层和 DeepSeek 开局设置均未改变。


## 全流程状态与启动优化

### 工具调用后的过程显示

MCP 工具调用结束后，AI Coach 不再停留在静止状态。界面会继续显示：

1. 工具结果整理；
2. DeepSeek 下一轮综合推理；
3. 模型草稿返回；
4. 规则证据与局面令牌复核；
5. 最终回答与交互候选组装。

活动面板保留最近阶段时间线，并每秒接收一次 SSE 心跳。工具调用不会提前停止总计时器。

### 依赖检查

启动器先检查每个已安装模块及其实际版本。只有以下情况才调用 pip：

- 模块未安装；
- 模块无法导入；
- 已安装版本不满足 `requirements.txt`。

`requirements.txt` 或发布包发生变化，但现有版本仍满足要求时，不会下载。可选 MCP 依赖若安装失败，会记录结果并停止每次启动重复下载；需要手动重试时运行：

```bash
cd 跳棋
python bootstrap.py --repair
```

### 首次启动全流程自检

每个发布版本首次启动时会执行一次缓存式自检：

- 检查全部 HTML 内联按钮/输入控件是否能解析到真实 JavaScript 处理函数；
- 使用 Flask 测试客户端执行首页、开局、合法走法、落子、AI、悔棋、提示、点评、聊天事件流、聊天历史、配置测试、MCP 清单、存档加载/重命名/删除等流程；
- 通过后写入 `.venv/.chinese_checkers_release_selftest.json`；
- 同一发布版本后续启动直接跳过。


## DeepSeek 上游真实流式 Agent

此前版本只将本地阶段状态通过 SSE 发送给浏览器，DeepSeek 请求本身仍是整轮返回。本版将 `/api/chat/stream` 使用的 DeepSeek 上游请求改为真实流式：

```text
delta.reasoning_content
→ delta.content
→ delta.tool_calls
→ 本地工具执行
→ 下一子轮 delta.reasoning_content
→ 最终 delta.content
```

实现细节：

- 请求启用 `stream: true`。
- 请求启用 `stream_options.include_usage`。
- 使用 `iter_lines(chunk_size=1)` 解析 DeepSeek SSE。
- 实时显示每个 `reasoning_content` 增量。
- 实时显示模型过程文字增量。
- 工具名称和 JSON 参数生成期间显示“参数流”。
- 工具执行后完整回传该 assistant 消息的 `content`、`reasoning_content` 和 `tool_calls`。
- 完整工具轮次写入 `chat_messages.metadata_json.agent_messages`。
- 后续用户轮次恢复历史 assistant/tool 消息。
- 推理强度支持 `low / high / xhigh / max`。

## 独立推理气泡

每个 DeepSeek 子轮现在使用独立气泡：第 1 轮推理、第 2 轮推理……不会再拼接进同一个推理框。MCP 工具、最终回答、Coach 报告和候选也使用统一的独立气泡。

每个气泡可单独收缩。收缩后仅显示标题；状态、耗时、正文、参数、结果和箭头全部隐藏。新 Token 到达时不会强制重新展开用户已经收缩的气泡。

工具参数草稿使用“模型轮次 + 工具索引”标识，正式工具记录使用 `call_id`，避免不同轮次中相同索引的工具互相覆盖。


## AI 对话无输出热修复

独立气泡版本中，`renderTyping()` 创建了实时 AI 回复容器，但没有将它插入 `chatMessages`。SSE、推理、MCP 和最终回答都在更新一个脱离页面的 DOM 子树，因此界面只显示用户消息。

本版在启动计时器和处理任何 SSE 事件之前执行：

```javascript
messages.appendChild(item);
```

构建阶段使用真实 Chromium 执行两轮推理、MCP 调用、最终回答和独立收缩流程。

## 聊天气泡默认状态与滚动

- 每一轮推理默认收缩，只显示一行标题。
- MCP 参数生成和实际调用默认收缩，只显示一行标题。
- 最终回答、上下文信息、Coach 报告和候选结果默认展开。
- 用户停留在底部时，新内容自动跟随。
- 用户向上滚动后，自动跟随立即暂停，新 Token 不会把视图拉回底部。
- 用户回到底部后自动恢复跟随，也可点击“↓ 回到底部”。
