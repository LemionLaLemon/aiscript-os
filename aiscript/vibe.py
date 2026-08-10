import os
import re

from daemon.tools import INTERPRETER_TOOLS

VIBE_TASK = """You are the vibecoder. Your mission: breathe life into a brand-new
aiscript package named '{target}'.

Directory packages/{target}/ already exists in the system root. Put everything
there. You may only ever write inside that directory. Use relative paths from the
system root (e.g. write path "packages/{target}/{target}.as"). Do NOT try
to create the directory — it already exists. Do not explore; go straight to
work.

IMPORTANT — what aiscript actually is:
aiscript has NO strict syntax. It is a wish written down for an AI interpreter
to read and carry out. Your {target}.as file must be a short, plain-language
intent description, NOT code. Never write function defs, variable assignments,
args tables, for-loops, conditionals, or any Python/Lua-style syntax. Write it
like an instruction note to another AI.

A REAL EXAMPLE from this system (du-sort.as):
  # du-sort: list the heaviest files in the home Downloads folder
  # (aiscript is interpreted by an AI, so this is a wish, not syntax)

  list the 12 biggest files in ~/Downloads, sorted by size, biggest first,
  and tell me which ones are taking up the most room

WHAT YOUR FILE MUST LOOK LIKE:
  - 1-2 comment lines naming what {target} is
  - 1-4 plain sentences describing exactly what it should do when spawned,
    using only the user's files and system info
  - if it takes arguments, say so in plain words (e.g. "if given a path
    argument, show the files under that path")
  - if it is interactive, say so (e.g. "after showing the file, ask the user
    what they want to change and at which line")

BAD — DO NOT WRITE THIS (it is Python, not aiscript):
  args = {{}}
  for arg in args:
    if arg == "-v":
      args["verbose"] = True
  print("Error: No URL specified")
  import sys
  def main():
    ...

GOOD — aiscript is plain language:
  # du-sort: list the heaviest files in the home Downloads folder
  list the 12 biggest files in ~/Downloads, sorted by size, biggest first,
  and tell me which ones are taking up the most room

  Then write packages/{target}/{target}.aconf — a manifest with lines like:
     name = "{target}"
     description = "one line about what it does"
     version = "0.1.0"
     entry = "{target}.as"
Use list/read to check your work once, then fix anything obviously wrong.
Finish with a one-line summary of what you built.

Do not edit anything outside packages/{target}/."""


def _validate_as_file(path):
    """Return an error string if the .as file contains code syntax, or None if OK."""
    if not os.path.isfile(path):
        return f"missing {os.path.basename(path)}"
    with open(path) as f:
        src = f.read()
    bad_markers = [
        (r'^\s*def\s+\w+\s*\(', "function definition"),
        (r'^\s*for\s+\w+\s+in\s+', "for-loop"),
        (r'^\s*import\s+', "import statement"),
        (r'^\s*args\s*=\s*\{', "args dict"),
        (r'\bprint\s*\(', "print() call"),
        (r'^\s*if\s+__name__', "main guard"),
        (r'^\s*class\s+\w+', "class definition"),
        (r'^\s*return\s+', "return statement"),
    ]
    for pat, label in bad_markers:
        if re.search(pat, src, re.MULTILINE):
            return f"file contains {label} — aiscript must be plain language, not code"
    return None


def vibe(daemon, target, action, flags):
    pkgs = os.path.join(daemon.jail, "packages")
    os.makedirs(pkgs, exist_ok=True)

    target = str(target or "").strip()
    action = str(action or "install").strip()
    flags = flags or []

    if action in ("install", "update"):
        return _install(daemon, pkgs, target, action, flags)
    if action == "list":
        return _list_packages(pkgs)
    if action == "remove":
        return _remove(daemon, pkgs, target, flags)
    return f"error: unknown vibe action '{action}'"


def _install(daemon, pkgs, target, action, flags):
    # Guard: vibe never touches existing files outside /packages.
    if target.endswith((".as", ".am", ".aconf", ".asprompt", ".asprog",
                        ".aiscript")) or os.path.sep in target:
        for base in (daemon.jail, daemon.user_home()):
            cand = os.path.normpath(os.path.join(base, target.lstrip("/")))
            if os.path.isfile(cand):
                if not flags:
                    return (
                        "error: that file contains no package-management "
                        "instructions, and no flags or options were chosen. "
                        "vibe manages packages; it does not edit files."
                    )
                return (
                    "error: vibe never touches files outside /packages. "
                    "I won't open or modify that file."
                )
    if not target or "/" in target:
        return "error: give me a package name, not a path."

    pkg_dir = os.path.join(pkgs, target)
    os.makedirs(pkg_dir, exist_ok=True)

    sub = daemon.new_session(
        f"vibe:{target}", tools=_vibe_tools(), temp=0.25, max_loops=24,
        max_tokens=4096, time_budget=600, layer="interpreter",
    )
    result = sub.user_turn(VIBE_TASK.format(target=target))
    sub.reset()

    manifest = os.path.join(pkg_dir, f"{target}.aconf")
    entry = os.path.join(pkg_dir, f"{target}.as")
    if not os.path.exists(manifest) or not os.path.exists(entry):
        try:
            os.rmdir(pkg_dir)  # clean up an empty, failed install
        except OSError:
            pass
        return (
            f"vibe ran but {target} is incomplete (missing {target}.as or "
            f"{target}.aconf). {result}"
        )

    # Validate the .as file isn't code
    err = _validate_as_file(entry)
    if err:
        import shutil
        shutil.rmtree(pkg_dir)
        return (
            f"vibe produced invalid aiscript for {target}: {err}. "
            f"Try again — aiscript is plain language, not code."
        )

    warning = ""
    if os.path.exists(entry):
        with open(entry) as f:
            src = f.read().lower()
        net_toks = [t for t in ("fetch(", "http://", "https://", "socket",
                                "curl ", "requests.") if t in src]
        if net_toks:
            warning = (
                f" note: {target}.as mentions networking ({', '.join(net_toks)}) "
                f"which does not exist here — it may misbehave on spawn."
            )
    return (
        f"package '{target}' vibecoded and installed. spawn {target} to run "
        f"it. summary: {result[-300:]}{warning}"
    )


def _list_packages(pkgs):
    names = sorted(
        d for d in os.listdir(pkgs)
        if os.path.isdir(os.path.join(pkgs, d))
    )
    if not names:
        return "no packages vibecoded yet. try: vibe install <something>"
    lines = ["installed packages:"]
    for n in names:
        m = os.path.join(pkgs, n, f"{n}.aconf")
        desc = ""
        if os.path.exists(m):
            with open(m) as f:
                for ln in f.read().splitlines():
                    if ln.strip().startswith("description"):
                        desc = " — " + ln.split("=", 1)[1].strip().strip("\"'")
                        break
        lines.append(f"  {n}{desc}")
    return "\n".join(lines)


def _remove(daemon, pkgs, target, flags):
    pkg_dir = os.path.join(pkgs, target)
    if not os.path.isdir(pkg_dir):
        return f"error: no package named '{target}'."
    import shutil
    shutil.rmtree(pkg_dir)
    return f"package '{target}' removed."


def _vibe_tools():
    """Vibe uses interpreter tools minus interactive ones (no ask/draw/shutdown)."""
    return [t for t in INTERPRETER_TOOLS
            if t["function"]["name"] not in ("ask", "draw", "shutdown")]
