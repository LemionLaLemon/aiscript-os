import os
import re

_IMPORT_RE = re.compile(
    r"^\s*(?:from\s+\"([^\"]+)\"\s+import\s+(\w+)|"
    r"import\s+\"([^\"]+)\"\s+as\s+(\w+))\s*$"
)


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
    program = (
        f"--- aiscript program: {path} ---\n"
        f"<arguments: {args_repr or 'none'}>\n"
        f"{src}\n"
        f"--- end of program ---\n"
        f"Run this aiscript program now. Use your tools to do what it asks, "
        f"then report the result briefly. Keep your reply short."
    )
    return session.continue_turn(program, on_event=on_event)
