# Spike — LFM2.5-8B-A1B on the i5-13420H (CPU + iGPU)

Status: approved, in progress. Decision-gated: no default-switch without
passing Gate A.

## Why

The Qwen3.5-2B is the reliability bottleneck (ask-loops, forgotten files,
failed sums). LFM2.5-8B-A1B is purpose-built for on-device agents: 8.3B
total / 1.5B active, 128K ctx, 24 layers (18 conv + 6 attention -> tiny KV),
IFEval 91.84 (matches Gemma-4-26B-A4B-IT). Day-one llama.cpp/GGUF.

## Hardware ground truth (measured)

- iGPU: Intel UHD Raptor Lake-P, 48 EU, i915 driver.
- Vulkan toolchain already installed: ANV `intel_icd`, `glslc`, `shaderc`,
  `vulkan-icd-loader`, mesa 26.1.6. oneAPI also present (SYCL alt).
- Current `tools/llama.cpp/llama-b10333` is a CPU-only build; GPU needs a
  rebuild. 378GB disk free; huggingface.co reachable.
- Caveat: on a 48EU iGPU sharing DDR5, decode is bandwidth-bound (~= CPU);
  prefill may improve. Measure, don't assume.

## Phase 0 — prep (parallel)

1. Download `LiquidAI/LFM2.5-8B-A1B-GGUF` Q4_K_M (~4.7GB) -> `models/`.
2. Rebuild llama.cpp with `-DGGML_VULKAN=ON` into a NEW build dir (keep the
   CPU build untouched). ggml needs glslc/shaderc (present).

## Phase 1 — CPU viability (backend-independent, make-or-break)

- llama-server on port 8081, LFM GGUF, sampling per Liquid:
  `--temp 0.2 --top-k 80 --repeat-penalty 1.05 -c 8192 --parallel 4`.
  2B stays on 8080.
- 1a: `bench/bench_tools.py` at 8081 -> does `/v1/chat/completions` return
  real `tool_calls`? LFM natively emits `<|tool_call_start|>` markers; if
  llama-server doesn't map them, fall back to a marker->tool parser in
  `daemon/model.py`.
- 1b: cold-turn latency (policy-sized ~2K prompt), warm-turn (prompt cache),
  decode tok/s.
- 1c: reliability battery `bench/reliability.py` against 8081.

Gate A (go/no-go): tool calls resolve AND battery >= current
(5/5, 10/10, total, guard = all PASS). No-go -> stay 2B, write results here.

## Phase 2 — iGPU speed

- Same run on 8081 from the Vulkan build with `-ngl 999`. Compare tok/s,
  cold prefill, warm first-token vs CPU. Flaky/slower -> default CPU.

## Phase 3 — switch (only if Gate A passed)

- Default = LFM on Vulkan/iGPU if faster, else LFM on CPU build.
- Edits: `config.toml` (model_path/model_name), `start-server.sh`
  (sampling flags, CoT/reasoning handling), possible marker parser; keep the
  Qwen 2B GGUF as a one-line fallback profile.
- RAM: one engine at a time (stop 8080 before loading LFM).
- Record results in this file + `plans/ROADMAP.md`.

## Results (fill in)

- Gate A: NO-GO - stay on Qwen3.5-2B. Details below.
- Tool calls: PASS - llama-server maps LFM `<|tool_call_start|>` to real
  `tool_calls` (bench_tools 2/4; 2 fails were harness artifacts: minimal
  system prompt, no-description tools, "hello" needs no tool). No parser
  needed.
- Cold: 108s (CPU). Warm: 42-70s (CPU) - CONV LAYERS HAVE NO KV CACHE, so
  each turn re-prefills ~75% of the conversation. 2B warm was ~13s.
- Reliability battery (8081, temp 0.2/top-k 80/repeat-penalty 1.05):
  "ten" PASS (exact files+sizes), "total" PASS (exact 621,306),
  "five" FAIL once (listed a filtered 4-small-file subset, not top-5 by
  size) then PASS 3/3 on rerun. Guard PASS. So 3/4 vs the 2B's 4/4, with
  MORE variance in tool-arg selection. No demonstrated reliability win.
- iGPU: FAIL. lfm2moe tensors tag layer=0 (likely not offloadable in
  b10333), and llama.cpp's Vulkan backend + mesa ANV driver hangs
  intermittently on device init (Qwen ngl=999 and later LFM ngl=999 both
  hang; 3/3 retries dead). Not a stable engine path on this box. SYCL is
  an alternative but a multi-hour build with no guarantee.
- Decision: NO-GO. LFM is benchmark-better but on this i5 it is not
  faster, not clearly more reliable, and warm turns get 3-5x worse
  (conv-layer prefill). iGPU unstable. Keep 2B.
- Suggested middle ground (not tested): Qwen3.5-4B is dense attention, so
  the prompt cache still works (warm turns stay fast) and quality is above
  2B. Swap is one line in config.toml; config comment quotes ~6.5 tok/s.
  Worth a 20-min battery run before any 2B-replacement decision.
