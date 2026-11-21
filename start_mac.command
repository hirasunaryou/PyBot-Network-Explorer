#!/bin/bash
cd "$(dirname "$0")" || exit 1
echo "========================================="
echo " PyBot Network Explorer / macOS"
echo " Python standard library · no venv"
echo "========================================="
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3.8+ が必要です: https://www.python.org/downloads/"
  read -r -p "Enterで終了..."
  exit 1
fi
python3 launch.py
status=$?
if [ "$status" -ne 0 ]; then
  echo "起動できませんでした (code=$status)"
  read -r -p "Enterで終了..."
fi
exit "$status"
