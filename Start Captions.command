#!/bin/bash
cd -- "$(dirname -- "$0")" || exit 1
if [ "$(uname -m)" != "arm64" ]; then
  echo "This download requires an Apple Silicon Mac (M1 or newer)."
  read -r -p "Press Return to close. "
  exit 1
fi
if [ ! -x runtime/bin/python3 ]; then
  echo "Download and extract the Mac package from GitHub Releases first."
  read -r -p "Press Return to close. "
  exit 1
fi
if [ ! -f runtime/.ready ]; then
  echo "First-time setup. Keep this window open; downloads may take a while."
  runtime/bin/python3 -s -X utf8 setup_portable.py || { read -r -p "Setup failed. Press Return to close. "; exit 1; }
fi
runtime/bin/python3 -s -X utf8 main.py
if [ "$?" -ne 0 ]; then read -r -p "App stopped. Press Return to close. "; fi
