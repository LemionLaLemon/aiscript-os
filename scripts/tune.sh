#!/usr/bin/env bash
# Tune this laptop for as-os inference: latency-focused CPU profile and a
# higher sustained power limit (PL1) so llama.cpp can boost.
# Run as root (sudo ./scripts/tune.sh).
set -euo pipefail

echo "[tune] setting tuned profile to latency-performance"
tuned-adm profile latency-performance || true

# PL1: i5-13420H base TDP is 45W; laptops default to a lower cap (this one was 30W).
rapl=/sys/class/powercap/intel-rapl:0/constraint_0_power_limit_uw
if [ -w "$rapl" ]; then
  echo "[tune] raising PL1 to 45W"
  echo 45000000 > "$rapl"
  echo "       now: $(( $(cat "$rapl") / 1000000 ))W"
else
  echo "[tune] $rapl not writable; skipping power limit"
fi

echo "[tune] done. verify with: tuned-adm active"
