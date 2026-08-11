"""Shared system-prompt builders for daemon/server.py and bench scripts."""
import os


def build_shell_prompt(cfg, user=None):
    """Return the full shell system prompt from config."""
    root = os.path.dirname(os.path.dirname(__file__))
    policy_path = os.path.join(root, cfg["daemon"]["policy"])
    with open(policy_path) as f:
        base = f.read()
    user = user or os.environ.get("USER", "user")
    jail = cfg["daemon"].get("jail", "jail")
    body = (
        f"Current user on this system: {user}.\n"
        f"Filesystem layout:\n"
        f"  /home/{user}       — the user's home (Downloads, Documents)\n"
        f"  /apps             — installed aiscript apps\n"
        f"  /packages         — vibecoded packages (managed by vibe only)\n"
        f"{_installed_summary(jail)}\n"
        f"System uptime so far: {_uptime()}.\n\n" + base
    )
    return _delimit(body)


def _installed_summary(jail):
    """List what's actually installed so the shell knows its apps/packages."""
    apps_dir = os.path.join(jail, "apps")
    pkgs_dir = os.path.join(jail, "packages")
    apps, pkgs = [], []
    if os.path.isdir(apps_dir):
        for f in sorted(os.listdir(apps_dir)):
            name, ext = os.path.splitext(f)
            if ext in (".as", ".ais") and name:
                apps.append(name)
    if os.path.isdir(pkgs_dir):
        for d in sorted(os.listdir(pkgs_dir)):
            if os.path.isdir(os.path.join(pkgs_dir, d)):
                pkgs.append(d)
    lines = []
    if apps:
        lines.append(f"Installed apps: {', '.join(apps)}")
    if pkgs:
        lines.append(f"Installed packages: {', '.join(pkgs)}")
    if not lines:
        lines.append("Installed apps: (none yet — use vibe to add some)")
    return "\n".join(lines)


def build_interpreter_prompt(cfg, user=None):
    """Return the interpreter system prompt."""
    root = os.path.dirname(os.path.dirname(__file__))
    interp_path = os.path.join(root, cfg["daemon"].get(
        "interpreter_policy", "daemon/interpreter_policy.md"))
    with open(interp_path) as f:
        base = f.read()
    user = user or os.environ.get("USER", "user")
    body = (
        f"Your working directory is /home/{user} inside the sandbox.\n"
        f"The user's home is /home/{user}. "
        f"System uptime: {_uptime()}.\n\n" + base
    )
    return _delimit(body)


def _delimit(text):
    """Wrap a system prompt in clear delimiters so the model can never
    confuse system instructions with a user message."""
    return "-- START SYSTEM PROMPT --\n" + text + "\n-- END SYSTEM PROMPT --"


def _uptime():
    try:
        with open("/proc/uptime") as f:
            up = float(f.read().split()[0])
        m, s = divmod(int(up), 60)
        return f"{m}m{s}s"
    except Exception:
        return "unknown"
