"""Architecture diagram of as-os: how the as shell talks to the fast 0.8B
tier, escalates to the 2B big brain, and how aiscript/vibe apps are
"interpreted" by model sessions.

Run:  /tmp/opencode/diag-venv/bin/python3 docs/architecture_diagram.py
Output: docs/architecture.png
"""

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "architecture.png")

fig, ax = plt.subplots(figsize=(22, 17))
ax.set_xlim(0, 130)
ax.set_ylim(0, 84)
ax.axis("off")

# ---- palette ---------------------------------------------------------------
APP = ("#dcebff", "#2b5c8f")   # shell / daemon
SES = ("#e7f0ff", "#3a6ea5")   # sessions / loops
MDL = ("#f0e9ff", "#6a4fa3")   # llama-server model processes
TOL = ("#fff2e0", "#c77a21")   # tools / jail
APL = ("#ffe9ec", "#c2374b")   # aiscript / vibe
ESC = ("#ffe0e0", "#b00020")   # escalation
NOT = ("#f5f5f5", "#888888")   # notes / legend


def box(cx, cy, w, h, text, pal=NOT, fs=9, lw=1.5,
        style="round,pad=0.6,rounding_size=1.4"):
    fc, ec = pal
    b = FancyBboxPatch((cx - w / 2, cy - h / 2), w, h,
                       boxstyle=style, fc=fc, ec=ec, lw=lw, zorder=3)
    ax.add_patch(b)
    ax.text(cx, cy, text, ha="center", va="center", fontsize=fs,
            color="#0b0b0b", zorder=5, linespacing=1.45)
    return (cx, cy, w, h)


def arrow(x1, y1, x2, y2, color="#3a6ea5", ls="-", lw=1.8, rad=0.0,
          label="", lx=0.0, ly=0.0, fs=8.5):
    a = FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=16,
                        color=color, lw=lw, linestyle=ls,
                        connectionstyle=f"arc3,rad={rad}", zorder=4)
    ax.add_patch(a)
    if label:
        ax.text((x1 + x2) / 2 + lx, (y1 + y2) / 2 + ly, label,
                ha="center", va="center", fontsize=fs, color=color,
                style="italic", zorder=6,
                bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none",
                          alpha=0.85))


# ============================================================================
# title
# ============================================================================
ax.text(65, 81.5,
        "as-os — how the as shell, the model tiers, and the 'interpreters' fit together",
        ha="center", va="center", fontsize=14, fontweight="bold", color="#0b0b0b")

# ============================================================================
# LAYER 1 — user + shell + daemon
# ============================================================================
box(65, 76, 50, 5.5,
    "as shell  (shell/as_shell.py) — REPL at `as# `\n"
    "builtins handled locally:  help · status · chaos · temp · reset · exit\n"
    "everything else → kernel-2 (a model session)",
    APP, fs=9.5)
box(62, 66.5, 50, 7,
    "Daemon  (daemon/server.py) — one process with the shell\n"
    "session registry · two ModelEngines · ToolExecutor · Chaos gate\n"
    "system prompt = filesystem layout + policy.md (big) / policy_fast.md (fast)\n"
    "persisted user: jail/etc/as-os/user",
    APP, fs=9)

# ============================================================================
# LAYER 2 — the two model tiers
# ============================================================================
box(16, 55.5, 30, 5.5,
    "Session \"shell\" — tier='fast'  → 0.8B\n"
    "FAST_TOOLS: list · read · write · append · run · search · calc · info · ask · escalate\n"
    "prompt: policy_fast.md (≈1,200 tok) · max_tokens=512",
    SES, fs=8.5)
box(90, 55.5, 34, 5.5,
    "Session \"big\" (big_session, lazy)  → 2B\n"
    "full TOOLS: fast set + draw · spawn · vibe · shutdown\n"
    "prompt: policy.md (≈3,000 tok) · max_loops=12 · budget 240 s",
    SES, fs=8.5)

box(16, 45, 30, 7.5,
    "Session._loop (fast tier) — up to 8 rounds\n"
    "engine.chat(_request_messages(), tools=FAST_TOOLS)\n"
    "reply?      → stream to REPL, done\n"
    "tool?       → execute, feed back, loop\n"
    "tool == escalate? → hand off to the big brain",
    SES, fs=8.5)
box(90, 45, 34, 7.5,
    "Session._loop (big brain) — up to 12 rounds\n"
    "engine.chat(_request_messages(), tools=TOOLS)\n"
    "reply? → stream to REPL, done\n"
    "tool?  → execute, feed back, loop",
    SES, fs=8.5)

box(16, 33.5, 30, 5,
    "llama-server :8082 — Qwen3.5-0.8B (E-cores 8–11)\n"
    "warm ≈ 2–4 s · cold ≈ 13 s",
    MDL, fs=8.5)
