@echo off
REM Double-click this file to open the ASICS app in your web browser.
cd /d "%~dp0"
where uv >nul 2>nul || (echo This computer is not set up yet. Ask your developer. & pause & exit /b 1)
if not exist "%LOCALAPPDATA%\ms-playwright" echo Note: the browser used for JavaScript pages is not installed. The app still works, but Step 1 will skip that stage. To install it once, run: uv run playwright install chromium
echo Starting the ASICS app. Your browser will open in a few seconds...
uv run --quiet streamlit run app.py
