#!/bin/bash
# 跳棋 - Chinese Checkers 启动脚本 (Mac/Linux)

cd "$(dirname "$0")/跳棋"

echo "================================"
echo "  跳棋 Chinese Checkers"
echo "================================"
echo ""

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "[错误] 未找到 Python3，请先安装 Python 3.9+"
    exit 1
fi

echo "正在安装依赖..."
pip3 install -r requirements.txt -q

echo ""
echo "正在启动游戏服务器..."
echo "请在浏览器中打开：http://127.0.0.1:5000"
echo "按 Ctrl+C 可停止服务器"
echo "================================"
echo ""

python3 app.py
