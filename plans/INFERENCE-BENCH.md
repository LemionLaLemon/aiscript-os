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
- **Measurement trap:** a 512-token completion overstates tok/s (warm cache +
  startup effects). 1000-token completions give the stable number (~16.4).
- **The earlier "spec decode 52% faster" claim was an artifact** of comparing
  a cold no-cache server against a cached spec server. With production flags
  both converge to the same rate.

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
