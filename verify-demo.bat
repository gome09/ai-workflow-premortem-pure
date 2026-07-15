@echo off
chcp 65001 >nul
title AI Risk Premortem Demo - 验证

echo ============================================
echo   企业 AI 项目部署前风险预评估 Demo
echo   四阶段实况验证脚本 (Live E2E)
echo ============================================
echo.
echo 此脚本将：
echo  1. 检查后端 API 是否已就绪
echo  2. 运行四阶段实况端到端测试
echo  3. 汇报测试结果与产物位置
echo.

echo [1/2] 检查后端服务 (http://127.0.0.1:8000/health)...
curl -sf http://127.0.0.1:8000/health >nul 2>&1
if errorlevel 1 (
    echo      ERROR: 无法连接后端 API
    echo             请先运行 start-demo.bat 启动服务后再执行验证
    pause
    exit /b 1
)
echo      OK: 后端已就绪

echo.
echo [2/2] 运行四阶段实况端到端测试...
echo      正在执行 scripts\live_e2e_four_stage.py，请耐心等待...
echo.
uv run python scripts/live_e2e_four_stage.py
set "RC=%errorlevel%"

echo.
echo ============================================
if "%RC%"=="0" (
    echo   PASS: 四阶段实况验证通过
    echo.
    echo   产物位置: artifacts\live_e2e_four_stage\
    echo ============================================
    echo.
    pause
    exit /b 0
) else (
    echo   FAIL: 四阶段实况验证失败 ^(退出码 %RC%^)
    echo.
    echo   请查看详情: artifacts\live_e2e_four_stage\
    echo ============================================
    echo.
    pause
    exit /b 1
)
