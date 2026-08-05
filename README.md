# 跳棋 · Chinese Checkers (2nd Edition)

霓虹风格六角星棋盘跳棋，支持 2/3/4/6 人对战与人机对弈。

---

## 系统要求

- **Python 3.9+**
- 操作系统：Windows / macOS / Linux
- 浏览器：Chrome / Edge / Firefox（推荐 Chrome）

## 快速开始

### Windows

双击 **`启动跳棋.bat`**，等待依赖安装后在浏览器打开 `http://127.0.0.1:5000`

### macOS / Linux

```bash
cd 跳棋
pip install -r requirements.txt
python app.py
```

浏览器访问 **`http://127.0.0.1:5000`**

---

## 功能

| 功能 | 说明 |
|------|------|
| 🎮 游戏模式 | PVP（人人对战）/ PVE（人机对战） |
| 👥 玩家人数 | 2 / 3 / 4 / 6 人 |
| 🤖 AI 难度 | ★ 随机 / ★★ 贪心 / ★★★ Minimax（Alpha-Beta 剪枝） |
| 💡 提示 | 最高难度 AI 推荐当前最佳走法 |
| ↩ 悔棋 | 单步 / 双步（PVE 模式自动撤销 AI 回合） |
| 🎬 回放 | 对局中实时回顾 + 存档加载回放 |
| 🗂 存档管理 | 命名存档、删除、重命名 |
| 🤖 AI 点评 | 接入 DeepSeek API，电竞解说风格点评（可选） |

---

## 文件结构

```
跳棋/
├── app.py              # Flask Web 服务
├── board.py            # 棋盘状态与规则引擎
├── ai.py               # AI 引擎（随机 / 贪心 / Minimax）
├── config.py           # 全局配置
├── replay.py           # 棋谱保存与加载
├── llm_comment.py      # LLM 点评（DeepSeek）
├── requirements.txt    # Python 依赖
├── static/
│   ├── css/style.css   # 霓虹主题样式
│   └── js/game.js      # Canvas 棋盘渲染 + 交互逻辑
└── templates/
    └── index.html      # 前端页面
```

---

## AI 点评

在设置面板输入 [DeepSeek API Key](https://platform.deepseek.com)（可选），PVE 模式中 AI 走棋后可获得电竞风格点评。不设置不影响正常游戏。

---

## 许可

仅限个人娱乐使用。
