#!/usr/bin/python3
"""ascOS engine health check. Exits 0 when the engine answers /health."""
import sys
try:
    import requests
except ImportError:
    print("requests not installed", file=sys.stderr)
    sys.exit(1)
port = sys.argv[1] if len(sys.argv) > 1 else "8080"
try:
    r = requests.get(f"http://127.0.0.1:{port}/health", timeout=2)
    sys.exit(0 if r.ok else 1)
except Exception as e:
    print(f"health check failed: {e}", file=sys.stderr)
    sys.exit(1)
