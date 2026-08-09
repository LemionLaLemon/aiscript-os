#!/usr/bin/env python3
"""End-to-end smoke test: OOBE -> shell session -> a real task -> vibe."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tomllib

from daemon.server import Daemon

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def canned_ask(prompt, choices):
    print(f"   [fake ask] {prompt} -> {choices or 'free text'}")
    if "username" in prompt.lower() or "name" in prompt.lower():
        return "alex"
    if "chaos" in prompt.lower() or "chaotic" in prompt.lower():
        return "0.3"
    return "no"


def main():
    with open(os.path.join(ROOT, "config.toml"), "rb") as f:
        cfg = tomllib.load(f)
    cfg["chaos"]["p"] = 0.0  # deterministic test run

    d = Daemon(cfg)
    d.start()

    import time
    def show(ev):
        t = ev["type"]
        if t == "content":
            sys.stdout.write(ev["text"]); sys.stdout.flush()
        elif t == "tool":
            print(f"\n   [tool] {ev['name']}({ev['args']})", flush=True)

    t0 = time.time()
    print("== OOBE ==")
    d.run_oobe(canned_ask, on_event=show)
    if d.current_user is None:
        home = os.path.join(d.jail, "home")
        users = [u for u in os.listdir(home) if os.path.isdir(os.path.join(home, u))]
        with_dl = [u for u in users
                   if os.path.isdir(os.path.join(home, u, "Downloads"))]
        d.current_user = (with_dl or users or [None])[0]
    print(f"\n== OOBE done ({time.time()-t0:.0f}s), user:", d.current_user)

    sess = d.new_session("shell", temp=0.15)
    events = []

    def ev(e):
        events.append(e)

    t0 = time.time()
    print("== shell turn: list 5 biggest files in Downloads ==")
    out = sess.user_turn(
        "list the 5 biggest files in my Downloads folder, sorted by size",
        on_event=ev,
    )
    print(f"\n== done ({time.time()-t0:.0f}s) ==")
    print(out[-800:])

    tools_used = [e for e in events if e["type"] == "tool"]
    print("\n== tools called ==")
    for t in tools_used:
        print("   ", t["name"], t["args"])

    print("\n== vibe: install fastfetch ==")
    vout = d._handle_vibe("fastfetch", "install", [])
    print(vout[:300])
    pkgs = os.path.join(d.jail, "packages", "fastfetch")
    print("package dir exists:", os.path.isdir(pkgs), "->", sorted(os.listdir(pkgs)) if os.path.isdir(pkgs) else "n/a")

    print("\n== vibe: guard test (existing file, no flags) ==")
    print(d._handle_vibe(f"home/{d.current_user}/Documents/notes.txt",
                         "install", [])[:200])

    print("\n== spawn: run a jail app ==")
    sout = d._handle_spawn("du-sort", [])
    print(sout[:300])

    print("\n== shutdown refusal test ==")
    print(d.executor.shutdown()[:120])


if __name__ == "__main__":
    main()
