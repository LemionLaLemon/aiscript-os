"""Shared system-prompt builder used by daemon/server.py and bench scripts."""
import os


def build_system_prompt(cfg, user=None):
    """Return the full OS system prompt from config (policy.md + header)."""
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
        f"System uptime so far: 0.\n\n" + base
    )
