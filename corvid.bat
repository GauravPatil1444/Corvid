@echo off
:: 1. Save the directory where the user typed the command (e.g., your React folder)
set TARGET_WORKSPACE=%CD%

:: 2. Switch to the Corvid folder so uv perfectly loads the .venv and .env files
cd /d D:\Python\projects\Corvid

:: 3. Run the AI Debugger, passing arguments like "start" or "init"
uv run main.py %*

:: 4. Switch back to your original folder so your terminal stays put
cd /d "%TARGET_WORKSPACE%"