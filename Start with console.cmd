@echo off
cd /d "%~dp0"
"%~dp0runtime\python.exe" -s -X utf8 "%~dp0main.py"
pause
