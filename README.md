# 跳棋（Chinese Checkers）

基于 Flask 的六人跳棋网页游戏，支持人机对战和双人对战。

## 环境要求

- Python 3.9+
- pip

## 快速开始

### 1. 安装依赖

```bash
pip install -r 跳棋/requirements.txt
```

### 2. 启动游戏

**Windows 用户**：双击 `启动跳棋.bat`

**Mac / Linux 用户**：在终端中运行：
```bash
cd 跳棋
python app.py
```

### 3. 打开浏览器

启动后，在浏览器中访问：**http://127.0.0.1:5000**

## 玩法说明

- 支持 **6 人** 跳棋（可设置 2~6 位玩家）
- **人机对战**：选择 AI 难度（简单/普通/困难）
- **双人对战**：两位玩家轮流操作
- **棋谱回放**：对局结束后可保存棋谱，随时回放

## LLM 点评功能（可选）

游戏内置 AI 点评功能，需要设置 DeepSeek API Key：

**Windows：**
```cmd
set DEEPSEEK_API_KEY=你的API密钥
python app.py
```

**Mac / Linux：**
```bash
export DEEPSEEK_API_KEY=你的API密钥
python app.py
```

不设置 API Key 不影响正常游戏，仅点评功能不可用。

## 项目结构

```
跳棋/
├── app.py              # Flask 主程序
├── board.py            # 棋盘状态与规则引擎
├── ai.py               # AI 引擎
├── config.py           # 全局配置
├── replay.py           # 棋谱保存与加载
├── llm_comment.py      # LLM 点评模块
├── requirements.txt    # Python 依赖
├── templates/
│   └── index.html      # 前端页面
├── static/
│   ├── css/
│   │   └── style.css   # 样式
│   └── js/
│       └── game.js     # 前端游戏逻辑
└── replays/            # 棋谱存档目录
```
