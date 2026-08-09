#!/usr/bin/env bash
# Start llama-server with the as-os model.
# Uses only the physical P-cores (this laptop: 4P + 4E), which measured fastest.
set -euo pipefail
cd "$(dirname "$0")/.."

BIN=tools/llama.cpp/llama-b10333
MODEL=${MODEL:-models/Qwen3.5-2B-Q4_K_M.gguf}
PORT=${PORT:-8080}
CTX=${CTX:-8192}        # context PER SLOT
THREADS=${THREADS:-4}
SLOTS=${SLOTS:-4}
MASK=${MASK:-0,2,4,6}

# llama-server splits -c across --parallel slots, so pass the total.
TOTAL_CTX=$((CTX * SLOTS))

exec taskset -c "$MASK" env LD_LIBRARY_PATH="$BIN" "$BIN/llama-server" \
  -m "$MODEL" \
  -c "$TOTAL_CTX" \
  -t "$THREADS" \
  --parallel "$SLOTS" \
  -ctk q8_0 -ctv q8_0 \
  --cache-prompt --cache-reuse 64 \
  -rea off \
  --host 127.0.0.1 \
  --port "$PORT" \
  --temp 0.15 \
  --no-webui \
  --log-disable
