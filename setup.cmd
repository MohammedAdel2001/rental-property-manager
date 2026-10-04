@echo off
cd /d "%~dp0"
echo Setting up Rental Property Manager...
python --version
if errorlevel 1 goto failed
if not exist ".venv\Scripts\python.exe" python -m venv .venv
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" manage.py migrate
if errorlevel 1 goto failed
".venv\Scripts\python.exe" manage.py seed_demo
if errorlevel 1 goto failed
echo.
echo Ready! Double-click start.cmd to open the application.
pause
exit /b 0
:failed
echo.
echo Setup could not finish. See the error above.
pause
exit /b 1
