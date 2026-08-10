#!/usr/bin/env python3
"""Run the full quality + speed bench for ONE server config at a time.

Usage:
  python3 bench/one_config.py --label "baseline" \
      [--model models/LFM2.5-8B-A1B-Q4_K_M.gguf] \
      [--draft models/LFM2.5-1.2B-Instruct-Q4_K_M.gguf] \
      [--spec-n-max 6] [--port 8090] [--csv benchmarks/results.csv]

Starts the llama-server (single config), waits for health, runs:
  1. bench_tools.py --prompt daemon   (tool-call quality)
  2. reliability.py                   (answer quality)
  3. timed 600-token completion       (speed: effective tok/s)
Then kills the server. Records everything to the CSV with a notes column.
"""
import argparse
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(ROOT, "tools", "llama.cpp", "llama-b10333")


def wait_health(port, timeout=90):
    import urllib.request
    start = time.time()
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/health", timeout=2
            ) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(2)
    return False


def speed(port, n=600):
    import json
    import urllib.request
    body = {
        "prompt": "Count from 1 to 300, listing every number on its own line.",
        "n_predict": n,
        "temperature": 0.0,
        "stream": False,
        "cache_prompt": True,
    }
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/completion",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=600) as r:
        d = json.load(r)
    t = d.get("timings", {})
    pred = t.get("predicted_n", 0)
    ms = t.get("predicted_ms")
    tok_s = (pred / (ms / 1000)) if ms else 0.0
    pre_ms = t.get("prompt_ms")
    prompt_n = t.get("prompt_n", 0)
    pre_tok_s = (prompt_n / (pre_ms / 1000)) if pre_ms else 0.0
    return {"decode_tokps": round(tok_s, 2),
            "prefill_tokps": round(pre_tok_s, 2)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--model", default="models/LFM2.5-8B-A1B-Q4_K_M.gguf")
    ap.add_argument("--draft", default=None)
    ap.add_argument("--spec-n-max", type=int, default=0)
    ap.add_argument("--port", type=int, default=8090)
    ap.add_argument("--csv", default="benchmarks/results.csv")
    ap.add_argument("--skip-quality", action="store_true")
    args = ap.parse_args()

    model = os.path.join(ROOT, args.model)
    cmd = ["taskset", "-c", "0,2,4,6",
           "env", f"LD_LIBRARY_PATH={BIN}",
           os.path.join(BIN, "llama-server"),
           "-m", model,
           "-c", "8192", "-t", "4", "--parallel", "1",
           "-ctk", "q8_0", "-ctv", "q8_0",
           "--host", "127.0.0.1", "--port", str(args.port),
           "--no-webui", "--log-disable"]
    if args.draft:
        cmd += ["-md", os.path.join(ROOT, args.draft)]
    if args.spec_n_max:
        cmd += ["--spec-draft-n-max", str(args.spec_n_max)]

    logf = open(f"/tmp/asbench_{args.port}.log", "w")
    print(f"[{args.label}] starting server on :{args.port} ...")
    proc = subprocess.Popen(cmd, stdout=logf, stderr=logf,
                            stdin=subprocess.DEVNULL,
                            start_new_session=True)
    try:
        if not wait_health(args.port):
            print("ERROR: server never became healthy")
            print(open(f"/tmp/asbench_{args.port}.log").read()[-2000:])
            sys.exit(1)
        print(f"[{args.label}] server up")

        notes = [args.label]

        # 1. tool-call quality
        tools_out = subprocess.run(
            [sys.executable, "bench/bench_tools.py", "--port", str(args.port),
             "--prompt", "daemon"],
            cwd=ROOT, capture_output=True, text=True, timeout=300,
        )
        tools_txt = tools_out.stdout
        print(tools_txt)
        m = [ln for ln in tools_txt.splitlines() if "/" in ln
             and "tasks produced" in ln]
        notes.append("tools=" + (m[0].split(" ")[0] if m else "ERR"))

        # 2. answer quality (reliability)
        if not args.skip_quality:
            rel_out = subprocess.run(
                [sys.executable, "bench/reliability.py", "--port",
                 str(args.port)],
                cwd=ROOT, capture_output=True, text=True, timeout=600,
            )
            rel_txt = rel_out.stdout
            print(rel_txt)
            for ln in rel_txt.splitlines():
                if ln.startswith("[PASS]") or ln.startswith("[FAIL]"):
                    notes.append(ln[:60])

        # 3. speed
        sp = speed(args.port)
        print(f"[{args.label}] prefill={sp['prefill_tokps']} tok/s "
              f"decode={sp['decode_tokps']} tok/s")
        notes.append(f"prefill={sp['prefill_tokps']} decode={sp['decode_tokps']}")

        # append to CSV
        csv_path = os.path.join(ROOT, args.csv)
        exists = os.path.exists(csv_path)
        with open(csv_path, "a") as f:
            if not exists:
                f.write("date,label,config,bench_tools,reliability,"
                        "prefill_tokps,decode_tokps,notes\n")
            date = time.strftime("%Y-%m-%d")
            config = (f"model={os.path.basename(model)}"
                      + (f" draft={os.path.basename(args.draft)}"
                         f" nmax={args.spec_n_max}" if args.draft else ""))
            f.write(f"{date},{args.label},{config},{'; '.join(notes)},\n")
        print(f"[{args.label}] CSV row appended to {args.csv}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        logf.close()
        print(f"[{args.label}] server stopped")


if __name__ == "__main__":
    main()
