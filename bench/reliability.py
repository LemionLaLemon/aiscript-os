#!/usr/bin/env python3
"""Phase-2 reliability battery. Cases 1-3 run real sessions against a live
llama-server and score answers against ground truth from the jail. The
repeat-guard case is a deterministic fake-engine unit check (no server)."""
import csv
import os
import re
import sys
import json
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("AS_NO_WARMUP", "1")   # keep bench timings pure

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
    csv_path = None
    port = None
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--port" and i + 1 < len(args):
            port = int(args[i + 1]); i += 2
        elif args[i] == "--csv" and i + 1 < len(args):
            csv_path = args[i + 1]; i += 2
        else:
            i += 1

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

    results = {}
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
                results[label] = "pass" if ok else "fail"
                print(f"[{'PASS' if ok else 'FAIL'}] {label}: missing={missing}")
            except Exception as e:
                results[label] = "fail"
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
            results["total"] = "pass" if ok else "fail"
            print(f"[{'PASS' if ok else 'FAIL'}] total: expected {total} "
                  f"in answer (len={len(ans)})")
        except Exception as e:
            results["total"] = "fail"
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
        def __init__(self, text_calls=False, varying=False):
            self.n = 0
            self.cfg = {}
            self.text_calls = text_calls
            self.varying = varying

        def chat(self, messages, **kw):
            self.n += 1
            if kw.get("tool_choice") == "none":
                return {"role": "assistant",
                        "content": "I used the existing result: 4"}
            path = f"file-{self.n}.txt" if self.varying else "same.txt"
            if self.text_calls:
                return {"role": "assistant",
                        "content": f"read(path=\"{path}\")"}
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "id": f"c{self.n}",
                    "function": {"name": "read",
                                 "arguments": json.dumps({"path": path})},
                }],
            }

    class FakeExec:
        def __init__(self):
            self.executed = []

        def execute(self, tool, args, chrooted=False):
            self.executed.append((tool, args))
            return "4"

    guard_passes = []
    for label, text_calls in (("structured", False), ("text fallback", True)):
        fake_engine = FakeEngine(text_calls=text_calls)
        fake_exec = FakeExec()
        sess = Session(fake_engine, fake_exec, system_prompt="sys")
        sess.max_loops = 5
        out = sess.user_turn("hi", on_event=lambda e: None)
        steered = sum(
            1 for m in sess.messages
            if m.get("role") == "tool"
            and "[repeated call #" in m.get("content", "")
        )
        ok = (steered == 1 and len(fake_exec.executed) == 1
              and fake_engine.n == 3
              and out == "I used the existing result: 4")
        guard_passes.append(ok)
        print(f"[{'PASS' if ok else 'FAIL'}] {label}: "
              f"executed={len(fake_exec.executed)} steered={steered} "
              f"engine_calls={fake_engine.n} out={out!r}")
    fake_engine = FakeEngine(varying=True)
    fake_exec = FakeExec()
    sess = Session(fake_engine, fake_exec, system_prompt="sys")
    sess.max_loops = 5
    out = sess.user_turn("hi", on_event=lambda e: None)
    varying_ok = (len(fake_exec.executed) == 5
                  and out == "(agent loop ran too long; giving up)")
    guard_passes.append(varying_ok)
    print(f"[{'PASS' if varying_ok else 'FAIL'}] legitimate repeated tool: "
          f"executed={len(fake_exec.executed)} out={out!r}")

    from daemon.model import ModelEngine
    payload_engine = ModelEngine({
        "host": "127.0.0.1", "port": 1, "model_name": "test",
    })
    payload = payload_engine._payload(
        [], [], 0.1, 0, 32, "auto", reasoning_budget=7)
    budget_ok = (payload.get("reasoning_budget_tokens") == 7
                 and "reasoning_budget" not in payload
                 and payload.get("parallel_tool_calls") is None)
    guard_passes.append(budget_ok)
    print(f"[{'PASS' if budget_ok else 'FAIL'}] reasoning budget payload: "
          f"{payload.get('reasoning_budget_tokens')!r}")
    tool_payload = payload_engine._payload(
        [], [{"type": "function", "function": {"name": "list"}}],
        0.1, 0, 32, "required", reasoning_budget=7)
    serial_tools_ok = tool_payload.get("parallel_tool_calls") is False
    guard_passes.append(serial_tools_ok)
    print(f"[{'PASS' if serial_tools_ok else 'FAIL'}] serial tool calls: "
          f"{tool_payload.get('parallel_tool_calls')!r}")

    # Raw user input must reach the shell AI. In particular, BusyBox `ls`
    # must never be mistaken for an aiscript app and spawned by the REPL.
    from daemon.server import Daemon
    resolver = Daemon(CFG)
    resolver.current_user = USER
    man_app = resolver._resolve_app("man")
    routing_ok = (resolver._resolve_app("ls") is None
                  and resolver._resolve_app("/bin/ls") is None
                  and man_app is not None and man_app.endswith(".as"))
    guard_passes.append(routing_ok)
    print(f"[{'PASS' if routing_ok else 'FAIL'}] AI-first input routing: "
          f"ls={resolver._resolve_app('ls')!r}, man={man_app!r}")

    class FastListEngine:
        cfg = {}
        def __init__(self):
            self.calls = []
        def chat(self, messages, **kw):
            self.calls.append((messages, kw.get("tools"),
                               kw.get("tool_choice")))
            if kw.get("tool_choice") == "none":
                return {"role": "assistant",
                        "content": "I found these delightful little files: 4"}
            return {
                "role": "assistant", "content": None,
                "tool_calls": [{
                    "id": "list1",
                    "function": {"name": "list",
                                 "arguments": json.dumps({"path": "."})},
                }],
            }
    fast_engine = FastListEngine()
    fast_exec = FakeExec()
    fast_sess = Session(fast_engine, fast_exec, system_prompt="large policy")
    fast_out = fast_sess.user_turn("ls", on_event=lambda e: None)
    fast_ok = (len(fast_engine.calls) == 2
               and len(fast_engine.calls[0][1]) == 1
               and fast_engine.calls[0][1][0]["function"]["name"] == "list"
               and fast_exec.executed == [("list", {"path": "home/user"})]
               and fast_engine.calls[1][1] == []
               and fast_engine.calls[1][2] == "none"
               and fast_out == "I found these delightful little files: 4")
    guard_passes.append(fast_ok)
    print(f"[{'PASS' if fast_ok else 'FAIL'}] AI-composed list: "
          f"model_calls={len(fast_engine.calls)}, "
          f"tools={fast_exec.executed}, out={fast_out!r}")
    results["guard"] = "pass" if all(guard_passes) else "fail"

    if csv_path:
        os.makedirs(os.path.dirname(csv_path) or ".", exist_ok=True)
        file_exists = os.path.exists(csv_path)
        with open(csv_path, "a", newline="") as f:
            w = csv.writer(f)
            if not file_exists:
                w.writerow(["date", "model", "build", "backend", "temp",
                            "bench_tools_raw", "bench_tools_valid", "reliability",
                            "rel_five", "rel_ten", "rel_total", "rel_guard",
                            "prefill_tokps", "decode_tokps", "notes"])
            model_name = os.path.basename(CFG["llama"].get("model_path", ""))
            rel_score = sum(1 for v in results.values() if v == "pass")
            w.writerow([
                time.strftime("%Y-%m-%d"),
                model_name,
                "llama-b10333 CPU",
                "CPU",
                CFG["daemon"].get("temp", 0.15),
                "", "",
                f"{rel_score}/4",
                results.get("five", ""),
                results.get("ten", ""),
                results.get("total", ""),
                results.get("guard", ""),
                "", "",
                "",
            ])
        print(f"[csv] appended to {csv_path}")


if __name__ == "__main__":
    main()
