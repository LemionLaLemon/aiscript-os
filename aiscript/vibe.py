import os
import re

from daemon.tools import INTERPRETER_TOOLS

VIBE_TASK = """-- START SYSTEM PROMPT --
You are the vibecoder. Your mission: breathe life into a brand-new aiscript
package named '{target}'.

Directory packages/{target}/ already exists in the system root. Put everything
there. You may only ever write inside that directory. Use relative paths from
the system root (e.g. write path "packages/{target}/{target}.as"). Do NOT try
to create the directory — it already exists. Do not explore; go straight to
work.

IMPORTANT — what aiscript actually is:
aiscript is interpreted by an AI. It has no strict syntax. A .as file has TWO
sections:

  1. SYSTEM PROMPT SECTION (REQUIRED): a short description of what the program
     does, so the interpreter knows its purpose.
  2. --- program --- SECTION (OPTIONAL): the program's real logic and assets.
     This can be actual code (Python-style or any style), data, ASCII art,
     templates — whatever the program needs. Code is ENCOURAGED here when the
     package needs real behavior; the interpreter reads and executes it.

REAL EXAMPLE (cowsay):
  # cowsay: make a cow say a message
  # given a message, show it in a speech bubble above an ASCII cow

  --- program ---
  COW = [
      "        \\   ^__^",
      "         \\  (oo)\\_______",
      "            (__)\\       )\\/\\",
      "                ||----w |",
      "                ||     ||",
  ]

  when spawned: take the message from the first argument (or ask the user),
  wrap it in a speech bubble, then print the cow below the bubble.

WHAT YOUR FILE MUST LOOK LIKE:
  - Start with 1-2 comment lines: "# {target}: <one-line description>"
  - Add 1-4 plain sentences describing what it does when spawned, using only
    the user's files and system info.
  - If it takes arguments, say so in plain words (e.g. "if given a path
    argument, show the files under that path").
  - If it is interactive, say so (e.g. "after showing the file, ask the user
    what they want to change and at which line").
  - Add a "--- program ---" section with real logic/assets when the package
    needs behavior beyond simple reporting. Actual code is fine and welcome.

  Then write packages/{target}/{target}.aconf — a manifest with lines like:
     name = "{target}"
     description = "one line about what it does"
     version = "0.1.0"
     entry = "{target}.as"
Use list/read to check your work once, then fix anything obviously wrong.
Finish with a one-line summary of what you built.

MANDATORY: your {target}.as file MUST contain a "--- program ---" section
with real content — actual code, data, or assets that make the program do
something. A description alone is a failed install and will be rejected.
The whole point is that the program CAN RUN. If {target} has behavior
(say something, list something, calculate something, draw something), the
program section must implement that behavior in concrete code or data.
NEVER stop after just writing the description — always write the program
section too.

WORK STYLE: Do NOT narrate a plan. Do NOT write "analysis" or "plan"
sections. Do NOT list the steps you will take. Go straight to writing.

You may call the write tool (preferred). BUT if calling tools is not working
or you are not sure the file was written, do NOT loop and do NOT give up:
instead, OUTPUT THE FILE CONTENTS DIRECTLY, exactly like this:

  --- cowsay.as ---
  # cowsay: cow message display
  when spawned: show a message in a speech bubble above an ASCII cow
  --- program ---
  (the real program logic/assets)
  --- cowsay.aconf ---
  name = "cowsay"
  description = "cow message display"
  version = "0.1.0"
  entry = "cowsay.as"

Put each file under a line that is exactly "--- <filename> ---". The system
will save those sections for you. One shot: either call write() for both
files, or output both --- sections. Never do both repeatedly, never loop,
never say "I'll do it next".

Do not edit anything outside packages/{target}/.
-- END SYSTEM PROMPT --"""


