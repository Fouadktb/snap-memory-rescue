#!/bin/zsh
set -e
cd "${0:A:h}"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -e . --quiet
exec .venv/bin/python -m app.launcher
