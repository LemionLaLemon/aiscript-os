#!/usr/bin/env python3
"""Phase-2 reliability battery. Cases 1-3 run real sessions against a live
llama-server and score answers against ground truth from the jail. The
repeat-guard case is a deterministic fake-engine unit check (no server)."""
import os
import re
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tomllib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(ROOT, "config.toml"), "rb") as f:
    CFG = tomllib.load(f)

JAIL = os.path.realpath(CFG["daemon"]["jail"])
USER = "demo"
DOWNLOADS = os.path.join(JAIL, "home", USER, "Downloads")


def top_sizes(n):
    files = []
    for name in os.listdir(DOWNLOADS):
        p = os.path.join(DOWNLOADS, name)
        if os.path.isfile(p):
            files.append((name, os.path.getsize(p)))
    files.sort(key=lambda x: -x[1])
    return files[:n]


def answer_missing_files(answer, names):
    return [n for n in names if n not in answer]


def answer_has_int(answer, value):
    ints = [int(m) for m in re.findall(r"\d+", answer.replace(",", ""))]
    return value in ints


def run_case(daemon, task):
    sess = daemon.new_session(f"bench-{task[0]}")
    out = sess.user_turn(task[1], on_event=lambda e: None)
    print(f"  --- answer: {out[:300]!r}")
    return out


def main():
    guard_only = "--guard-only" in sys.argv
    port = None
    if "--port" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])
    if port:
        CFG["llama"]["port"] = port
        CFG["llama"]["host"] = "127.0.0.1"
    daemon = None
    if not guard_only and os.path.exists(DOWNLOADS):
        from daemon.server import Daemon

        daemon = Daemon(CFG)
        daemon.current_user = USER
        try:
            daemon.start()
        except RuntimeError as e:
            print(f"[SKIP live cases] {e}")
            daemon = None

    if daemon:
        cases = [
            ("five", 5),
            ("ten", 10),
        ]
        for label, n in cases:
            ok = ans = None
            try:
                ans = run_case(daemon, (
                    label,
                    f"list the {n} biggest files in ~/Downloads and name all {n}",
                ))
                top = top_sizes(n)
                missing = answer_missing_files(ans, [t[0] for t in top])
                ok = not missing
                print(f"[{'PASS' if ok else 'FAIL'}] {label}: missing={missing}")
            except Exception as e:
                print(f"[FAIL] {label}: {e}")
        # total-size case
        try:
            ans = run_case(daemon, (
                "total",
                "list the 5 biggest files in ~/Downloads and tell me the total "
                "size of those five, in bytes",
            ))
            total = sum(s for _, s in top_sizes(5))
            ok = answer_has_int(ans, total)
            print(f"[{'PASS' if ok else 'FAIL'}] total: expected {total} "
                  f"in answer (len={len(ans)})")
        except Exception as e:
            print(f"[FAIL] total: {e}")
    elif not guard_only:
        print("[SKIP live cases] no demo Downloads dir")

    if guard_only:
        print("(live cases skipped)")

    # repeat-guard unit check (no server needed)
    print("\nrepeat-guard (fake engine):")
    sys.path.insert(0, ROOT)
    from daemon.session import Session

    class FakeEngine:
        def __init__(self):
            self.n = 0

        def chat(self, messages, **kw):
            self.n += 1
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "id": f"c{self.n}",
                    "function": {"name": "calc",
                                 "arguments": json.dumps(
                                     {"expr": f"{self.n}+{self.n}"})},
                }],
            }

    class FakeExec:
        def __init__(self):
            self.executed = []

        def execute(self, tool, args):
            self.executed.append((tool, args))
            return "4"

    fake_engine = FakeEngine()
    fake_exec = FakeExec()
    sess = Session(fake_engine, fake_exec, system_prompt="sys")
    sess.max_loops = 5
    out = sess.user_turn("hi", on_event=lambda e: None)
    steered = sum(
        1 for m in sess.messages
        if m.get("role") == "tool" and "[repeated call]" in m.get("content", "")
    )
    if steered == 3 and len(fake_exec.executed) == 2:
        print(f"[PASS] 3 identical-tool calls steered after 2 real executions "
              f"({len(fake_exec.executed)} executed, {steered} steers)")
    else:
        print(f"[FAIL] executed={len(fake_exec.executed)} steered={steered} "
              f"engine_calls={fake_engine.n} out={out!r}")


if __name__ == "__main__":
    main()
