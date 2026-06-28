@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 合同生成工具

echo ============================================
echo   合同生成工具 - 启动中...
echo ============================================
echo.

:: ── 1. 查找 Python ──
set PYTHON=
for %%p in (python python3 "C:\Program Files\Python312\python.exe" "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" "%LOCALAPPDATA%\Programs\Python\Python313\python.exe") do (
    if not defined PYTHON (
        %%p --version >nul 2>&1 && set PYTHON=%%p
    )
)

if not defined PYTHON (
    echo [错误] 未找到 Python 3.12+
    echo.
    echo 请从 https://www.python.org/downloads/ 下载安装
    echo 安装时务必勾选 "Add Python to PATH"
    pause
    exit /b 1
)

:: ── 2. 检查/创建虚拟环境 ──
set VENV=%~dp0.venv
if not exist "%VENV%\Scripts\python.exe" (
    echo [设置] 首次运行，正在创建虚拟环境...
    %PYTHON% -m venv "%VENV%"
    if errorlevel 1 (
        echo [错误] 创建虚拟环境失败
        pause
        exit /b 1
    )
    echo [设置] 安装依赖包...
    "%VENV%\Scripts\python.exe" -m pip install --quiet flask python-docx openpyxl
    if errorlevel 1 (
        echo [错误] 安装依赖失败，请检查网络连接
        pause
        exit /b 1
    )
    echo [完成] 环境准备完毕！
)

:: ── 3. 启动 ──
set PYTHON=%VENV%\Scripts\python.exe
echo [信息] 启动服务 http://127.0.0.1:5000
echo 请勿关闭此窗口，关闭即停止服务。
echo ============================================
echo.

%PYTHON% app.py
pause
