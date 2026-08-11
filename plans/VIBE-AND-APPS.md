# Vibe + App Ecosystem + OOBE — Remaining Work

Goal: Fix OOBE live-test failures, make shell recognize apps, rework vibe .as format (code allowed), add man utility, and delimit all system prompts.

## A. Fix the OOBE (root cause: create_user has no tool schema)

**Root cause:** `ToolExecutor.create_user()` exists (tools.py:816) and the handler is wired (server.py:31), but there is **no JSON schema** for it in `_SHELL_TOOL_SCHEMAS`. The OOBE prompt tells the model to call create_user; the model cannot. It stalls, re-asks the username, and the fallback `oobe.py:75` blindly creates `user`.

- **A1.** Add `create_user` schema to `_SHELL_TOOL_SCHEMAS` (username required, password optional). `OOBE_TOOL_NAMES` already lists it → OOBE toolset picks it up. The schema also appears in normal shell sessions (harmless).
- **A2.** Add `Session.keep_tool_msgs` flag (default False). When True, assistant tool-call messages are NOT dropped from `_request_messages`. OOBE sets it True so the model sees its own prior ask/create_user calls, not just the results. Cache cost irrelevant for one-time OOBE.
- **A3.** Smarter fallback: if create_user still never runs, scan session messages for the last `[ask]` result and extract the username from it. Fall back to `"user"` only if nothing usable found.

## B. Shell doesn't recognize apps ("notes" not spawnable)

- **B1.** `prompt.py build_shell_prompt`: inject live installed apps + packages from `jail/apps/` and `jail/packages/` into the prompt. Format: `Installed apps: notepad, sysinfo, find-big, search-files, notes, du-sort, welcome. Installed packages: cowsay (if present).` Computed at session creation; reflects what's actually installed.
- **B2.** `policy.md`: add rule — "When the user types a bare word that matches an installed app or package (e.g. 'notes', 'cowsay', 'sysinfo'), run it: call `spawn(app='<name>')`. Do not deliberate — just spawn."

## C. vibe .as two-section format (code now allowed)

The user's format spec:
- **System prompt section (required):** `# <name>: <general description>` + optional extra prose.
- **`--- program ---` section (optional):** assets or real logic/code. The interpreter layer reads and executes it, so code is fine and encouraged when the package needs real behavior.

- **C1.** Rewrite `VIBE_TASK` to teach the two-section format with a **complete cowsay example including the cow ASCII art + actual logic** in the program section. Explicitly state code is allowed and encouraged.
- **C2.** Pass `system_prompt=VIBE_TASK.format(target=target)` to the vibe sub-session (currently defaults to the shell personality kernel-2 prompt, which is wrong context for vibecoding).
- **C3.** Validator rework: **drop the code-syntax rejection** (obsolete). Require: (a) `# <name>:` header line, (b) non-trivial body (≥3 non-empty lines or a `--- program ---` section) to catch stubs. Keep the networking warning.
- **C4.** `runner.py`: note in the wrapper that content after `--- program ---` is the program's logic/assets to use when executing.

## D. `man` shell utility (an app, not a builtin)

- **D1.** `jail/apps/man.as` — given a topic argument (e.g. `man vibe`), reads `/share/man/<topic>.txt` and shows it. No topic → lists all manuals and asks which to read. Uses interpreter tools (read, list, ask).
- **D2.** `jail/share/man/` directories with `.txt` manuals:
  - `aiscript` — what aiscript is, .as two-section format, examples
  - `tools` — every shell + interpreter tool with description + optional flags/params
  - `vibe` — package manager usage (install/remove/list/update), flags, format notes
  - `spawn` — running apps
  - `notepad` — interactive editor usage
  - `shell` — builtins (help, status, apps, pkgs, chaos, temp, reset, exit)
  - `man` — how to use man itself
- **D3.** `policy.md`: "When you're unsure how to do something, or the user asks for help/usage, call `spawn(app='man', args=['<topic>'])`."
- Note: `jail/` is gitignored; these live on-disk like the other preloaded apps.

## E. System prompt delimiters

Add `-- START SYSTEM PROMPT --` / `-- END SYSTEM PROMPT --` to every system prompt to prevent the model from confusing system instructions with user messages:

- **E1.** `prompt.py`: wrap both `build_shell_prompt` and `build_interpreter_prompt` output.
- **E2.** `OOBE_PROMPT` (oobe.py): wrap (it's passed as `system` role).
- **E3.** `VIBE_TASK` (vibe.py): wrap (becomes the vibe sub-session's system prompt after C2).

## F. Fix latent bench import bug

`bench/bench_tools.py:81`: `from daemon.prompt import build_system_prompt` → `build_shell_prompt`. The old name no longer exists.

## G. Reasoning discipline (cut thinking on ACTION prompts only)

The user's feedback: even after the "Think less. Act now." clause, the model
still over-thinks on **action-oriented** prompts:
- `vibe install <x>` — should be a single `vibe` tool call, but it deliberates.
- delegating to the interpreter — it's *scared* to call `interpret()` when the
  structured tools can't do the task, instead of delegating immediately.
- it spends reasoning tokens analyzing what tool to use / whether it's allowed.

But thinking on **question-oriented** prompts is fine and should be preserved
(e.g. "why is CRD a valid injection path at Columbia Generating Station" — the
model should reason about that answer).

Rules to add to `policy.md`:
- **Action prompts (do/something/install/run/fix):** the request maps to one
  tool → call it in the first tool round, NO deliberation. If the structured
  tools can't do it, `interpret()` it immediately — do not weigh whether
  delegating is "allowed" or "safe". The interpreter exists precisely for
  this. Never reason about tool availability or permission.
- **Question prompts (explain/why/how/what-is):** reasoning is welcome and
  expected. Think, then answer.
- How to tell them apart: a request that ends in an action (a verb that makes
  the machine do something) is an action prompt. A request that ends in an
  answer (why/explain/describe) is a question prompt.
- Add the same discipline to `interpreter_policy.md`: when given a wish,
  carry it out with the fewest steps — no meta-commentary about the sandbox,
  no "let me think about the best approach" preambles.

## Verification

1. Delete `jail/etc/as-os/configured` → OOBE asks username once, creates that user with that name, writes `.asrc` — no `user` fallback.
2. Type `notes` in the shell → shell recognizes it as an app → spawns notes.
3. `vibe install cowsay` → `.as` has header + `--- program ---` with cow art/logic; `spawn cowsay` → cow says a message.
4. `man vibe` → shows vibe manual with tool descriptions + flags.
5. `pkgs` → shows actually-installed packages (e.g. cowsay).
6. OOBE prompt has `-- START SYSTEM PROMPT --` / `-- END SYSTEM PROMPT --` delimiters visible to the model.
7. `vibe install cowsay` → a single `vibe` tool call, minimal reasoning.
8. A task the structured tools can't do (e.g. "count all .iso files in ~/Downloads" needs grep/find) → shell calls `interpret()` immediately.
9. "why is CRD a valid injection path" → model reasons and gives a proper answer, no premature tool call.
