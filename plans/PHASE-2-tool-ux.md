# Phase 2 — 2B tool-UX polish

Status: approved, in progress. Goal: make the tool surface reliable enough
that the 2B brain (Qwen3.5-2B) succeeds consistently, and make the system
usable by a human (README).

## Why

Observed failure modes on the 2B:

- **"5 biggest + total size" task fails** — model called `calc` three times
  without listing first, spiraled, gave up (0/5 files named). Root cause:
  `list` returned human-rounded sizes (`180.0K` for `184312`), so sums were
  approximate and untrustworthy.
- **Same-tool repeats** (`calc`×3) burn loops and trip the budget.
- **No README** — the user has only observed logs; cannot run or use it.

Non-issues (measured): truncation is not a real problem in recent tests
(5/5 and 10/10 files named on complete answers); drop finish_reason work.

## Workstream B — tool changes

1. **`list` returns exact bytes.** No tool-side human formatting. The
   interpreter decides how to render `184312` (184K, 180K, bare number, or
   not at all). Fixes total-size/compare tasks.
2. **`[N entries]` count header** as the first line of list results, so the
   model knows exactly how many entries it holds.
3. **Repeat-guard generalization** in `daemon/session.py`: steer when the
   same tool is called N times with the same/near-identical args (kills the
   `calc×3` spiral), not just exact duplicates.
4. **Policy steerage** in `daemon/policy.md`: sizes come from `list` (never
   `du`/`ls`/`cat`), one structured tool at a time.

## Workstream A — README

`README.md` at repo root: what as-os is, the fiction, hardware, build/run,
usage (OOBE, `as#` builtins, natural-language tasks, vibe/spawn), tools,
troubleshooting.

## Bench harness

Extend `bench/` with a reliability battery (fresh session):

- "list the 5 biggest files in Downloads, name all five" -> 5/5
- "list the 10 biggest, name all ten" -> 10/10
- "list the 5 biggest and give their total size" -> correct total
- repeat-spiral check (same tool N× -> steered, not looped)

Measure before and after the tool changes; keep as regression gate.

## Out of scope

- Truncation handling (dropped by decision)
- Language port (see ROADMAP.md; stay Python)
- Phase 3/4 work
