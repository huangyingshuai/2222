@echo off
chcp 65001 >nul
title 文档转 MD 归档台
cd /d "%~dp0"
echo.
echo   ============================================
echo     文档转 MD 归档台  正在启动...
echo     浏览器会自动打开 http://localhost:8501
echo     关闭此窗口即停止服务
echo   ============================================
echo.
python -m streamlit run app.py --server.port 8501 --browser.gatherUsageStats false
pause
