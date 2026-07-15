@echo off
chcp 65001 >nul
title AI Risk Premortem Demo - 停止服务
setlocal enabledelayedexpansion

echo ============================================
echo   企业 AI 项目部署前风险预评估 Demo
echo   停止服务脚本 (Windows)
echo ============================================
echo.
echo 此脚本将停止占用以下端口的服务进程：
echo   - 后端 API : 8000
echo   - 前端界面 : 8501
echo.

echo [1/2] 停止后端服务 (端口 8000)...
set FOUND8000=0
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8000" ^| findstr LISTENING') do (
    taskkill /PID %%p /F >nul 2>&1
    echo      端口 8000: 已停止 (PID %%p)
    set FOUND8000=1
)
if "!FOUND8000!"=="0" (
    echo      端口 8000: 未在运行
)

echo.
echo [2/2] 停止前端服务 (端口 8501)...
set FOUND8501=0
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8501" ^| findstr LISTENING') do (
    taskkill /PID %%p /F >nul 2>&1
    echo      端口 8501: 已停止 (PID %%p)
    set FOUND8501=1
)
if "!FOUND8501!"=="0" (
    echo      端口 8501: 未在运行
)

echo.
echo ============================================
echo   停止操作完成
echo.
echo   如需重新启动，请运行: start-demo.bat
echo ============================================
echo.
endlocal
pause
