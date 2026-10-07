#!/bin/bash
# Double-click this file to open the ASICS app in your web browser.
# Keep this window open while you use the app; close it to stop the app.
cd "$(dirname "$0")"
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
if ! command -v uv >/dev/null 2>&1; then
  echo "This computer isn't set up yet (the 'uv' tool is missing)."
  echo "Please ask your developer to follow 'Setting up a new computer' in README.md."
  read -n 1 -s -r -p "Press any key to close."
  exit 1
fi
echo "Starting the ASICS app. Your browser will open in a few seconds..."
uv run --quiet streamlit run app.py
