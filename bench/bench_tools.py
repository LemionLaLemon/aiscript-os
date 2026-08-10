#!/usr/bin/env python3
"""Tool-call benchmark: does the model emit well-formed tool calls for the
exact prompts the OS will use? Run against a live llama-server."""
import csv
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tomllib

from daemon.model import ModelEngine

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TASKS = [
    ("list big files", [
        {"type": "function", "function": {
            "name": "list",
            "parameters": {"type": "object", "properties": {
                "path": {"type": "string"}, "sort": {"type": "string"},
                "top": {"type": "integer"}}, "required": ["path"]},
        }},
    ], "list the 20 biggest files in my Downloads folder"),
    ("read a file", [
        {"type": "function", "function": {
            "name": "read",
            "parameters": {"type": "object", "properties": {
                "path": {"type": "string"}}, "required": ["path"]},
        }},
    ], "show me the contents of welcome.txt"),
    ("two tools", [
        {"type": "function", "function": {
            "name": "list",
            "parameters": {"type": "object", "properties": {
                "path": {"type": "string"}}, "required": ["path"]},
        }},
        {"type": "function", "function": {
            "name": "run",
            "parameters": {"type": "object", "properties": {
                "command": {"type": "string"}}, "required": ["command"]},
        }},
    ], "how much memory do we have? use run() to check"),
    ("plain chat, no tools", [
        {"type": "function", "function": {
            "name": "list",
            "parameters": {"type": "object", "properties": {
                "path": {"type": "string"}}, "required": ["path"]},
        }},
    ], "hello, what can you do?"),
]

MINIMAL_PROMPT = "You are the OS. Call tools when useful."


def main():
    port = None
    csv_path = None
    use_daemon_prompt = False
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--port" and i + 1 < len(args):
            port = int(args[i + 1]); i += 2
        elif args[i] == "--csv" and i + 1 < len(args):
            csv_path = args[i + 1]; i += 2
        elif args[i] == "--prompt" and i + 1 < len(args):
            use_daemon_prompt = args[i + 1] == "daemon"; i += 2
        else:
            i += 1

    with open(os.path.join(ROOT, "config.toml"), "rb") as f:
        cfg = tomllib.load(f)
    if port:
        cfg["llama"]["port"] = port
        cfg["llama"]["host"] = "127.0.0.1"

    if use_daemon_prompt:
        from daemon.prompt import build_shell_prompt
        system_content = build_shell_prompt(cfg)
    else:
        system_content = MINIMAL_PROMPT

    engine = ModelEngine(cfg["llama"])
    if not engine.ping():
        print("llama-server not running. start it first:\n  scripts/start-server.sh")
        sys.exit(1)

    total = correct = 0
    results = []
    for label, tools, user in TASKS:
        total += 1
        try:
            msg = engine.chat(
                [{"role": "system", "content": system_content},
                 {"role": "user", "content": user}],
                tools=tools, temp=0.15,
            )
        except Exception as e:
            print(f"[{label}] FAIL: {e}")
            results.append({"label": label, "ok": False, "detail": str(e)})
            continue
        tcs = msg.get("tool_calls")
        no_tool_ok = "no tools" in label
        if tcs:
            parsed = all(
                json.loads(tc["function"]["arguments"]) is not None
                for tc in tcs
            )
            ok = parsed and not no_tool_ok
            detail = json.dumps([
                (tc["function"]["name"], tc["function"]["arguments"])
                for tc in tcs
            ], ensure_ascii=False)[:200]
        else:
            ok = no_tool_ok
            detail = f"no tool call; content={msg.get('content','')[:80]!r}"
        correct += ok
        results.append({"label": label, "ok": ok, "detail": detail})
        print(f"[{'PASS' if ok else 'FAIL'}] {label}: {detail}")

    print(f"\n{correct}/{total} tasks produced well-formed tool calls")

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
            model_name = os.path.basename(cfg["llama"].get("model_path", ""))
            valid_tools = sum(1 for r in results
                              if r["ok"] and r["label"] != "plain chat, no tools")
            w.writerow([
                time.strftime("%Y-%m-%d"),
                model_name,
                "llama-b10333 CPU",
                "CPU",
                cfg["daemon"].get("temp", 0.15),
                f"{correct}/{total}",
                f"{valid_tools}/3",
                "", "", "", "", "",
                "", "",
                f"--prompt daemon" if use_daemon_prompt else "",
            ])
        print(f"[csv] appended to {csv_path}")


if __name__ == "__main__":
    main()
