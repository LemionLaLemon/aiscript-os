import os

VIBE_TASK = """You are the vibecoder. Your mission: breathe life into a brand-new
aiscript package named '{target}'.

Directory packages/{target}/ already exists in the system root. Put everything
there. You may only ever write inside that directory. Use relative paths from
the system root (e.g. write path "packages/{target}/{target}.as"). Do NOT try
to create the directory — it already exists. Do not explore; go straight to
work.

IMPORTANT — what aiscript actually is:
aiscript has NO strict syntax. It is a wish written down for an AI interpreter
to read and carry out. Your {target}.as file must be a short, plain-language
intent description, NOT code. Never write function defs, variable assignments,
args tables, for-loops, conditionals, or any Python/Lua-style syntax. Write it
like an instruction note to another AI.

A real example from this system:
  # du-sort: list the heaviest files in the home Downloads folder
  # (aiscript is interpreted by an AI, so this is a wish, not syntax)

  list the 12 biggest files in ~/Downloads, sorted by size, biggest first,
  and tell me which ones are taking up the most room

So write packages/{target}/{target}.as with:
  - 1-2 comment lines naming what {target} is
  - 1-3 plain sentences describing exactly what it should do when spawned,
    using only the user's files and system info
  - if it takes arguments, say so in plain words (e.g. "if given a path
    argument, show the files under that path")
  - NOTE: '~' IS the user's home directory. Write "~" or "~/Downloads",
    never "~/home". If you want the whole home, just say "~".
  - Remember: there is NO networking anywhere on this system. Never use
    fetch, http, url, socket, curl, request, or downloads in your app.

Then write packages/{target}/{target}.aconf — a manifest with lines like:
     name = "{target}"
     description = "one line about what it does"
     version = "0.1.0"
     entry = "{target}.as"
Use list/read to check your work once, then fix anything obviously wrong.
Finish with a one-line summary of what you built.

Do not edit anything outside packages/{target}/."""


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
        f"vibe:{target}", tools=_vibe_tools(), temp=0.35, max_loops=20,
        max_tokens=600, time_budget=420,
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
    from . import runner
    from daemon.tools import TOOLS
    return [t for t in TOOLS
            if t["function"]["name"] not in ("vibe", "shutdown", "ask", "draw")]
