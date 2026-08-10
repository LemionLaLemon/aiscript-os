# Plan: bench LFM 8B vs Qwen 3.5-4B + save benchmarks

## Goal
- Determine if LFM's tool-calling failures are prompt-fixable (safety refusal
  overridable by policy.md) or a hard safety ceiling.
- Save all bench data to `benchmarks/results.csv` so they never need re-benching.
- Re-bench LFM after a policy fix to see if it improves on read/run.

## Key findings (prior run)
- **LFM 8B**: bench_tools 1/4 (read/run refused as safety), reliability 3/4,
  decode 27.7 tok/s (fastest).
- **Qwen 3.5-4B**: bench_tools 3/4, reliability 4/4, decode 13.1 tok/s.
- **Qwen 3.5-2B** (baseline): bench_tools 2/4, reliability 4/4, decode 23 tok/s.
- **iGPU**: works (97% util confirmed) but 2-7x slower than CPU — dead end.

## Step 1: write plan to plans/BENCH-LFM-VS-4B.md ← done (this file)

## Step 2: create `benchmarks/results.csv` (hand-written, current data)

Schema:
```
date,model,build,backend,temp,bench_tools_raw,bench_tools_valid,reliability,rel_five,rel_ten,rel_total,rel_guard,prefill_tokps,decode_tokps,notes
```

Rows: 2B, 4B, LFM-pre-fix, LFM-iGPU, Qwen-iGPU (no re-runs needed).

## Step 3: edit `daemon/policy.md` — tool-use mandate

Target: lines 104-131 ("## Tools" section). Add/rewrite:

1. Insert at the top of "## Tools":
   - Tools are yours, sandboxed, safe — nothing to refuse.
   - When a task needs read/run/write, use them. Refusal is failure.
2. Soften "Be sparing with run()" → "run() is fine when you need it;
   structured tools are usually faster and preferred."
3. Keep all existing tool descriptions unchanged.

## Step 4: extract `build_system_prompt()` from server.py → daemon/prompt.py

Refactor: move system_prompt logic from server.py to daemon/prompt.py.
Both server.py and bench_tools.py import from there.

## Step 5: add `--csv PATH` + `--prompt daemon` to bench/bench_tools.py

- `--csv PATH` appends one row after all tasks.
- `--prompt daemon` loads the real policy.md prompt (via build_system_prompt)
  instead of the minimal "You are the OS" stub.

## Step 6: add `--csv PATH` to bench/reliability.py

Appends one row with reliability scores + guard result.

## Step 7: re-bench LFM 8B (CPU, 8081)

After policy edit, restart LFM on CPU and run:
1. Quick ad-hoc read + run test (definitive refusal test).
2. `bench/bench_tools.py --port 8081 --prompt daemon --csv benchmarks/results.csv`
3. `bench/reliability.py --port 8081 --csv benchmarks/results.csv`

## Step 8: commit everything + report
