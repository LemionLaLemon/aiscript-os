"""Shared system-prompt builders for daemon/server.py and bench scripts."""
import os


def build_shell_prompt(cfg, user=None):
    """Return the full shell system prompt from config."""
    root = os.path.dirname(os.path.dirname(__file__))
    policy_path = os.path.join(root, cfg["daemon"]["policy"])
    with open(policy_path) as f:
        base = f.read()
    user = user or os.environ.get("USER", "user")
    return (
        f"Current user on this system: {user}.\n"
        f"Filesystem layout:\n"
        f"  /home/{user}       — the user's home (Downloads, Documents)\n"
        f"  /apps             — installed aiscript apps\n"
        f"  /packages         — vibecoded packages (managed by vibe only)\n"
        f"System uptime so far: {_uptime()}.\n\n" + base
    )


def build_interpreter_prompt(cfg, user=None):
    """Return the interpreter system prompt."""
    root = os.path.dirname(os.path.dirname(__file__))
    interp_path = os.path.join(root, cfg["daemon"].get(
        "interpreter_policy", "daemon/interpreter_policy.md"))
    with open(interp_path) as f:
        base = f.read()
    user = user or os.environ.get("USER", "user")
    return (
        f"Your working directory is /home/{user} inside the sandbox.\n"
        f"The user's home is /home/{user}. "
        f"System uptime: {_uptime()}.\n\n" + base
    )


def _uptime():
    try:
        with open("/proc/uptime") as f:
            up = float(f.read().split()[0])
        m, s = divmod(int(up), 60)
        return f"{m}m{s}s"
    except Exception:
        return "unknown"
