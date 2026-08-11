#!/usr/bin/env bash
# Start the as-os shell (llama-server + as_shell.py in one command).
cd "$(dirname "$0")/.."

PORT=${PORT:-8080}

# Kill any existing llama-server on this port
pkill -f "llama-server.*--port $PORT" 2>/dev/null && sleep 2 || true

# Start llama-server in background
echo "starting llama-server on port $PORT..."
./scripts/start-server.sh &
LLAMA_PID=$!
trap "kill $LLAMA_PID 2>/dev/null; wait $LLAMA_PID 2>/dev/null" EXIT

# Wait for health
echo "waiting for llama-server..."
for i in $(seq 1 60); do
    if curl -s --max-time 2 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
        echo "llama-server ready (pid $LLAMA_PID)"
        break
    fi
    sleep 2
done

# Verify health one final time
if ! curl -s --max-time 2 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
    echo "ERROR: llama-server failed to start on port $PORT"
    exit 1
fi

# Give the server time to fully initialize (KV cache, backend warm-up).
# The daemon also retries its ping, so this is belt-and-braces.
sleep 2

# Launch the shell
echo "launching as# shell..."
python3 shell/as_shell.py
