#!/usr/bin/env bash
# One-command setup for ARC Remote (macOS).
set -euo pipefail
cd "$(dirname "$0")"

PY=${PYTHON:-python3}
$PY -c 'import sys; assert sys.version_info >= (3, 9), "Python 3.9+ required"'

[ -d venv ] || $PY -m venv venv
# shellcheck disable=SC1091
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

if command -v npm >/dev/null 2>&1; then
  (cd mobileapp && npm install && npm run build)
else
  echo "npm not found - skipping web UI build (install Node 18+ to build the app)."
fi

[ -f .env ] || { cp .env.example .env; echo "Created .env - add your Gemini API_KEY."; }

cat <<MSG

Setup complete. Start the daemon:
  source venv/bin/activate
  python -m remote.server
Then pair your phone:
  python -m remote.pair
Voice mode / local ML models (optional): pip install -r requirements-full.txt
MSG
