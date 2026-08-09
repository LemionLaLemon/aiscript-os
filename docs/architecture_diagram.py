"""Architecture diagram of as-os: how the as shell talks to the single 2B
"kernel-2" session, and how aiscript/vibe apps are "interpreted" by model
sub-sessions.

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

fig, ax = plt.subplots(figsize=(20, 15))
ax.set_xlim(0, 120)
ax.set_ylim(0, 84)
ax.axis("off")

APP = ("#dcebff", "#2b5c8f")   # shell / daemon
SES = ("#e7f0ff", "#3a6ea5")   # sessions / loops
MDL = ("#f0e9ff", "#6a4fa3")   # llama-server model process
TOL = ("#fff2e0", "#c77a21")   # tools / jail
APL = ("#ffe9ec", "#c2374b")   # aiscript / vibe
NOT = ("#f5f5f5", "#888888")   # notes / legend


def box(cx, cy, w, h, text, pal=NOT, fs=9, lw=1.5,
        style="round,pad=0.6,rounding_size=1.4"):
    fc, ec = pal
    b = FancyBboxPatch((cx - w / 2, cy - h / 2), w, h,
                       boxstyle=style, fc=fc, ec=ec, lw=lw, zorder=3)
    ax.add_patch(b)
    ax.text(cx, cy, text, ha="center", va="center", fontsize=fs,
            color="#0b0b0b", zorder=5, linespacing=1.45)


def arrow(x1, y1, x2, y2, color="#3a6ea5", ls="-", lw=1.8,
          connectionstyle="arc3,rad=0.0", label="", lx=0.0, ly=0.0, fs=8.5):
    a = FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=16,
                        color=color, lw=lw, linestyle=ls,
                        connectionstyle=connectionstyle, zorder=4)
    ax.add_patch(a)
    if label:
        ax.text((x1 + x2) / 2 + lx, (y1 + y2) / 2 + ly, label,
                ha="center", va="center", fontsize=fs, color=color,
                style="italic", zorder=6,
                bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none",
                          alpha=0.85))


ax.text(60, 81.5,
        "as-os — how the as shell, kernel-2, and the 'interpreters' fit together",
        ha="center", va="center", fontsize=14, fontweight="bold", color="#0b0b0b")

# ============================ main column ==================================
box(52, 76, 40, 5.5,
    "as shell  (shell/as_shell.py) — REPL at `as# `\n"
    "builtins handled locally: help · status · chaos · temp · reset · exit\n"
    "everything else → kernel-2 (a model session)",
    APP, fs=9.5)
box(52, 66.5, 44, 7,
    "Daemon  (daemon/server.py) — one process with the shell\n"
    "session registry · ModelEngine · ToolExecutor · Chaos gate\n"
    "system prompt = filesystem layout + policy.md (≈3,000 tok)\n"
    "persisted user: jail/etc/as-os/user",
    APP, fs=8.5)
box(52, 55.5, 40, 5.5,
    "Session \"shell\" → kernel-2 (Qwen3.5-2B)\n"
    "TOOLS: list · read · write · append · run · search · calc · info · ask\n"
    "       draw · spawn · vibe · shutdown · max_tokens=512",
    SES, fs=8.5)
box(52, 45, 40, 7.5,
    "Session._loop — up to 8 rounds\n"
    "engine.chat(_request_messages(), tools=TOOLS)\n"
    "→ llama-server :8080 (streaming)\n"
    "reply? → stream to REPL, done\n"
    "tool?  → execute, feed back, loop",
    SES, fs=8.5)
box(52, 33.5, 40, 5,
    "llama-server :8080 — Qwen3.5-2B (P-cores 0,2,4,6)\n"
    "single engine for shell, spawn, vibe · warm ≈ 3–6 s",
    MDL, fs=8.5)
box(52, 11, 44, 6.5,
    "ToolExecutor.execute(tool, args)  (daemon/tools.py)\n"
    "jail sandbox: paths resolve inside jail/ only — absolute paths refused\n"
    "offline only · chaos may mutate list/read/run/search (p from .asrc)",
    TOL, fs=8.5)
box(52, 2.5, 44, 4.5,
    "jail/  — the fake OS root: home/<user> · apps/ · packages/ · etc/as-os/\n"
    "every user-visible file lives here; the host filesystem is invisible",
    TOL, fs=8.5)

# ============================ right column =================================
box(99, 62, 38, 7,
    "why turns got fast — _request_messages()\n"
    "drops assistant tool-call messages on re-send and\n"
    "tags results \"[name] …\" so the model still knows\n"
    "what ran → llama.cpp prompt cache survives turns:\n"
    "follow-up 90 s → 2.4 s",
    NOT, fs=8)
box(99, 40, 38, 11.5,
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
box(99, 10, 38, 8,
    "legend\n"
    "  solid → tool call / data flow\n"
    "  gray dash → replies & events\n"
    "  purple = model server · orange = jail\n"
    "  blue = shell/daemon · light blue = session\n"
    "  pink = aiscript / vibe sub-sessions",
    NOT, fs=8)

# ============================ arrows ========================================
arrow(52, 73.3, 52, 70.0, label="input line", ly=-0.5)
arrow(64, 70.1, 64, 73.3, color="#888888", ls=(0, (2, 2)), label="reply / events", ly=0.5)
arrow(52, 63.0, 52, 58.4, label="new_session(\"shell\")", ly=0.5)
arrow(52, 52.7, 52, 48.9)
arrow(52, 41.2, 52, 36.1, color="#6a4fa3",
      label="POST /v1/chat/completions (stream)", ly=2)
arrow(52, 7.7, 52, 4.8, color="#c77a21")

# tool call path: elbow out into the left gutter, down, then into the executor
arrow(32, 43, 30, 14.3, color="#c77a21",
      connectionstyle="angle3,angleA=180,angleB=-90",
      label="execute tool", lx=-8, ly=-1)

# events/replies: same gutter, elbow up into the daemon
arrow(32, 47, 32, 63.0, color="#888888", ls=(0, (2, 2)),
      connectionstyle="angle3,angleA=180,angleB=90",
      label="events / reply", lx=-8, ly=1)

# spawn/vibe/draw/ask dispatched by the executor, then sub-sessions on :8080
arrow(74, 13, 80, 42, color="#c2374b", connectionstyle="arc3,rad=-0.05",
      label="spawn/vibe/draw/ask", lx=7, ly=2)
arrow(86, 34.2, 68, 31.0, color="#6a4fa3", ls=(0, (2, 2)),
      connectionstyle="arc3,rad=0.0", label="sub-sessions run on :8080", lx=5, ly=2)

plt.savefig(OUT, dpi=150, bbox_inches="tight", facecolor="white")
print("wrote", OUT)
