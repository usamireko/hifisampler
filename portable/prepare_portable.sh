#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

PYTHON_EXE=""

if [ -f "$PWD/runtime/bin/python3" ]; then
    PYTHON_EXE="$PWD/runtime/bin/python3"
elif [ -f "$PWD/runtime/bin/python" ]; then
    PYTHON_EXE="$PWD/runtime/bin/python"
elif command -v python3 &>/dev/null; then
    PYTHON_EXE="python3"
elif command -v python &>/dev/null; then
    PYTHON_EXE="python"
else
    echo "Python runtime not found. Use the full portable package or install Python 3.10."
    exit 1
fi

"$PYTHON_EXE" "$PWD/manager/prepare_portable.py" "$@"
