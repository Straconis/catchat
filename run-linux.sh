#!/usr/bin/env sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if ! command -v python3 >/dev/null 2>&1; then
  echo 'Install Python 3 first.' >&2
  exit 1
fi
if ! python3 -c 'import tkinter' >/dev/null 2>&1; then
  echo 'Install Tk and venv. Ubuntu/Debian: sudo apt install python3-tk python3-venv' >&2
  echo 'Fedora: sudo dnf install python3-tkinter' >&2
  exit 1
fi
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
if ! .venv/bin/python -c 'import PIL, cryptography' >/dev/null 2>&1; then
  .venv/bin/python -m pip install -r requirements.txt
fi
exec .venv/bin/python cat_chat.py
