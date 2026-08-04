@echo off
chcp 65001 >nul
title 跳棋 - Chinese Checkers

cd /d "%~dp0跳棋"

echo ================================
echo   跳棋 Chinese Checkers
echo ================================
echo.
echo 正在检查 Python 环境...

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.9+
    echo 下载地址：https://www.python.org/downloads/
    pause
    exit /b 1
)

echo 正在安装依赖...
pip install -r requirements.txt -q

echo.
echo 正在启动游戏服务器...
echo 请在浏览器中打开：http://127.0.0.1:5000
echo 按 Ctrl+C 可停止服务器
echo ================================
echo.

python app.py

pause
