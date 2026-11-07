@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" host\gui.py %*
) else (
  py -3 host\gui.py %*
)
if errorlevel 1 (
  echo.
  echo Could not start GUI. Create .venv and install requirements-host.txt, or install pyserial for Python 3.
  pause
)
