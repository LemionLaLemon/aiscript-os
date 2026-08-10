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
- A Qwen3.5 GGUF model in `models/` (2B is the default; a 4B is also
  available and slower).

## Build

### 1. llama.cpp

`tools/llama.cpp/` is a source tree; build `llama-server` (the path in
`config.toml` is `tools/llama.cpp/llama-b10333`). Any recent `llama-server`
with `--cache-prompt` support works.

### 2. Models

Download a GGUF into `models/` and set `model_path`/`model_name` in
`config.toml`. Default: `Qwen3.5-2B-Q4_K_M.gguf`.

### 3. Seed the sandbox (optional)

```sh
python3 scripts/seed_jail.py    # demo user + Downloads/Documents sample files
```

## Run

```sh
./scripts/start-server.sh        # start llama-server on 127.0.0.1:8080
python3 shell/as_shell.py        # the as# shell (connects in-process)
```

`scripts/start-all.sh` does both. On a laptop you can raise power limits and
switch to a latency profile first (root): `sudo ./scripts/tune.sh`.

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

### Tools kernel-2 has

`list` `read` `write` `append` `run` `search` `calc` `info` `ask` `draw`
`spawn` `vibe` `shutdown` — all sandboxed inside the `jail/` root. No
networking, no other languages, nothing destructive. `~` means your home
(`home/<user>/`).

## Architecture

```
as# shell ──> daemon (sessions) ──> kernel-2 policy ──> tools ──> jail sandbox
                              └──> llama-server :8080 (the 2B brain)
              spawn/vibe create AI sub-sessions that interpret apps
```

See `docs/architecture.png` (regenerate with
`docs/architecture_diagram.py`).

## Troubleshooting

- **First turn is slow (~90s)** — the prompt cache is cold on a new session.
  Warm turns run in 3–6s.
- **Engine won't start** — llama-server needs the model path and build
  dir from `config.toml`; check `scripts/start-server.sh`.
- **Warm turns re-answer from memory** — after a turn, the model may answer
  follow-ups without re-listing. If files changed, ask it to look again.
- **Slower on 4B** — swap `model_path` back to the 2B.

## Repo layout

- `daemon/` — brain policy, sessions, tools, OOBE
- `aiscript/` — the runner (interpret apps) and vibe (vibecode packages)
- `asui/` — tiny UI library (terminal now; framebuffer comes with the image)
- `shell/as_shell.py` — the interactive shell
- `jail/` — the fake root filesystem (users, apps, packages) — gitignored
- `plans/` — roadmap and phase plans
- `bench/` — smoke test and reliability battery
