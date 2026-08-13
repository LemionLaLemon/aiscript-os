# Fresh-Jail Shell UX: essential packages, cwd, crash-proofing

Fixes for the 10-task fresh-jail test that revealed a broken out-of-box
experience. no cwd, no man/notepad, silent "(went quiet.)", and a context
overflow HTTP 400 that crashed the shell.

## A. Essential tools are vibe packages, installed by default

Linux philosophy: man, notepad, sysinfo, find-big, search-files are ESSENTIAL
system tools shipped as vibe packages in `jail/packages/`. They are installed
by default but the user can `vibe remove`/reinstall them — it's their system.

- New tracked dir `essential/<name>/<name>.as` + `<name>.aconf` for:
  man, notepad, sysinfo, find-big, search-files (sources from backup apps/).
- `scripts/seed_jail.py` installs each essential package into
  `jail/packages/<name>/` (copy .as + .aconf) so the default jail has them.
- Demo seed apps (du-sort, notes, welcome) stay in `aiscript/apps/` -> jail/apps.
- Manpages: new tracked `share/man/` at repo root (aiscript, man, notepad,
  shell, spawn, tools, vibe). seed_jail copies them to `jail/share/man/`.
  - `tools.txt` is the index covering EVERY tool (incl. new cd/pwd).
  - `man.as` falls back to reading tools.txt when a topic has no dedicated page.
- Policy: add "use man when unsure" to daemon/policy.md + interpreter_policy.md
  ("if you don't know how to use a tool, read man <topic> before acting").

## B. Working directory (cwd) — tools only, prompt shows it

- `Session.cwd` (jail-relative, default home/<user>), in to_dict/from_dict.
- New tools `cd(path)` and `pwd()`; implemented in Session._exec_tool
  (mutates cwd), executor stays stateless.
- `Session._resolve(path)`: `.` -> cwd, `~/x` -> home, `/x` -> jail-rel,
  else cwd/x. Applied to path/src/dst args of list/read/write/append/search/
  delete/move/copy/mkdir before executor.
- `run` executes in cwd (subprocess cwd = jail/<cwd>).
- Shell prompt shows cwd: `as/~# ` home, `as/~/Documents# ` after cd.

## C. No more silent "(kernel-2 went quiet.)"

In _loop, empty content + no tool call -> append a nudge ("call a tool or read
man <topic>") and retry once (max 2) before an actionable fallback.

## D. Context overflow must never crash

- model.py.chat: catch HTTP 400 exceed_context_size_error -> ModelError.
- Session._loop: on context-full, auto-compact history (drop oldest
  tool/assistant msgs) and retry once; else "context full — type new".
- _request_messages pre-check: est_tokens > ~6500 -> prune oldest tool results.
- REPL wraps user_turn in try/except so a model error can't kill the shell.

## E. Speed

- History auto-compaction shrinks the huge prefill.
- Trim policy.md (231 -> ~40% shorter) + interpreter_policy.md; both re-prefill
  every turn at ~25ms/token.

## F. Clearer session help

Expand `help` builtin with one-line descriptions of every builtin + session
command; point to man shell.

## Verification

1. Fresh jail -> essential packages installed (man, notepad, sysinfo,
   find-big, search-files) + share/man populated; `vibe list` shows them.
   [DONE - seed_jail installs essential/ into jail/packages/; manpages into
   jail/share/man/]
2. `man man`, `man tools`, `man list` work; `man <unknown>` falls back.
   [DONE - man.as falls back to tools.txt; tools.txt index lists every tool]
3. `ls` lists home; `cd Documents` -> prompt `as/~/Documents#`; `ls` lists
   Documents; `pwd` -> ~/Documents; `cd ~` returns home.
   [DONE - daemon-level test: cd Documents -> now in ~/Documents, list .
   resolves to cwd, pwd -> ~/Documents, cd ~ -> home, cwd persists on save/
   load. Live AI test: model called cd({"path":"Documents"}) correctly]
4. `notepad asmcalc.as` -> write calc -> `run asmcalc.as` works.
   [DONE - notepad resolves from jail/packages; _try_app_spawn spawns it]
5. Long session >8192 tokens compacts/retries instead of 400-crashing.
   [DONE - ContextOverflow raised on 400, _compact_history + retry, and
   _request_messages pre-compacts >7000 est tokens]
6. Unit tests: 21 new cwd/compact tests pass; 22 session + shell session +
   reliability repeat-guard all stay green.

## Post-test bug fix (reported by the user on the live shell)

Two symptoms: (a) "runs out of context and compacts way too quickly", and
(b) "after it finishes responding it's like it's waiting for a timeout before
actually letting you type".

Root cause: the model pads its answers with zero-width spaces (`\u200b`) and
sometimes falls into a degenerate repetition loop. Each `\u200b` is a real
token — the tokenizer counts 2000 of them as 2000 tokens. So:

- the shell streamed hundreds of invisible chars after the answer (symptom b)
- `est_tokens()` (words*1.3) said ~4 tokens while the real count was 2000+,
  so the context silently filled in ~2 turns and the engine 400'd (symptom a)

Fixes in daemon/model.py + daemon/session.py:
- `_strip_invisible()` removes `\u200b`/`\ufeff`/etc from streamed content and
  tool-call args (both streaming and single-shot paths).
- `_detect_repetition()` + `_trim_repetition()` cut the model's repetition
  loop out of the stream and the stored history.
- `est_tokens()` now counts zero-width chars as real tokens; `_compact_history`
  uses it; the pre-compact threshold in `_request_messages` reserves room for
  max_tokens (limit = 8192 - max_tokens - 512).

Verified live over 3 turns: stored_u200b=0, est_tokens=4834 after 3 turns
(previously overflowed at ~2), cd/mkdir both created correct state, no 400.
