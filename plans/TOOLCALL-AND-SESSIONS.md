# Tool-call Reinforcement + Session Management

Goal: fix the root cause of LFM writing tool calls as text/JSON instead of
emitting structured tool_calls (via `tool_choice`), and add full AI-tool-style
session management to the shell.

## Part 1 — Reinforce tool calling with `tool_choice`

The OpenAI-compatible API in this llama.cpp build supports `tool_choice`
(`"auto"` / `"required"`, verified at server-chat.cpp:554 + common-chat.cpp:344).
We never send it, so the model is free to answer in prose or emit JSON blobs.

- `daemon/model.py`: add `tool_choice` param to `chat()` + `_payload()`; send
  it in the request body. Default `"auto"`.
- `daemon/session.py`: `Session` gains `tool_choice` attr + a lightweight
  `_classify_turn(text)`:
  - QUESTION (why / explain / what is / how does / describe...) -> `"auto"`
  - ACTION (everything else: install, list, run, spawn, "what's in Downloads",
    "cowsay hello") -> `"required"`
  - Pass the classified choice into `engine.chat(..., tool_choice=...)` per turn.
- Sub-sessions (interpreter, vibe, spawn): always `tool_choice="required"`.
- Keep `_extract_text_tool_call` / `_extract_json_command_call` as a last-resort
  net; they should fire far less now.

## Part 2 — Session management (AI-tool style)

New module `daemon/session_store.py` for persistence under
`jail/home/<user>/.as/sessions/<name>.json`:
- save / load / list / delete session state (messages + temp). System prompt is
  rebuilt fresh on load (uptime/apps are live).
- `Session` gains `to_dict()` / `from_dict()` and `est_tokens()` heuristic
  (sum(len(m.content.split()) * 1.3)).

Shell builtins (`shell/as_shell.py`):
- `new`            — fresh session (discards current, regenerates system prompt)
- `new temp`       — temporary session (runs, auto-discards, never saved)
- `sessions`       — list saved sessions (name, turns, est tokens)
- `session switch <name>` — load a saved session as current
- `session rename <name> <new>` — explicit name (locks auto-naming)
- `session delete <name>` — remove a saved session
- `history`        — current session turn count + est tokens + warning when long
- Auto-warn: at ~40 turns or ~6000 est tokens, print a "context getting long,
  type new" hint.

Auto-naming (when no explicit name given):
- On `new`, name = extractive from the first non-trivial user message.
- Continuous rename: if the user never locks a name, update the session name
  every ~5 turns from the most recent user message.
- Explicit `session rename` locks the name (stops auto-rename).

## Verification

1. Shell action turn (e.g. "cowsay hello") sends tool_choice=required and emits
   a structured tool call.  [DONE - live: "list the home directory" -> required
   -> list(path="/home/user")]
2. Shell question turn (e.g. "why is the sky blue") sends tool_choice=auto and
   answers without forcing a tool call.  [DONE - live: answered in prose]
3. `new` starts a fresh session; `history` shows turns/tokens; long sessions warn.
   [DONE - REPL tested: new/history/sessions/help/status all work]
4. `sessions` lists; `session switch` loads; `session rename` locks; `session
   delete` removes; `new temp` runs without saving.  [DONE - 22 unit tests +
   shell unit tests all pass]
5. Saved sessions persist across shell restarts.  [DONE - daemon store
   save/load/rename/delete/latest verified; load_session rebuilds fresh prompt]

Extras found while implementing:
- The bench reliability.py FakeExec.execute lacked the `chrooted` kwarg (stale
  helper vs _exec_tool); fixed to accept it.
- `_classify_turn` treats greetings/trivial input as auto so "hi" never forces
  a tool call; "what's in X" is an action (required).
- store.rename rewrites the JSON name field (not just the filename) so a
  renamed session keeps its display name after a reload.
- man shell.txt updated with the new session builtins and SESSIONS section.
- Live repro of the user's exact report ("make a directory called asm-calc in
  Documents"): with tool_choice=required the model emits a structured
  `mkdir({path:...})` and the shell shows `⟳ mkdir(...)`. The prior failure
  (endless "— kernel-2*" narration) was the model drifting into a `[run] mkdir
  path` bracket directive that the text parser didn't recognize, so no tool
  call was executed and the narration streamed forever. Fix: `_extract_bracket_tool_call`
  now parses `[tool] args` directives (run -> command, list/read/mkdir/delete
  -> path, calc -> expr, spawn app=... args=[], vibe action target) as a
  fallback when the `toolname(...)` form doesn't match. Verified: the drift
  is caught, executed, and the turn ends cleanly.
