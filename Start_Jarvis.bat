@echo off
title Jarvis Voice Assistant
cd /d "%~dp0"
echo Starting Jarvis...
call .venv\Scripts\activate.bat
python main2.py
pause
