@echo off
cd /d "%~dp0"
if not exist "%~dp0runtime\python.exe" (
  echo Please download and extract the Windows package from GitHub Releases first.
  pause
  exit /b 1
)
if not exist "%~dp0runtime\.ready" (
  echo First-time setup. Keep this window open. Downloads may take a while.
  "%~dp0runtime\python.exe" -s -X utf8 "%~dp0setup_portable.py"
  if errorlevel 1 (
    echo Setup failed. Check your internet connection and try again.
    pause
    exit /b 1
  )
)
start "Translate Anything" "%~dp0runtime\pythonw.exe" -s -X utf8 "%~dp0main.py"
