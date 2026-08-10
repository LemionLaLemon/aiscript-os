# Vibe + App Ecosystem Overhaul

Goal: Make vibe produce real working apps, add interactive stdin/display to the interpreter layer, preload useful utilities, and fix the OOBE so first boot is smooth.

## A. Vibe overhaul (`aiscript/vibe.py`)

- `max_tokens` 600 → 4096 (per-generation cap; push to 6144 if still truncated)
- `time_budget` 420s → 600s
- Move sub-session to interpreter layer: `layer="interpreter"`, tools = INTERPRETER_TOOLS minus ask/draw/shutdown (non-interactive vibecoding). Drop `_vibe_tools()`.
- Harden `VIBE_TASK`: add a "BAD" example (the current probe/fastfetch Python garbage — `def main()`, `args = {}`, `import sys`, `print(`) marked as rejected, forbid them outright.
- Post-validator: scan the produced `.as` for syntax markers (`def `, `import `, `args = {`, `for .* in .*:`, `print(`, `sys.`); if found, delete the dir and return a clear error (auto-retry once first).

## B. Sub-session token + tool rework (`daemon/tools.py`, `daemon/server.py`)

- `INTERPRETER_TOOLS` += `ask` + `draw` (interactive stdin/display for the deep layer; handlers already wired in as_shell.py).
- `interpret()`: `max_tokens` 400 → 2048.
- `spawn()`: `max_tokens` 400 → 2048, `max_loops` 4 → 32, `time_budget` 160 → 600s.
- Delete dead `_sub_tools()`.

## C. Interactive notepad (`jail/apps/notepad.as`)

Hand-written plain-language app. Opens a file, shows the buffer, then loops: ask the user what to change and at which line, apply via read/write/append, re-show, repeat until done.

## D. Preloaded utilities (`jail/apps/`)

Hand-written: `sysinfo.as` (calls `info`), `find-big.as`, `search-files.as` (calls `search`).
`notes.ais`/`welcome.ais` start working once `draw` is in the interpreter toolset.
Remove broken vibecoded packages: fastfetch, probe.

## E. OOBE prompt rewrite (`daemon/oobe.py`)

Keep the LLM-driven OOBE but rewrite `OOBE_PROMPT` to be a structured, step-by-step task that prevents circular asks and ensures each step completes before the next.

Steps the prompt must enforce:
1. Greet warmly (one sentence, house style).
2. Ask for a username (required, no defaults). Validate with `_handle_create_user`.
3. Ask for chaos level — offer 3 choices (calm / balanced / chaotic). Pick the number from their choice.
4. Ask for machine name (optional, default "lemion").
5. Write `.asrc` with temp, chaos_p, machine_name.
6. Say goodbye. Do NOT ask anything else after step 5.

Key constraint: each question is asked exactly ONCE. Never repeat a question. Never ask open-ended questions beyond the 4 above. Never ask "which apps" — default is all preloaded.

## F. Overthinking policy (`daemon/policy.md`)

Add a "Think less. Act now." section:
- If a request maps directly to a tool, call it in your first tool round.
- Never deliberate about tool availability, what the user "really" meant, or how to rephrase.
- `ls`/`list`/`show files`/`show me X` = `list(path)`, call it immediately.
- Overthinking is a failure mode; acting is the goal.

## G. Thinking UI (`shell/as_shell.py`)

- Vibe renders magenta automatically (now `layer="interpreter"`).
- Add `[vibe: vibecoding <pkg>…]` status line in `_sub_event`.
- Fix spinner/ask interaction so notepad's `? prompt` isn't clobbered.

## H. Shell UX (`shell/as_shell.py`)

- Enable readline history (arrow keys work).
- Add builtins: `apps` (list jail/apps + jail/packages), `pkgs` (vibe list).

## Verification

1. First boot → OOBE creates user, writes .asrc, no circular asks.
2. `spawn notepad` → interactive edit loop works.
3. `vibe install <x>` → prose `.as` + valid `.aconf` in /packages.
4. `spawn sysinfo/find-big/search-files` → real output.
5. Shell responds to "ls" with a single `list` call, minimal reasoning.
