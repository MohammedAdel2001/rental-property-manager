@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run setup.cmd first to install this project.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" scripts\launch.py
if errorlevel 1 pause
