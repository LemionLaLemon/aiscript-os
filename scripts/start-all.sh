#!/usr/bin/env bash
# Start the llama-server (the 2B "big brain"). Reads model/port/cores from
# config.toml. The shell, vibe, and spawn all use this one engine.
set -euo pipefail
cd "$(dirname "$0")/.."

PY=$(cat <<'PYEOF'
import tomllib
cfg = tomllib.load(open("config.toml", "rb"))
c = cfg["llama"]
print(f"model={c['model_path']}")
print(f"port={c['port']}")
print(f"mask={c['cpu_mask']}")
print(f"threads={c.get('threads', 4)}")
print(f"slots={c.get('slots', 1)}")
PYEOF
)
eval "$(python3 -c "$PY")"

echo "starting big brain (2B) on port $port, cores $mask"
setsid bash -c "MODEL=$model PORT=$port SLOTS=$slots \
  THREADS=$threads MASK=$mask \
  exec scripts/start-server.sh > /tmp/opencode/llama-server.log 2>&1 < /dev/null &"

sleep 3
for _ in $(seq 1 60); do
  s=$(curl -s --max-time 2 "http://127.0.0.1:$port/health" 2>/dev/null || true)
  [ -n "$s" ] && break
  sleep 2
done
echo "port $port: ${s:-unreachable}"
