@echo off
chcp 65001 >nul
title AI Risk Premortem Demo

echo ============================================
echo   企业 AI 项目部署前风险预评估 Demo
echo   AI Workflow Premortem & Human Oversight Platform
echo   Version: 1.2.2
echo ============================================
echo.
echo 启动步骤：
echo  1. 确保 Python 3.11+ 和 uv 已安装
echo  2. 首次运行请先执行 install-demo.bat
echo  3. 本脚本将启动后端 API 和前端界面
echo.
echo 访问地址：
echo   - 前端界面: http://localhost:8501
echo   - 后端 API: http://127.0.0.1:8000
echo.
echo 登录信息：
echo   - 用户名: demo@example.com
echo   - 密码: demo-password-123
echo.
echo 按任意键继续...
pause >nul

echo.
echo [1/6] 检查 uv 包管理器...
where uv >nul 2>&1
if errorlevel 1 (
    echo      ERROR: 未检测到 uv
    echo             请先运行 install-demo.bat 安装依赖环境
    pause
    exit /b 1
)
echo      OK: uv 已安装

echo.
echo [2/6] 检查虚拟环境 (.venv)...
if not exist .venv\ (
    echo      ERROR: 未检测到 .venv 虚拟环境
    echo             请先运行 install-demo.bat 安装项目依赖
    pause
    exit /b 1
)
echo      OK: .venv 已存在

echo.
echo [3/6] 检查端口占用 (8000 / 8501)...
netstat -ano | findstr ":8000" | findstr LISTENING >nul
if not errorlevel 1 (
    echo      ERROR: 端口 8000 已被占用
    echo             后端服务可能已在运行，或有其他进程占用该端口
    echo             请先运行 stop-demo.bat 停止已有服务后重试
    pause
    exit /b 1
)
netstat -ano | findstr ":8501" | findstr LISTENING >nul
if not errorlevel 1 (
    echo      ERROR: 端口 8501 已被占用
    echo             前端服务可能已在运行，或有其他进程占用该端口
    echo             请先运行 stop-demo.bat 停止已有服务后重试
    pause
    exit /b 1
)
echo      OK: 端口 8000 与 8501 均空闲

echo.
echo [4/6] 切换到演示模式配置...
if not exist .env (
    copy .env.demo .env >nul
    echo      已创建 .env (演示模式)
) else (
    echo      .env 已存在，保留当前配置
)

echo.
echo [5/6] 启动后端服务 (端口 8000)...
start "Backend API" cmd /k "uv run uvicorn api.main:app --port 8000"

echo.
echo       等待后端就绪 (健康检查，最长 60 秒)...
set ATTEMPT=0
:wait_backend
set /a ATTEMPT+=1
curl -sf http://127.0.0.1:8000/health >nul 2>&1
if not errorlevel 1 goto backend_ready
if %ATTEMPT% GEQ 30 goto backend_timeout
echo       等待后端就绪... (%ATTEMPT%/30)
timeout /t 2 /nobreak >nul
goto wait_backend

:backend_timeout
echo.
echo      ERROR: 后端在 60 秒内未就绪
echo             请查看 "Backend API" 窗口中的错误日志排查问题
echo             确认无误后可运行 stop-demo.bat 清理，再重新启动
pause
exit /b 1

:backend_ready
echo      OK: 后端已就绪

echo.
echo [6/6] 启动前端服务 (端口 8501)...
start "Frontend UI" cmd /k "uv run streamlit run frontend/app.py --server.port 8501"

echo.
echo       自动打开浏览器...
start "" http://localhost:8501

echo.
echo ============================================
echo   服务已启动！
echo.
echo   前端界面: http://localhost:8501
echo   后端 API: http://127.0.0.1:8000
echo.
echo   登录：demo@example.com / demo-password-123
echo.
echo   停止服务请运行: stop-demo.bat
echo   按 Ctrl+C 可关闭当前窗口
echo ============================================
echo.
