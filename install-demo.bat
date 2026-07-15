@echo off
chcp 65001 >nul
title AI Risk Premortem Demo - 安装

echo ============================================
echo   企业 AI 项目部署前风险预评估 Demo
echo   依赖安装脚本 (Windows)
echo ============================================
echo.
echo 此脚本将：
echo  1. 检查 Python 版本 (需要 3.11+)
echo  2. 检查 uv 是否安装
echo  3. 使用 uv 安装项目依赖
echo  4. 创建演示模式配置文件
echo.

echo.
echo [1/4] 检查 Python 版本...
python --version 2>&1 | findstr /i "Python 3.1" >nul
if errorlevel 1 (
    echo      ERROR: 未检测到 Python 3.11+
    echo             请安装 Python 3.11+ 并添加到 PATH
    pause
    exit /b 1
)
echo      OK: Python 版本检查通过

echo.
echo [2/4] 检查 uv 包管理器...
where uv >nul 2>&1
if errorlevel 1 (
    echo      正在安装 uv...
    powershell -Command "Invoke-WebRequest -Uri 'https://astral.sh/uv/install.ps1' -UseBasicParsing | Invoke-Expression"
    if errorlevel 1 (
        echo      ERROR: uv 安装失败
        echo             请手动安装 uv: https://github.com/astral-sh/uv
        pause
        exit /b 1
    )
    echo      OK: uv 安装成功
) else (
    echo      OK: uv 已安装
)

echo.
echo [3/4] 安装项目依赖...
echo      这可能需要几分钟，请耐心等待...
uv sync
if errorlevel 1 (
    echo      ERROR: 依赖安装失败
    pause
    exit /b 1
)
echo      OK: 依赖安装成功

echo.
echo [4/4] 创建演示模式配置...
if not exist .env (
    copy .env.demo .env >nul
    echo      OK: 已创建 .env (演示模式，无需真实 API Key)
) else (
    echo      OK: .env 已存在
)

echo.
echo ============================================
echo   安装完成！
echo.
echo   接下来运行：start-demo.bat
echo.
echo   访问地址：
echo     - 前端界面: http://localhost:8501
echo     - 后端 API: http://127.0.0.1:8000
echo.
echo   登录：demo@example.com / demo-password-123
echo ============================================
echo.
pause
