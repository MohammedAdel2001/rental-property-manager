@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run setup.cmd first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" manage.py test --verbosity 2
if errorlevel 1 goto failed
".venv\Scripts\python.exe" manage.py check
if errorlevel 1 goto failed
echo All checks passed.
pause
exit /b 0
:failed
echo Some checks failed. See the error above.
pause
exit /b 1
