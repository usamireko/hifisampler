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

SERVER_SCRIPT="$PWD/hifiserver.py"
if [ ! -f "$SERVER_SCRIPT" ]; then
    SERVER_SCRIPT="$PWD/../hifiserver.py"
fi
if [ ! -f "$SERVER_SCRIPT" ]; then
    echo "ERROR: hifiserver.py was not found."
    exit 1
fi

export HIFISAMPLER_CONFIG="$PWD/config.yaml"
export HIFISAMPLER_DEFAULT_CONFIG="$PWD/config.default.yaml"

mkdir -p "$PWD/logs"
LOG_FILE="$PWD/logs/server.log"

if [ -f "$PWD/manager/prepare_portable.py" ]; then
    "$PYTHON_EXE" "$PWD/manager/prepare_portable.py" || {
        echo "ERROR: portable preparation failed."
        exit 1
    }
fi

echo ""
echo "Hifisampler server started."
echo "Logs: $LOG_FILE"
echo "Press Ctrl+C to stop the server."
echo ""

echo "===== Hifisampler server start $(date) =====" >> "$LOG_FILE"
exec "$PYTHON_EXE" "$SERVER_SCRIPT" >> "$LOG_FILE" 2>&1