def _validate_as_file(path):
    """Return an error string if the .as file is a stub/header-only, else None."""
    if not os.path.isfile(path):
        return f"missing {os.path.basename(path)}"
    with open(path) as f:
        src = f.read()

    # (a) must have a "# <name>:" header line
    if not re.search(r'^#\s*\S+\s*:', src, re.MULTILINE):
        return "missing the required '# <name>: description' header line"

    # (b) must not be a stub: at least 3 non-empty lines, OR a program section
    body = [ln for ln in src.splitlines() if ln.strip()]
    has_program = "--- program ---" in src
    if not has_program and len(body) < 3:
        return (
            "file is only a stub (a description with no body or program "
            "section). Give it real content."
        )
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
        f"vibe:{target}", system_prompt=VIBE_TASK.format(target=target),
        tools=_vibe_tools(), temp=0.25, max_loops=8,
        max_tokens=4096, time_budget=300, layer="interpreter",
        tool_choice="required", cwd="",
    )
    result = sub.user_turn(
        f"Vibecode the '{target}' package now. Write packages/{target}/"
        f"{target}.as and packages/{target}/{target}.aconf."
    )
    sub.reset()

    manifest = os.path.join(pkg_dir, f"{target}.aconf")
    entry = os.path.join(pkg_dir, f"{target}.as")
    if not os.path.exists(manifest) or not os.path.exists(entry):
        # The vibecoder sometimes emits the file contents as a text/markdown
        # dump instead of calling the write tool (a reasoning-model quirk).
        # Recover the files from the dump before giving up.
        written = _recover_from_dump(daemon, pkg_dir, target, result)
        if written:
            entry = os.path.join(pkg_dir, f"{target}.as")
            manifest = os.path.join(pkg_dir, f"{target}.aconf")
        elif os.path.exists(entry) or os.path.exists(manifest):
            written = True
        if not written:
            # First attempt produced nothing usable. The vibecoder sometimes
            # gets stuck in a repetition spiral (a reasoning-model quirk) and
            # returns empty. One corrective retry with a stronger kick before
            # giving up.
            result = _retry_vibecode(daemon, sub, pkg_dir, target, result,
                                     "no files were written")
            written = _recover_from_dump(daemon, pkg_dir, target, result)
            if written:
                entry = os.path.join(pkg_dir, f"{target}.as")
                manifest = os.path.join(pkg_dir, f"{target}.aconf")
            else:
                try:
                    os.rmdir(pkg_dir)  # clean up an empty, failed install
                except OSError:
                    pass
                return (
                    f"vibe ran but {target} is incomplete (missing {target}.as "
                    f"or {target}.aconf). {result}"
                )

    # Validate the .as file isn't a stub
    err = _validate_as_file(entry)
    if err:
        # auto-retry once with a stronger kick
        result2 = _retry_vibecode(daemon, sub, pkg_dir, target, result, err)
        err = _validate_as_file(entry)
        if err:
            import shutil
            shutil.rmtree(pkg_dir)
            return (
                f"vibe produced a bad {target}.as after a retry: {err}. "
                f"{result2}"
            )
        result = result2

    # The aconf manifest is simple and mechanical — if the vibecoder garbled
    # it, regenerate it deterministically. A bad manifest breaks spawn.
    if not _valid_manifest(manifest, target):
        with open(manifest, "w") as f:
            f.write(
                f'name = "{target}"\n'
                f'description = "vibecoded {target} package"\n'
                f'version = "0.1.0"\n'
                f'entry = "{target}.as"\n'
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


def _retry_vibecode(daemon, sub, pkg_dir, target, result, err):
    """One corrective retry: tell the vibecoder its file was rejected and why,
    then let it fix the file in place."""
    # recreate the sub-session (previous one was reset)
    sub2 = daemon.new_session(
        f"vibe:{target}-retry", system_prompt=VIBE_TASK.format(target=target),
        tools=_vibe_tools(), temp=0.3, max_loops=6,
        max_tokens=4096, time_budget=240, layer="interpreter",
        tool_choice="required", cwd="",
    )
    kick = (
        f"Your previous vibe of '{target}' was rejected: {err}. "
        f"The packages/{target}/ directory still exists. Rewrite "
        f"packages/{target}/{target}.as so it passes: it MUST have the "
        f"'# {target}: description' header AND a '--- program ---' section "
        f"with real logic/assets. Also ensure packages/{target}/{target}.aconf "
        f"exists. Do it now."
    )
    result2 = sub2.user_turn(kick)
    sub2.reset()
    return result2


def _recover_from_dump(daemon, pkg_dir, target, result):
    """The vibecoder sometimes writes the package as a plain-text/markdown
    dump instead of calling the write tool. If so, carve the .as and .aconf
    out of the result text and write them into pkg_dir. Returns True if both
    files now exist."""
    if not result:
        return False
    text = str(result)
    # Only attempt recovery if the dump clearly contains both a header line
    # and a program section (i.e. it really is the .as content, not chatter).
    if "# " not in text and "--- program ---" not in text:
        return False
    written = False
    for path, body in _split_dump(text):
        rel = os.path.basename(path)
        if rel.endswith(".aconf"):
            with open(os.path.join(pkg_dir, rel), "w") as f:
                f.write(body)
            written = True
        elif rel.endswith(".as") or rel.endswith(".ais"):
            with open(os.path.join(pkg_dir, rel), "w") as f:
                f.write(body)
            written = True
    # If the dump didn't label its files, fall back to heuristic detection:
    # a .as block is everything with the header, .aconf is the name= block.
    if not written:
        if "--- program ---" in text or re.search(r'^#\s*\S+\s*:', text, re.MULTILINE):
            entry = os.path.join(pkg_dir, f"{target}.as")
            with open(entry, "w") as f:
                f.write(text.strip() + "\n")
            written = True
    return written


def _split_dump(text):
    """Split a vibecoder dump into (path, body) pairs. Handles labelled
    blocks like '--- packages/cowsay/cowsay.as ---' and markdown fenced
    blocks with a filename in the info string (```cowsay.as)."""
    import re as _re
    pairs = []
    # labelled section: --- packages/<name>/file.ext --- ... (next marker or EOF)
    for m in _re.finditer(r"---+\s*([\w./@-]+?\.(?:as|ais|aconf))\s*---*", text):
        path = m.group(1)
        start = m.end()
        nxt = _re.search(r"---+\s*[\w./@-]+?\.(?:as|ais|aconf)\s*---*", text[start:])
        end = start + nxt.start() if nxt else len(text)
        body = text[start:end].strip()
        if body:
            pairs.append((path, body))
    # markdown fences: ```cowsay.as ... ``` or ``` ... ``` near a filename line
    if not pairs:
        for m in _re.finditer(r"```([\w./@-]*\.(?:as|ais|aconf))?\s*\n(.*?)```",
                              text, _re.DOTALL):
            lang = m.group(1) or ""
            body = m.group(2).strip()
            if not body:
                continue
            if lang:
                pairs.append((lang, body))
            else:
                # try to guess from a preceding "Filename: X" or "file: X" line
                pre = text[max(0, m.start() - 200):m.start()]
                fm = _re.search(r"(?:filename|file|path)\s*[:=]\s*([\w./@-]+\.(?:as|ais|aconf))",
                                pre, _re.IGNORECASE)
                if fm:
                    pairs.append((fm.group(1), body))
    return pairs


def _valid_manifest(path, target):
    """A manifest is valid if it has name=, entry=, and version=/description=
    lines that look right (not the vibecoder's repeated chatter)."""
    if not os.path.isfile(path):
        return False
    try:
        with open(path) as f:
            src = f.read()
    except OSError:
        return False
    has_name = re.search(r'^\s*name\s*=\s*["\']?' + re.escape(target) +
                         r'["\']?\s*$', src, re.MULTILINE)
    has_entry = re.search(r'^\s*entry\s*=', src, re.MULTILINE)
    # reject obvious junk (a manifest should be < 200 chars of real config)
    if len(src) > 400:
        return False
    return bool(has_name and has_entry)


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
