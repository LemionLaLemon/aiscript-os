#!/usr/bin/env bash
# Start the as-os shell (llama-server + as_shell.py in one command).
set -euo pipefail
cd "$(dirname "$0")/.."

PORT=${PORT:-8080}

# Kill any existing llama-server on this port
existing=$(lsof -ti:$PORT 2>/dev/null || true)
if [ -n "$existing" ]; then
    echo "killing existing llama-server on port $PORT (pid $existing)"
    kill $existing 2>/dev/null || true
    sleep 2
fi

# Start llama-server in background
echo "starting llama-server on port $PORT..."
./scripts/start-server.sh &
LLAMA_PID=$!

# Wait for health
echo "waiting for llama-server..."
for i in $(seq 1 60); do
    if curl -s --max-time 2 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
        echo "llama-server ready"
        break
    fi
    sleep 2
done

# Check health one more time
if ! curl -s --max-time 2 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
    echo "ERROR: llama-server failed to start on port $PORT"
    kill $LLAMA_PID 2>/dev/null || true
    exit 1
fi

# Launch the shell
echo "launching as# shell..."
python3 shell/as_shell.py

# Clean up llama-server when shell exits
echo "shell exited — stopping llama-server..."
kill $LLAMA_PID 2>/dev/null || true
wait $LLAMA_PID 2>/dev/null || true
echo "done."
