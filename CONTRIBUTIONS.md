# Contributing to aiscript-os

Thanks for helping with ascOS. This project is an experiment in making a
local AI the operating system's interpreter, so contributions should preserve
that premise: the user speaks to the AI, and the kernel provides safe tools for
the AI to act.

## Before you start

Read the [README](README.md) for the current architecture and roadmap. The
project is still in Phase 3: the host shell and jailed interpreter are usable,
but the bootable image and package ecosystem are experimental.

The normal development environment is Linux with Python 3, a working
`llama-server`, and a local GGUF model. The model is not required for the
unit and reliability tests.

## Architectural rules

- Keep user intent AI-first. Do not turn ordinary shell input into host
  commands or direct Python dispatch. Built-ins should be narrowly scoped and
  explicit.
- Keep filesystem and command execution inside `jail/`. The interpreter's
  `run()` tool is chrooted; it is not a host shell escape hatch.
- aiscript (`.as`, `.am`, `.aconf`) is intentionally interpreted prose, not a
  compiler language. Do not add a rigid parser where a useful prompt contract
  is enough.
- The shell agent owns personality, policy, sessions, and user-facing output.
  The interpreter agent is terse, operational, and sandboxed.
- Tool calls must be observable and recoverable. Preserve tool-call/result
  context for the active turn, prevent identical retry loops, and make tools
  return useful structured text.
- Terminal apps must not let model tokens own raw keyboard handling or the
  framebuffer. Use deterministic local input/rendering for lifecycle controls;
  delegate semantic actions to the interpreter.
- Do not add networking, telemetry, or dependencies on another programming
  language to the ascOS runtime.

## Local setup

```sh
python3 scripts/seed_jail.py
./scripts/setup-jail.sh
./scripts/start_as_shell.sh
```

The shell starts `llama-server` and then launches `shell/as_shell.py`. Keep
models out of Git; configure the model path in `config.toml` locally.

## Making changes

Prefer small, focused changes. Before editing, identify which layer owns the
behavior:

- `shell/`: terminal input, rendering, built-ins, and user-facing events
- `daemon/`: sessions, model transport, policies, tool execution, and OOBE
- `aiscript/`: app execution and `vibe` package management
- `essential/`: seed packages shipped with the system
- `bench/`: deterministic regression and reliability checks
- `scripts/iso/`: image and seed assembly

When changing a tool, update its schema, implementation, policy guidance, and
tests together. When changing a prompt, test both structured tool calls and
the model's plain-text/XML fallback paths.

## Testing

Run the fast checks before committing:

```sh
python3 -m unittest discover -s bench -p 'test_*.py' -v
python3 bench/reliability.py --guard-only
python3 -m py_compile daemon/*.py aiscript/*.py shell/*.py
git diff --check
```

For changes involving the live model or shell, also run the relevant smoke
tests when the local server is available. A model-generated result is not a
substitute for a deterministic regression test: reproduce the failure with a
fake engine wherever possible.

The full ISO build requires root privileges and external system tooling. Do
not run `make usb` unless you have explicitly selected the target device; it is
destructive.

## aiscript apps and packages

An app should explain its purpose in plain language and include a meaningful
`--- program ---` section (natural variants such as `--- program start` are
also tolerated). Package installation is performed by `vibe`; do not manually
write under `jail/packages/` as part of normal app development.

Interactive apps should define what the native runtime owns—saving, quitting,
keyboard decoding, and screen lifecycle—and reserve the AI interpreter for
semantic work submitted by the user.

## Pull requests and commits

Describe the user-visible behavior, the architectural layer changed, and the
tests you ran. Include a short reproduction for bugs involving model output,
tool calls, prompt history, or terminal state. Avoid committing model files,
generated ISO artifacts, local session history, credentials, or machine-specific
configuration.

Keep commits focused and use imperative summaries, for example:

```text
preserve active tool-call history across interpreter rounds
```

Be kind to contributors and candid about the limits of a small local model.
The goal is a playful, inspectable AI operating system—not a conventional
Unix clone hiding an AI behind a command parser.
