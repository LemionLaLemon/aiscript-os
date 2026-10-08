import os
import re

_IMPORT_RE = re.compile(
    r"^\s*(?:from\s+\"([^\"]+)\"\s+import\s+(\w+)|"
    r"import\s+\"([^\"]+)\"\s+as\s+(\w+))\s*$"
)

# Aiscript has no grammar, so section labels are conventions rather than
# tokens. Keep the canonical spelling for documentation, but recognize the
# natural variants users and small models actually write.
_PROGRAM_LABELS = {
    "program", "program start", "program body", "program logic",
    "program code", "program implementation",
}


def find_program_section(src):
    """Return (preamble, body) for a recognizable program heading, or None."""
    offset = 0
    for line in src.splitlines(keepends=True):
        label = line.strip().strip("-").strip().lower().replace("_", " ")
        label = re.sub(r"\s+", " ", label)
        if label in _PROGRAM_LABELS:
            return src[:offset], src[offset + len(line):]
        offset += len(line)
    return None


def scan_imports(src):
    """Return [(module_path, alias)] from import lines in aiscript source."""
    imports = []
    for line in src.splitlines():
        m = _IMPORT_RE.match(line.strip())
        if m:
            path = m.group(1) or m.group(3)
            alias = m.group(2) or m.group(4)
            imports.append((path, alias))
    return imports


def resolve_module(session, base_path, module_path):
    jail = session.executor.jail
    if module_path.startswith("/"):
        p = os.path.normpath(os.path.join(jail, module_path.lstrip("/")))
    else:
        p = os.path.normpath(
            os.path.join(os.path.dirname(base_path), module_path)
        )
    if p != jail and not p.startswith(jail + os.sep):
        raise FileNotFoundError(f"module escapes sandbox: {module_path}")
    return p


def run_file(session, path, args=None, on_event=None):
    """Interpret an aiscript program by streaming it through the session."""
    session._program_path = os.path.realpath(path)
    with open(path) as f:
        src = f.read()

    for module_path, alias in scan_imports(src):
        try:
            mp = resolve_module(session, path, module_path)
            with open(mp) as f:
                body = f.read()
        except (FileNotFoundError, OSError) as e:
            body = f"[module not found: {e}]"
        session.inject(
            f"[imported module '{alias}' from {module_path}]\n{body}"
        )

    args_repr = ", ".join(map(str, args or []))
    try:
        rel_path = os.path.relpath(path, session.executor.jail)
    except ValueError:
        rel_path = path
    program = (
        "[APP RUNTIME: source and imports are already loaded. Execute the "
        "program immediately. Do not inspect the filesystem for this app, "
        "do not rewrite it, and do not print its source.]\n"
        f"--- aiscript app: {rel_path} ---\n"
        f"<arguments: {args_repr or 'none'}>\n"
        f"{src}\n"
        f"--- end of app ---\n"
        f"Aiscript has no strict grammar. Treat the entire source as executable "
        f"intent. Section headings such as '--- program ---' or "
        f"'--- program start' are organizational hints, not required syntax. "
        f"Carry out that wish now, then report the result briefly."
    )
    return session.continue_turn(program, on_event=on_event)
