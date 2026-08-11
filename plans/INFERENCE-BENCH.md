# Inference Optimization Bench — Results

Goal: find the fastest llama.cpp config for LFM2.5-8B-A1B on this i5-13420H.
Tested: speculative decoding (2 draft models) + flash attention.

## Verdict: keep the current production config — no changes

| Config | Effective tok/s (1000-tok completion avg) |
|--------|-------------------------------------------|
| Baseline (prod flags: cache-prompt, rea off) | **16.4** |
| Spec decode + LFM2.5-1.2B-Instruct draft (n-max 6) | 16.6 |
| Spec decode + LFM2.5-1.2B-Thinking draft (n-max 6) | 16.7 |
| Flash attention (`-fa on`) | ~18 (512-tok; noisy) |

## Findings

- **Speculative decoding: no gain.** The 8B-A1B is a MoE with ~1B *active*
  params (17 tok/s standalone). A 1.2B dense draft decodes at only 18.7 tok/s
  standalone — not fast enough to offset the CPU/bandwidth contention of
  running both models. All spec variants converge to the same ~16.4-16.7 tok/s.
- **Flash attention: no gain.** FA is a GPU optimization; on this CPU it is
  neutral-to-slower.
- **Batch-thread split (-t 4 -tb 8): no gain.** Decode is bandwidth-bound,
  not compute-bound; extra prefill threads don't speed decode.
- **KV cache q4_0: no gain.** Flat on short prompts; only helps at very long
  context where KV traffic dominates (not the shell's profile).
- **Fresh GGML_NATIVE build: no gain.** Built the same source (0865990) with
  -march=native for this CPU; the b10333 dispatch build was already optimal
  (alderlake lib). 15.7 vs 16.4 tok/s — within noise.
- **Measurement trap:** a 512-token completion overstates tok/s (warm cache +
  startup effects). 1000-token completions give the stable number (~16.4).
- **The earlier "spec decode 52% faster" claim was an artifact** of comparing
  a cold no-cache server against a cached spec server. With production flags
  both converge to the same rate.

## Verdict

~16-18 tok/s is the practical ceiling for the 8B-A1B on this i5-13420H.
Decode is memory-latency bound for the scattered MoE expert reads — NOT
bandwidth-bound, NOT power-bound, NOT thread-limited. This was verified by
elimination (see below).

## Root cause (corrected, round 3)

Memory hardware verified: **2x 8GB DDR5-4800 dual-channel (Kingston + Samsung)**,
~77 GB/s theoretical, ~50 GB/s realistic. At 16-17 tok/s x ~670MB/token active
the *effective* bandwidth used is ~11 GB/s — only ~20% of realistic. So the
machine is NOT bandwidth-saturated.

What actually limits decode:
- **~19W power draw** during inference (measured via RAPL energy_uj) — far
  below the 45W PL1. CPU is voluntarily at 3.0GHz, stalled waiting on DRAM.
- **Thread sweep flat**: -t 8 (all P+E) = 17.0, -t 12 (all) = 15.1 (worse,
  HT contention). Not latency-hiding limited.
- **PL1 raised 45W->75W: flat.** CPU still 3.0GHz. Not power-limited.
- **mlock: flat.** Model already resident; not page-cache misses.
- **Start-of-run burst:** llama-server's tg_3s shows ~35 tok/s for the first
  ~400 tokens (experts hot in cache), then settles to ~17 tok/s cold DRAM
  latency. That 35 t/s burst is why the original bench rows report 33.7.

Conclusion: the 8B-A1B's active ~1B experts are read via scattered/random
access each token. Random DRAM access latency at ~3GHz with 4 P-cores caps
decode at ~17 tok/s. No server flag, thread count, power limit, or rebuild
changes this — it's the memory-access pattern.

The remaining lever is perceived latency: cutting LFM's reasoning-token burn
via the prompt (the "Think less. Act now." policy) helps time-to-first-answer
more than any inference knob. (PL1 was restored to the 45W firmware default.)

## Downloads

- `models/LFM2.5-1.2B-Instruct-Q4_K_M.gguf` (731MB) — vocab-matched, works with `-md`
- `models/LFM2.5-1.2B-Thinking-Q4_K_M.gguf` (731MB) — vocab-matched, works with `-md`

Both left on disk but NOT enabled in start-server.sh. Can be removed to free
~1.5GB, or kept for future experiments.

## Secondary findings (quality gate)

Run with the production-flag server via `bench_tools.py --prompt daemon`
(tool quality) + `reliability.py` (answer quality):

- Tool quality: **4/4** (after fixing bench scoring: "plain chat no tools"
  correctly NOT calling a tool now counts as pass).
- Reliability live cases: **five/ten/total FAIL** — the model answers
  "~/Downloads is empty" because it uses `run("ls ~/Downloads")`, and the
  shell `run()` tool sets HOME=jail so `~` = `jail/Downloads` (nonexistent),
  not `jail/home/demo/Downloads`. Prompt gap: policy.md says `~` = user home
  but the shell run() env disagrees.
- Reliability guard: **FAIL** — pre-existing harness bug: `FakeExec.execute()`
  doesn't accept the `chrooted=` kwarg Session passes, so every tool call
  errors (`executed=0`). Unrelated to inference.

## Tooling added

- `scripts/bench-server.sh start|stop PORT [--draft G [--spec-n-max N]]` —
  start/stop a bench server with production flags, one config at a time.
- `bench/one_config.py` — full quality+speed driver (start → quality → speed → csv).
- `bench_tools.py` fix: `build_system_prompt` → `build_shell_prompt` import.
- `bench_tools.py` scoring fix: "no tools" task passes when the model does
  NOT call a tool.

## Follow-ups (from quality gate)

1. Fix shell `run()` `~` expansion so `~` = user home (interpreter layer is
   already chrooted with HOME=/home; shell layer run() uses cwd=jail,
   HOME=jail). Either set HOME to the user home in shell run(), or update
   policy.md to tell the model to use `list`/`read` tools (not run ls ~).
2. Fix reliability harness FakeExec signature.
3. Optional: remove the 2 unused 1.2B draft GGUFs to reclaim ~1.5GB.