box(90, 33.5, 34, 5,
    "llama-server :8080 — Qwen3.5-2B (P-cores 0,2,4,6)\n"
    "warm ≈ 3–5 s · cold ≈ 14–60 s",
    MDL, fs=8.5)

# ============================================================================
# COMMON TOOLS → JAIL
# ============================================================================
box(55, 11, 50, 6.5,
    "ToolExecutor.execute(tool, args)  (daemon/tools.py)\n"
    "jail sandbox: _jail_path() resolves paths inside jail/ only — absolute paths refused\n"
    "offline only · chaos may mutate list/read/run/search (p from .asrc)",
    TOL, fs=8.5)
box(55, 2.5, 50, 4.5,
    "jail/  — the fake OS root: home/<user> · apps/ · packages/ · etc/as-os/\n"
    "every user-visible file lives here; the real host filesystem is invisible",
    TOL, fs=8.5)

# ============================================================================
# TOOLS THAT SPAWN SUB-SESSIONS (aiscript interpreter / vibecoder)
# ============================================================================
box(90, 22, 34, 11,
    "spawn / vibe / draw / ask — handlers that create\n"
    "their own session (also on :8080)\n"
    "\n"
    "spawn <app> → runner.run_file streams <app>.as as\n"
    "  one <continuing> turn → \"app:\" session INTERPRETS\n"
    "  the aiscript by calling tools, step by step\n"
    "\n"
    "vibe install <pkg> → VIBE_TASK → \"vibe:\" session\n"
    "  vibecodes packages/<pkg>/<pkg>.as + .aconf\n"
    "\n"
    "draw <spec> → asui renderer · ask → input()",
    APL, fs=8)

# ============================================================================
# NOTES / LEGEND
# ============================================================================
box(116, 62, 26, 7,
    "why turns got fast — _request_messages()\n"
    "drops assistant tool-call messages on re-send and\n"
    "tags results \"[name] …\" so the model still knows\n"
    "what ran → llama.cpp prompt cache survives turns:\n"
    "follow-up 90 s → 2.4 s",
    NOT, fs=7.5)
box(116, 9, 26, 8,
    "legend\n"
    "  solid → tool call / data flow\n"
    "  red dash → escalate() hand-off\n"
    "  gray dash → replies & events\n"
    "  purple = model server · orange = jail\n"
    "  blue = shell/daemon · light blue = session\n"
    "  pink = aiscript / vibe sub-sessions",
    NOT, fs=7.5)

# ============================================================================
# ARROWS
# ============================================================================
arrow(65, 73.3, 65, 70.0, label="input line", ly=-0.5)
arrow(80, 70.1, 80, 73.3, color="#888888", ls=(0, (2, 2)), label="reply / events", ly=0.5)
arrow(45, 63.0, 17, 58.4, label="new_session(tier=\"fast\")", lx=-4, ly=1)
arrow(78, 63.0, 90, 58.4, label="new_session(\"big\")  (lazy, on escalate)", lx=4, ly=1)
arrow(16, 52.7, 16, 48.9)
arrow(90, 52.7, 90, 48.9)
arrow(16, 41.2, 16, 36.1, color="#6a4fa3",
      label="POST /v1/chat/completions (stream)", ly=2)
arrow(90, 41.2, 90, 36.1, color="#6a4fa3")

# escalation hand-off (fast loop -> big loop)
arrow(31, 45, 73, 45, color="#b00020", ls=(0, (4, 3)), rad=0.0,
      label="tool == escalate() → Shell._escalate re-runs the SAME line on big_session",
      lx=0, ly=2.2, fs=8)

# tool execution into the shared executor
arrow(30, 41.2, 44, 14.3, color="#c77a21", rad=0.12, label="execute tool", lx=-3, ly=1.5)
arrow(73, 41.2, 66, 14.3, color="#c77a21", rad=-0.12)
arrow(55, 7.7, 55, 4.8, color="#c77a21")

# spawn/vibe/draw/ask are tools too — dispatched by the executor
arrow(80, 11, 86, 16.6, color="#c2374b", label="spawn/vibe/draw/ask", lx=-4, ly=2)

# sub-sessions reuse the 2B engine
arrow(90, 27.5, 90, 31.0, color="#6a4fa3", ls=(0, (2, 2)),
      label="sub-sessions run on :8080", lx=5.5, ly=0)

# replies & streaming events back to the daemon
arrow(33, 48.9, 50, 63.0, color="#888888", ls=(0, (2, 2)), rad=0.08,
      label="events / reply", lx=-1, ly=1)
arrow(74, 48.9, 70, 63.0, color="#888888", ls=(0, (2, 2)), rad=-0.08)

plt.savefig(OUT, dpi=150, bbox_inches="tight", facecolor="white")
print("wrote", OUT)
