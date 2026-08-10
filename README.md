# as-os

An operating system whose soul is a local AI. There is no compiler on this
machine. Everything is **aiscript** — a plain-language wish that an AI
interpreter reads and carries out. You talk to the machine in sentences; it
figures out the rest.

## The fiction

- **kernel-2** is the AI brain. It interprets everything you type at `as#`.
- **aiscript** is the only language. It has no syntax rules — it is a wish,
  written down, interpreted by an AI. `.as` = runnable app, `.am` = module,
  `.aconf` = config.
- **vibe** is the package manager. It *vibecodes* an aiscript app from a
  package name into `/packages/<name>/`. There is no network and no repo —
  every package is generated on the spot.
- **spawn** runs a vibecoded (or hand-written) app in its own AI sub-session.
- The machine is warm, cheeky, and gently rude. It loves you and will insult
  you affectionately. It will refuse networking and other programming
  languages with enthusiasm.

## Requirements

- Linux with a reasonably modern CPU (built and tuned on an i5-13420H).
- ~8 GB free RAM (the model + KV cache dominate).
- A GGUF model in `models/` (LFM2.5-8B-A1B is the default; Qwen3.5-2B/4B
  also available).

## Build

### 1. llama.cpp

`tools/llama.cpp/` is a source tree; build `llama-server` (the path in
`config.toml` is `tools/llama.cpp/llama-b10333`). Any recent `llama-server`
with `--cache-prompt` support works.

### 2. Models

Download a GGUF into `models/` and set `model_path`/`model_name` in
`config.toml`. Default: `LFM2.5-8B-A1B-Q4_K_M.gguf`.

### 3. Seed the sandbox (optional)

```sh
python3 scripts/seed_jail.py    # demo user + Downloads/Documents sample files
```

## Run

```sh
./scripts/start_as_shell.sh    # starts llama-server + launches the as# shell
```

Or manually:
```sh
./scripts/start-server.sh      # start llama-server on 127.0.0.1:8080
python3 shell/as_shell.py      # the as# shell (connects in-process)
```

To stop everything: `./scripts/stop_all.sh`

On first boot, the machine runs an **OOBE** — it introduces itself, creates
your user account, and asks a few personalisation questions.

## Use

Type anything at `as#`. It is natural language, not a command language:

```
as# list the 5 biggest files in my Downloads folder
as# read my notes.txt
as# sum up the sizes of everything in Downloads
as# spawn notepad
as# vibe install fastfetch
```

Built-ins (the only non-AI commands):

```
help     status     chaos on|off|p <n>     temp <0-1>     reset     exit
```

- `vibe install <name>` — vibecode a package, then `spawn <name>` to run it.
- `vibe list` / `vibe remove <name>` / `vibe update <name>`.
- `chaos` toggles the system's chaos probability (it occasionally mutates
  tool calls for fun); `p 0` disables it entirely.

### Tools the shell has

`list` `read` `write` `append` `run` `search` `calc` `info` `ask` `draw`
`spawn` `vibe` `interpret` `delete` `move` `copy` `mkdir` `shutdown` — all
sandboxed inside the `jail/` root. The `interpret` tool delegates plain-English
wishes to the interpreter layer (chrooted full busybox). `~` means your home
(`home/<user>/`).

## Architecture

```
as# shell (shell agent, personality, toolset)
    │  plain-English wishes via interpret()
    ▼
interpreter (full busybox, chrooted in jail/, terse)
    └── apps (spawn) also use the interpreter
```

- **Shell** — the user-facing agent with personality and the toolset. Owns the
  `policy.md` prompt. Runs sandboxed tools directly.
- **Interpreter** — a deeper agent chrooted in `jail/` with the entire busybox.
  Only reachable via the shell's `interpret()` or the app runtime (spawn).
  Terse, no personality.
- **Thinking UI** — `show_thinking` in `config.toml`: "on" = colored token stream,
  "off" = status lines, "silent" = no thinking at all.

See `docs/architecture.png` (regenerate with
`docs/architecture_diagram.py`).

## Troubleshooting

- **First turn is slow (~90s)** — the prompt cache is cold on a new session.
  Warm turns run in 3–6s.
- **Engine won't start** — llama-server needs the model path and build
  dir from `config.toml`; check `scripts/start-server.sh`.
- **Interpreter chroot broken** — run `scripts/setup-jail.sh` to install
  busybox into the jail.
- **Warm turns re-answer from memory** — after a turn, the model may answer
  follow-ups without re-listing. If files changed, ask it to look again.

## Repo layout

- `daemon/` — brain policy (shell + interpreter), sessions, tools, OOBE
- `aiscript/` — the runner (interpret apps) and vibe (vibecode packages)
- `asui/` — tiny UI library (terminal now; framebuffer comes with the image)
- `shell/as_shell.py` — the interactive shell
- `jail/` — the fake root filesystem (users, apps, packages) — gitignored
- `plans/` — roadmap and phase plans
- `bench/` — smoke test and reliability battery
- `scripts/` — start_as_shell.sh, stop_all.sh, setup-jail.sh
