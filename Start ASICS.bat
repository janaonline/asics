@echo off
REM Double-click this file to open the ASICS app in your web browser.
cd /d "%~dp0"
where uv >nul 2>nul || (echo This computer is not set up yet. Ask your developer. & pause & exit /b 1)
echo Starting the ASICS app. Your browser will open in a few seconds...
uv run --quiet streamlit run app.py
