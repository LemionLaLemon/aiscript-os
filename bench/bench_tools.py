#!/usr/bin/env python3
"""Tool-call benchmark: does the model emit well-formed tool calls for the
exact prompts the OS will use? Run against a live llama-server."""
import json
import os
import sys

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


def main():
    port = None
    if "--port" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])
    with open(os.path.join(ROOT, "config.toml"), "rb") as f:
        cfg = tomllib.load(f)
    if port:
        cfg["llama"]["port"] = port
        cfg["llama"]["host"] = "127.0.0.1"
    engine = ModelEngine(cfg["llama"])
    if not engine.ping():
        print("llama-server not running. start it first:\n  scripts/start-server.sh")
        sys.exit(1)

    total = correct = 0
    for label, tools, user in TASKS:
        total += 1
        try:
            msg = engine.chat(
                [{"role": "system",
                  "content": "You are the OS. Call tools when useful."},
                 {"role": "user", "content": user}],
                tools=tools, temp=0.15,
            )
        except Exception as e:
            print(f"[{label}] FAIL: {e}")
            continue
        tcs = msg.get("tool_calls")
        if tcs:
            parsed = all(
                json.loads(tc["function"]["arguments"]) is not None
                for tc in tcs
            )
            ok = parsed
            detail = json.dumps([
                (tc["function"]["name"], tc["function"]["arguments"])
                for tc in tcs
            ], ensure_ascii=False)[:200]
        else:
            ok = False
            detail = f"no tool call; content={msg.get('content','')[:80]!r}"
        correct += ok
        print(f"[{'PASS' if ok else 'FAIL'}] {label}: {detail}")

    print(f"\n{correct}/{total} tasks produced well-formed tool calls")


if __name__ == "__main__":
    main()
