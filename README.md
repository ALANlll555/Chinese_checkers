# 跳棋 · Chinese Checkers (3rd Edition)

六角星棋盘跳棋，支持 2/3/4/6 人对战与人机对弈。提供 6 套可切换皮肤主题、背景音乐与音效系统。

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
| 🎨 主题皮肤 | 3 种风格 × 浅/深双模式 = 6 套主题（iOS · 极简 · 卡通） |
| 🎵 背景音乐 | 4 种独立可选风格（钢琴 · 环境音 · 8-bit · Lo-fi） |
| 🔊 音效反馈 | 选中 / 落子 / 连跳 / 胜利 / 悔棋 / 按钮 音效 |

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
│   ├── css/style.css   # 多主题 CSS 变量体系 + 6 套皮肤
│   ├── js/audio.js     # Web Audio 音效引擎 + BGM 生成器
│   └── js/game.js      # Canvas 棋盘渲染 + 交互 + Theme 桥接
└── templates/
    └── index.html      # 前端页面
```

---

## 主题皮肤

点击面板顶部的 6 个色块即可切换主题，视觉风格和 Canvas 棋盘同步变化：

| 风格 | 浅色 | 深色 |
|------|------|------|
| 🍎 **iOS** | 毛玻璃卡片 + SF 字体 + 系统蓝 | OLED 黑底 + 暗色毛玻璃 |
| ◻️ **极简** | 纯白底 + 细灰边框 + 零阴影 | 纯黑底 + 高对比白字 |
| 🎨 **卡通** | 奶油底 + 粗黑描边 + 漫画阴影 | 深紫底 + 霓虹品红发光 |

主题设置自动保存，刷新不丢失。

## 背景音乐 & 音效

- **BGM**：4 种风格（🎹钢琴 / 🏖️环境音 / 🎮8-bit / 🎷Lo-fi），与视觉主题独立选择
- **音效**：全部使用 Web Audio API 程序化合成，无需外部音频文件
- BGM 默认关闭，点击 🔊 按钮开启；音量可调节

## AI 点评

在设置面板输入 [DeepSeek API Key](https://platform.deepseek.com)（可选），PVE 模式中 AI 走棋后可获得电竞风格点评。不设置不影响正常游戏。

---

## 许可

仅限个人娱乐使用。
