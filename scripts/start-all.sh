#!/usr/bin/env bash
# Start BOTH llama-servers: the big brain (2B, P-cores) and the fast tier
# (0.8B, E-cores). Reads model/port/cores from config.toml.
set -euo pipefail
cd "$(dirname "$0")/.."

PY=$(cat <<'PYEOF'
import tomllib
cfg = tomllib.load(open("config.toml", "rb"))
for k in ("llama", "fast"):
    c = cfg[k]
    print(f"{k}_model={c['model_path']}")
    print(f"{k}_port={c['port']}")
    print(f"{k}_mask={c['cpu_mask']}")
    print(f"{k}_threads={c.get('threads', 4)}")
    print(f"{k}_slots={c.get('slots', 1)}")
PYEOF
)
eval "$(python3 -c "$PY")"

echo "starting big brain (2B) on port $llama_port, cores $llama_mask"
setsid bash -c "MODEL=$llama_model PORT=$llama_port SLOTS=$llama_slots \
  THREADS=$llama_threads MASK=$llama_mask \
  exec scripts/start-server.sh > /tmp/opencode/llama-server.log 2>&1 < /dev/null &"

echo "starting fast tier (0.8B) on port $fast_port, cores $fast_mask"
setsid bash -c "MODEL=$fast_model PORT=$fast_port SLOTS=$fast_slots \
  THREADS=$fast_threads MASK=$fast_mask \
  exec scripts/start-server.sh > /tmp/opencode/fast-server.log 2>&1 < /dev/null &"

sleep 3
for p in "$llama_port" "$fast_port"; do
  for _ in $(seq 1 60); do
    s=$(curl -s --max-time 2 "http://127.0.0.1:$p/health" 2>/dev/null || true)
    [ -n "$s" ] && break
    sleep 2
  done
  echo "port $p: ${s:-unreachable}"
done
