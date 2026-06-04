@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 合同管理工具 - 安装程序
echo ============================================
echo    合同管理工具 - 安装程序
echo ============================================
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
pause
