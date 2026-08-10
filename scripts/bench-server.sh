#!/usr/bin/env bash
# Start a llama-server with a given config (detached). Usage:
#   scripts/bench-server.sh start <port> [--draft <gguf>] [--spec-n-max N]
#   scripts/bench-server.sh stop <port>
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BIN="$ROOT/tools/llama.cpp/llama-b10333"
MODEL="${MODEL:-models/LFM2.5-8B-A1B-Q4_K_M.gguf}"

action="$1"; shift
PORT="$1"; shift

case "$action" in
  start)
    cmd=(taskset -c 0,2,4,6 env "LD_LIBRARY_PATH=$BIN" "$BIN/llama-server"
         -m "$ROOT/$MODEL" -c 8192 -t 4 --parallel 1
         -ctk q8_0 -ctv q8_0 --host 127.0.0.1 --port "$PORT"
         --cache-prompt --cache-reuse 64 -rea off
         --temp 0.2 --top-k 80 --repeat-penalty 1.05
         --no-webui --log-disable)
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --draft) cmd+=(-md "$ROOT/$2"); shift 2;;
        --spec-n-max) cmd+=(--spec-draft-n-max "$2"); shift 2;;
        *) shift;;
      esac
    done
    setsid nohup "${cmd[@]}" >/tmp/asbench_$PORT.log 2>&1 < /dev/null &
    disown
    echo "started on :$PORT (pid $!)"
    ;;
  stop)
    # kill the llama-server bound to this port
    for pid in $(ss -tlnp 2>/dev/null | grep ":$PORT " | grep -oP 'pid=\K[0-9]+' | sort -u); do
      kill -9 "$pid" 2>/dev/null
    done
    echo "stopped :$PORT"
    ;;
  *)
    echo "usage: bench-server.sh {start|stop} PORT [--draft G [--spec-n-max N]]"
    exit 1
    ;;
esac
