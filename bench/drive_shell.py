#!/usr/bin/env python3
"""Drive the real daemon shell with LFM 2.5 8B and log every event.

Usage: python3 bench/drive_shell.py [task]...
Tasks: list, cd, vibe, notepad, runas, question, sysinfo, all
"""
import os
import sys
import json
import time
import threading
import tomllib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from daemon.server import Daemon


def load_cfg():
    with open(os.path.join(ROOT, "config.toml"), "rb") as f:
        return tomllib.load(f)


TASKS = {
    "list": "list all the files and folders in the current directory",
    "cd": "go into my Documents folder",
    "vibe": "vibe install cowsay",
    "notepad": "open notepad and edit the file Documents/notes.txt",
    "runas": "run the script Documents/hello.as",
    "question": "why is the sky blue?",
    "sysinfo": "show me system info",
}

TASK_TIMEOUT = 120


def main():
    tasks = sys.argv[1:] or ["all"]
    if "all" in tasks:
        tasks = list(TASKS)

    cfg = load_cfg()
    daemon = Daemon(cfg)
    daemon._load_persisted_user()
    if not daemon.current_user:
        daemon.current_user = "demo"
        daemon.executor.current_user = "demo"
        daemon.store.user = "demo"
    print(f"[harness] user={daemon.current_user} engine={daemon.engine.ping()}",
          flush=True)

    for task in tasks:
        text = TASKS[task]
        sess = daemon.new_session(f"test:{task}", temp=0.2, max_tokens=2048)
        calls = []
        phases = []
        think_chars = [0]
        content_chars = [0]

        def on_event(ev):
            t = ev.get("type")
            if t == "tool":
                calls.append(ev["name"])
                print(f"    [tool] {ev['name']}({json.dumps(ev.get('args', {}))})",
                      flush=True)
            elif t == "phase":
                phases.append(ev.get("state", ""))
                print(f"    [phase] {ev.get('state')}", flush=True)
            elif t == "thinking":
                think_chars[0] += len(ev.get("text", ""))
            elif t == "content":
                content_chars[0] += len(ev.get("text", ""))

        t0 = time.time()
        print(f"\n=== TASK: {task} :: {text} ===", flush=True)

        result_box = {}

        def run():
            try:
                result_box["r"] = sess.user_turn(text, on_event=on_event)
            except Exception as e:
                result_box["e"] = e

        th = threading.Thread(target=run, daemon=True)
        th.start()
        th.join(timeout=TASK_TIMEOUT)
        dt = time.time() - t0

        if th.is_alive():
            print(f"[TIMEOUT after {TASK_TIMEOUT}s]", flush=True)
        if "e" in result_box:
            print(f"[EXC] {result_box['e']!r}", flush=True)
        result = result_box.get("r")
        if result is not None:
            print(f"--- result ({dt:.0f}s, think {think_chars[0]}ch, "
                  f"content {content_chars[0]}ch) ---", flush=True)
            print(result[:1200], flush=True)
        print(f"[summary] {task}: {len(calls)} tool calls: "
              + (" -> ".join(calls) if calls else "NONE"), flush=True)
        print(f"[summary] phases: {' -> '.join(phases)}", flush=True)
        try:
            daemon.delete_session(sess.name)
        except Exception:
            pass


if __name__ == "__main__":
    main()
