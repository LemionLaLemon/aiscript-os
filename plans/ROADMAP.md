# as-os roadmap

Reconstructed from commits, code, and decisions made along the way. Phase 3
was lost to conversation compaction — treat it as undefined until rewritten.

## Phase 1 — Host prototype (DONE)

A working AI-interpreted OS running on Linux with llama.cpp + Qwen3.5-2B.

- `as` shell (`shell/as_shell.py`) with OOBE, chaos, temp/reset builtins
- daemon (`daemon/`) with 13 sandboxed tools and a policy brain
  (`daemon/policy.md`)
- aiscript: a wish-based language interpreted by the AI (no syntax rules)
- `vibe`: package manager that vibecodes wish-style apps into `/packages`
- prompt-cache fix: assistant tool-call messages dropped on the wire so the
  cache survives cross-turn (warm turns ~3–6s, cold first turn ~90s)

Commits: `1e03aa9` (phase 1), `bec9bfe` (two-tier + cache fix),
`02b8ad9` (single-brain 2B), `0c89f89` (REPL fixes), `277e50c`
(vibecoded apps actually run).

## Phase 2 — 2B tool-UX polish (current)

See `plans/PHASE-2-tool-ux.md`. Sharpen the tool surface so the 2B brain
succeeds more consistently, and write a README so it can be run and used.

## Phase 3 — (undefined)

Lost to compaction. Define it and write it down here before relying on it.

## Phase 4 — OS image + framebuffer

`asui/fb.py` reserves this: a framebuffer backend for the OS image
(`image/overlay/`). Terminal backend ships first.

## Language decision

The control plane (daemon, tools, vibecoder, runner, asui) stays in Python.

Rationale (measured on this laptop):
- inference: llama-server (C++) 6.1 GB RSS, one call 3–15s
- control plane: tool calls ~0.2 ms, calc ~6 µs, shell process ~37 MB RSS
- Python is ~0.1% of latency and ~0.6% of RAM; the model dwarfs it

Port trigger (revisit before Phase 4):
- control-plane CPU time ever competes with inference time, OR
- a target image where the Python runtime (~50 MB) matters next to the
  model+KV footprint (~1.3 GB+), OR
- iteration slows us down enough that a port pays for itself
