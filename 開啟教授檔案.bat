@echo off
rem Windows: double-click to open the professor research files (keep this window open; closing it syncs to Google Drive)
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
chcp 65001 >nul
where uv >nul 2>nul
if errorlevel 1 (
  echo uv not found. Install: powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  pause
  exit /b 1
)
uv sync -q
uv run python scripts\app.py %*
if errorlevel 1 pause
