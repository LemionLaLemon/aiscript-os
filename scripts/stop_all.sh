#!/usr/bin/env bash
# Stop all as-os processes (llama-server, shell, daemon).
set -euo pipefail

echo "stopping as-os processes..."

# Kill all llama-server processes started by this project
killed=0
for pid in $(pgrep -f "llama-server.*--port" 2>/dev/null || true); do
    cmd=$(ps -p $pid -o args= 2>/dev/null || true)
    if echo "$cmd" | grep -q "llama-server"; then
        echo "killing llama-server (pid $pid)"
        kill $pid 2>/dev/null || true
        killed=$((killed + 1))
    fi
done

# Kill any python3 as_shell.py processes
for pid in $(pgrep -f "as_shell.py" 2>/dev/null || true); do
    echo "killing as_shell.py (pid $pid)"
    kill $pid 2>/dev/null || true
    killed=$((killed + 1))
done

# Kill any python3 daemon processes (if running separately)
for pid in $(pgrep -f "python3.*daemon" 2>/dev/null || true); do
    cmd=$(ps -p $pid -o args= 2>/dev/null || true)
    if echo "$cmd" | grep -q "daemon"; then
        echo "killing daemon (pid $pid)"
        kill $pid 2>/dev/null || true
        killed=$((killed + 1))
    fi
done

if [ $killed -eq 0 ]; then
    echo "no as-os processes found"
else
    sleep 1
    echo "stopped $killed process(es)"
fi
