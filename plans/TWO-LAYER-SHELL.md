# Plan: Two-Layer Shell/Interpreter Split + Thinking UI

## Architecture
```
user → as# REPL (start_as_shell.sh)
         └─ SHELL agent (policy.md)
              owns SHELL_TOOLS:
              list read write append run search calc info ask draw spawn vibe
              delete move copy mkdir interpret
                    │  plain-English wish (never shell syntax)
                    ▼
         └─ INTERPRETER agent (interpreter_policy.md)
              owns full busybox run + list/read/write/append/search/calc/info
              chrooted inside jail/, cwd = /home/<user>
              reachable only via shell's interpret() or app runtime (spawn)
              terse, no personality
```

## Thinking UI
- Config: `[daemon] show_thinking` — "on"/"off"/"silent"
- ON: dim cyan (shell) / dim magenta (interpreter) token stream + ⟳ tool lines
- OFF: status lines: "shell is thinking...", "interpreter is thinking...", "running tasks...", "shell is forming an answer..."
- SILENT: no thinking at all (just show result) — for showcases

## Scripts
- `start_as_shell.sh` — starts llama-server + launches as_shell.py
- `stop_all.sh` — kills llama-server + any child processes

## Changes
1. `plans/TWO-LAYER-SHELL.md` — this plan
2. `daemon/interpreter_policy.md` — new interpreter system prompt
3. `daemon/policy.md` — rewritten as shell policy
4. `daemon/prompt.py` — shell + interpreter prompt builders
5. `daemon/tools.py` — split toolsets, add interpret/file tools, chrooted interpreter run
6. `daemon/session.py` — layer tag, phase events
7. `daemon/server.py` — shell session, interpret handler, app runtime uses interpreter
8. `shell/as_shell.py` — thinking UI, two colors, status lines, fix disappearing answer
9. `config.toml` — show_thinking setting
10. `scripts/setup-jail.sh` — install busybox into jail for chroot
11. `scripts/start_as_shell.sh` + `scripts/stop_all.sh`
12. `README.md` — document two layers

## Verify
- chroot works (unshare -r or setuid helper)
- Interpreter run("ls") lists jail root
- Shell smoke: "list files in the working directory" + delegation
- Thinking ON/OFF/SILENT rendering
- OOBE, spawn/vibe still work
- bench scripts still import TOOLS
