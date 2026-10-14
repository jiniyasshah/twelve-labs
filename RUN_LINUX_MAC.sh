#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip setuptools wheel
  .venv/bin/python -m pip install -r requirements.txt
fi
export PYTHONUTF8=1
export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-0}"
exec .venv/bin/python -X utf8 server.py
