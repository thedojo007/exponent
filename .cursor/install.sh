#!/usr/bin/env bash
# Idempotent Cloud Agent bootstrap for the Exponent / Jarvis ClickUp automation scripts.
# Safe to run repeatedly and against cached state.
set -euo pipefail

# Resolve the repository root (this script lives in <repo>/.cursor).
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# System packages:
#   python3-venv : required to create the virtualenv (ensurepip)
#   python3-tk   : Tkinter, for the optional project_lookup GUI helper. The core
#                  Jarvis/ClickUp automation does not need it and a headless VM
#                  cannot display the GUI, but installing it lets the module
#                  import and its xlsx parsing be exercised.
# python3-tk is best-effort; python3-venv is required for the venv below.
if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update -y
  sudo apt-get install -y --no-install-recommends python3-venv
  sudo apt-get install -y --no-install-recommends python3-tk \
    || echo "[install] python3-tk unavailable; project_lookup GUI import will be skipped"
fi

# Create an isolated virtualenv (matches the .gitignore convention of .venv/).
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

echo "[install] Done. Run scripts with: .venv/bin/python <script>.py"
