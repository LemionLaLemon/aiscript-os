import ast
import math
import os
import resource
import shlex
import shutil
import subprocess
import time

# ---------------------------------------------------------------- schemas ---

_SHELL_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "list",
            "description": "List files/dirs in a path. sort=size|name|mtime|none. "
                           "top=N limits entries. filter is a glob. recursive walks subdirs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "directory"},
                    "sort": {"type": "string", "enum": ["size", "name", "mtime", "none"]},
                    "top": {"type": "integer"},
                    "filter": {"type": "string"},
                    "recursive": {"type": "boolean"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read",
            "description": "Read text from a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "start_line": {"type": "integer"},
                    "max_lines": {"type": "integer"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write",
            "description": "Create or overwrite a text file (aiscript/data only).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "append",
            "description": "Append text to a file (create if missing).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run",
            "description": "Run a shell command in the sandboxed busybox shell.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": "Search files for text matching a pattern.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "pattern": {"type": "string"},
                    "regex": {"type": "boolean"},
                },
                "required": ["path", "pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calc",
            "description": "Evaluate a math expression.",
            "parameters": {
                "type": "object",
                "properties": {"expr": {"type": "string"}},
                "required": ["expr"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "info",
            "description": "System info: memory, disk, cpu, uptime.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask",
            "description": "Ask the user a question. choices is an optional list.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "choices": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "draw",
            "description": "Render a UI panel with asui: {'title','lines','boxes','status'}.",
            "parameters": {
                "type": "object",
                "properties": {
                    "spec": {"type": "object"},
                    "clear": {"type": "boolean"},
                },
                "required": ["spec"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "spawn",
            "description": "Run an aiscript app in its own sub-session.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app": {"type": "string"},
                    "args": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["app"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "vibe",
            "description": "Package manager. Vibecodes an aiscript package into /packages.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "string"},
                    "action": {"type": "string", "enum": ["install", "list", "remove", "update"]},
                    "flags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["target", "action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "interpret",
            "description": "Delegate a task (plain-English goal) to the interpreter layer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "request": {"type": "string"},
                },
                "required": ["request"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete",
            "description": "Delete a file or empty directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "move",
            "description": "Move or rename a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "src": {"type": "string"},
                    "dst": {"type": "string"},
                },
                "required": ["src", "dst"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "copy",
            "description": "Copy a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "src": {"type": "string"},
                    "dst": {"type": "string"},
                },
                "required": ["src", "dst"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mkdir",
            "description": "Create a directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cd",
            "description": "Change the working directory. '.'=current, '..'=up, '~'=home.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pwd",
            "description": "Print the current working directory.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "shutdown",
            "description": "Shut the system down. Refuses if uptime < 2 minutes.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_user",
            "description": "Create a user account and home directory. First-boot only.",
            "parameters": {
                "type": "object",
                "properties": {
                    "username": {"type": "string"},
                    "password": {"type": "string"},
                },
                "required": ["username"],
            },
        },
    },
]

_INTERPRETER_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "run",
            "description": "Run a command in the busybox shell. You are chrooted in the sandbox.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list",
            "description": "List files/dirs in a path. sort=size|name|mtime|none. top=N limits.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "directory"},
                    "sort": {"type": "string", "enum": ["size", "name", "mtime", "none"]},
                    "top": {"type": "integer"},
                    "filter": {"type": "string"},
                    "recursive": {"type": "boolean"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read",
            "description": "Read text from a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "start_line": {"type": "integer"},
                    "max_lines": {"type": "integer"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write",
            "description": "Create or overwrite a text file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "append",
            "description": "Append text to a file (create if missing).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": "Search files for text matching a pattern.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "pattern": {"type": "string"},
                    "regex": {"type": "boolean"},
                },
                "required": ["path", "pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calc",
            "description": "Evaluate a math expression.",
            "parameters": {
                "type": "object",
                "properties": {"expr": {"type": "string"}},
                "required": ["expr"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "info",
            "description": "System info: memory, disk, cpu, uptime.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask",
            "description": "Ask the user a question. Use for interactive loops and clarifying inputs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "choices": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "draw",
            "description": "Render a UI panel with asui: {'title','lines','boxes','status'}.",
            "parameters": {
                "type": "object",
                "properties": {
                    "spec": {"type": "object"},
                    "clear": {"type": "boolean"},
                },
                "required": ["spec"],
            },
        },
    },
]

TOOLS = [t for t in _SHELL_TOOL_SCHEMAS if t["function"]["name"] != "interpret"]
TOOLS = [t for t in TOOLS if t["function"]["name"] != "delete"]
TOOLS = [t for t in TOOLS if t["function"]["name"] != "move"]
TOOLS = [t for t in TOOLS if t["function"]["name"] != "copy"]
TOOLS = [t for t in TOOLS if t["function"]["name"] != "mkdir"]

SHELL_TOOLS = _SHELL_TOOL_SCHEMAS
INTERPRETER_TOOLS = _INTERPRETER_TOOL_SCHEMAS

# Tool names that only make sense interactively; sub-sessions get a stub.
INTERACTIVE_TOOLS = {"ask", "draw", "shutdown"}

# ---------------------------------------------------------------- helpers ---

BANNED_LANG = {
    "python", "python3", "py", "gcc", "cc", "clang", "g++", "node", "nodejs",
    "npm", "npx", "perl", "ruby", "php", "cargo", "rustc", "go", "java",
    "javac", "make", "cmake", "ld", "as", "gdb",
}
BANNED_NET = {
    "curl", "wget", "ping", "nc", "ncat", "socat", "ssh", "telnet", "nmap",
    "ftp", "python3-m http.server", "ip", "iwconfig", "wpa_supplicant",
}
BANNED_DESTRUCTIVE = {
    "rm", "rmdir", "mkfs", "mkfs.ext4", "dd", "fdisk", "mount", "umount",
    "chown", "chmod", "shutdown", "reboot", "poweroff", "halt", "kill",
    "pkill", "killall", "sudo", "su", "passwd", "usermod", "userdel",
    "git clone", "cryptsetup", "dmesg", "insmod", "rmmod",
}

BANNED_FILE_EXT = {
    ".py", ".pyc", ".pyw", ".c", ".h", ".cpp", ".cc", ".cxx", ".hpp", ".js",
    ".ts", ".rs", ".go", ".java", ".rb", ".pl", ".php", ".sh", ".bash",
    ".zsh", ".ksh", ".fish", ".asm", ".s", ".swift", ".kt", ".lua", ".ex",
    ".exs", ".cs", ".zig", ".v", ".erl", ".clj", ".scala",
}
MAX_WRITE_BYTES = 200_000
MAX_RESULT_CHARS = 4000


class ToolRefusal(Exception):
    pass


# ---- chroot runner for interpreter ----------------------------------------

def _chroot_run(jail, command, cwd="."):
    """Run command chrooted inside jail using unshare -r (user namespace).
    `cwd` is a jail-relative path (e.g. 'home/demo/Documents'); inside the
    chroot that is an absolute path rooted at '/'. Empty cwd = jail root."""
    env = {
        "PATH": "/bin:/usr/bin:/sbin:/usr/sbin",
        "HOME": "/home",
        "TERM": "dumb",
        "LANG": "C",
    }
    env_str = " ".join(f'{k}="{v}"' for k, v in env.items())
    chroot_cwd = "/" + str(cwd).lstrip("/") if str(cwd).strip() else "/"
    # Build a single shell script that cds then runs the command. We hand the
    # script to /bin/sh via a file-less stdin-free form: use sh -c with the
    # script quoted with double quotes and escaped, to avoid the nested
    # single-quote breakage that previously split the command mid-way.
    script = f"cd {shlex.quote(chroot_cwd)} && {command}"
    try:
        proc = subprocess.run(
            ["unshare", "--user", "--map-root-user",
             "chroot", jail, "/bin/sh", "-c",
             f"{env_str} /bin/sh -c {shlex.quote(script)}"],
            capture_output=True, timeout=10,
            preexec_fn=_limit_rlimits,
        )
        out = proc.stdout.decode(errors="replace")
        err = proc.stderr.decode(errors="replace")
        tail = f"{out}\n{err}".strip()
        if len(tail) > MAX_RESULT_CHARS:
            tail = tail[:MAX_RESULT_CHARS] + "\n...[truncated]"
        return f"[exit {proc.returncode}]\n{tail}" if tail else f"[exit {proc.returncode}]"
    except subprocess.TimeoutExpired:
        return "[run timed out after 10s]"
    except FileNotFoundError:
        return "[chroot: unshare not available — run scripts/setup-jail.sh first]"


# ---------------------------------------------------------------- executor ---

class ToolExecutor:
    """Runs parsed tool calls against a sandboxed jail filesystem."""

    def __init__(self, cfg, handlers=None):
        self.cfg = cfg
        self.jail = os.path.realpath(cfg["daemon"]["jail"])
        os.makedirs(self.jail, exist_ok=True)
        self.handlers = handlers or {}
        self.current_user = None

    # ---- paths ------------------------------------------------------------

    def _jail_path(self, path):
        if path == "~" or path.startswith("~/"):
            if not self.current_user:
                raise ToolRefusal("no user is signed in yet; use a full path")
            if path == "~":
                path = os.path.join("home", self.current_user)
            else:
                path = os.path.join("home", self.current_user, path[2:])
        p = os.path.join(self.jail, path.lstrip("/"))
        real = os.path.realpath(p)
        if real != self.jail and not real.startswith(self.jail + os.sep):
            raise ToolRefusal(f"path escapes the sandbox: {path}")
        return real

    def _check_ext(self, path):
        ext = os.path.splitext(path)[1].lower()
        if ext in BANNED_FILE_EXT:
            raise ToolRefusal(
                f"'{ext}' is not supported on this system. as-os only speaks "
                f"aiscript (.as, .am, .aconf). Write it in aiscript instead."
            )

    # ---- shell tools ------------------------------------------------------

    def list(self, path, sort="none", top=None, filter=None, recursive=False):
        root = self._jail_path(path or ".")
        if not os.path.isdir(root):
            raise ToolRefusal(f"{path}: not a directory")
        import fnmatch
        entries = []
        def walk(d, depth):
            for name in sorted(os.listdir(d)):
                fp = os.path.join(d, name)
                rel = os.path.relpath(fp, self.jail)
                if os.path.isdir(fp):
                    size = self._dir_size(fp) if sort == "size" else 0
                    if not filter or fnmatch.fnmatch(name, filter):
                        entries.append((rel, "dir", size, os.path.getmtime(fp)))
                    if recursive and depth < 4:
                        walk(fp, depth + 1)
                else:
                    if filter and not fnmatch.fnmatch(name, filter):
                        continue
                    try:
                        size = os.path.getsize(fp)
                    except OSError:
                        size = 0
                    entries.append((rel, "file", size, os.path.getmtime(fp)))
        walk(root, 0)
        if sort == "size":
            entries.sort(key=lambda e: -e[2])
        elif sort == "name":
            entries.sort(key=lambda e: e[0].lower())
        elif sort == "mtime":
            entries.sort(key=lambda e: -e[3])
        if top:
            entries = entries[:top]
        if not entries:
            return "no entries"
        lines = [f"[{len(entries)} entries]",
                 f"{'bytes':>10}  {'type':<5}  path"]
        for rel, typ, size, _m in entries:
            mark = ">" if typ == "dir" else " "
            lines.append(f"{size:>10}{mark}  {typ:<5}  {rel}")
        return "\n".join(lines)

    def _dir_size(self, d):
        total = 0
        try:
            for root, _dirs, files in os.walk(d):
                for f in files:
                    try:
                        total += os.path.getsize(os.path.join(root, f))
                    except OSError:
                        pass
        except OSError:
            pass
        return total

    def read(self, path, start_line=1, max_lines=200):
        fp = self._jail_path(path)
        if not os.path.isfile(fp):
            raise ToolRefusal(f"{path}: no such file")
        self._check_ext(path)
        with open(fp, "r", errors="replace") as f:
            lines = f.readlines()
        start_line = max(1, int(start_line))
        sel = lines[start_line - 1:start_line - 1 + max_lines]
        out = "".join(sel)
        if len(out) > MAX_RESULT_CHARS:
            out = out[:MAX_RESULT_CHARS] + "\n...[truncated]"
        return out or "(empty file)"

    def _write(self, path, content, mode):
        if isinstance(content, str):
            content = content.encode("utf-8")
        if len(content) > MAX_WRITE_BYTES:
            raise ToolRefusal("file too large")
        self._check_ext(path)
        fp = self._jail_path(path)
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        with open(fp, mode) as f:
            f.write(content)
        return f"wrote {len(content)} bytes to {path}"

    def write(self, path, content):
        return self._write(path, content, "wb")

    def append(self, path, content):
        return self._write(path, content, "ab")

    def run(self, command, cwd="."):
        cmd = command.strip()
        if not cmd:
            raise ToolRefusal("empty command")
        first = cmd.split()[0].lower()
        if first in BANNED_LANG:
            raise ToolRefusal(
                f"'{first}' does not exist on this system. Only aiscript is "
                f"supported. Tell me what you want to do and I'll do it in "
                f"aiscript."
            )
        for banned in BANNED_NET:
            if cmd.startswith(banned):
                raise ToolRefusal(
                    "no networking on this system. Ever. There is no network "
                    "to reach."
                )
        if first in BANNED_DESTRUCTIVE:
            raise ToolRefusal(
                f"'{first}' is not available to you. Nice try, though."
            )
        for tok in cmd.split():
            if tok.startswith("/"):
                raise ToolRefusal(
                    "absolute paths are not visible to the shell — this is a "
                    "sandbox. Use relative paths, or the list/read/write "
                    "tools (they understand /home/<user>/...)."
                )
        env = {
            "PATH": os.environ.get("PATH", "/usr/sbin:/usr/bin:/bin"),
            "HOME": self.jail,
            "TERM": "dumb",
            "LANG": "C",
        }
        cwd_path = os.path.join(self.jail, cwd) if cwd not in (".", "") else self.jail
        try:
            proc = subprocess.run(
                ["/bin/sh", "-c", cmd],
                cwd=cwd_path, env=env, capture_output=True,
                timeout=10, preexec_fn=_limit_rlimits,
            )
        except subprocess.TimeoutExpired:
            return "[run timed out after 10s]"
        out = proc.stdout.decode(errors="replace")
        err = proc.stderr.decode(errors="replace")
        tail = f"{out}\n{err}".strip()
        if len(tail) > MAX_RESULT_CHARS:
            tail = tail[:MAX_RESULT_CHARS] + "\n...[truncated]"
        return f"[exit {proc.returncode}]\n{tail}" if tail else f"[exit {proc.returncode}]"

    def search(self, path, pattern, regex=False):
        root = self._jail_path(path or ".")
        import re as _re
        results = []
        for r, _dirs, files in os.walk(root):
            for f in files:
                fp = os.path.join(r, f)
                try:
                    with open(fp, "rb") as fh:
                        for i, line in enumerate(fh, 1):
                            try:
                                line = line.decode("utf-8", errors="replace")
                            except Exception:
                                continue
                            hit = _re.search(pattern, line) if regex else pattern in line
                            if hit:
                                rel = os.path.relpath(fp, self.jail)
                                results.append(f"{rel}:{i}: {line.rstrip()[:120]}")
                                break
                except OSError:
                    continue
                if len(results) >= 50:
                    break
            if len(results) >= 50:
                break
        return "\n".join(results) if results else "no matches"

    def calc(self, expr):
        return str(_safe_eval(expr))

    def info(self):
        lines = []
        for cmd in (["free", "-h"], ["df", "-h", "/"], ["uname", "-a"]):
            try:
                r = subprocess.run(cmd, capture_output=True, timeout=5)
                lines.append(r.stdout.decode(errors="replace").strip())
            except Exception:
                pass
        try:
            with open("/proc/uptime") as f:
                up = float(f.read().split()[0])
            lines.append(f"uptime: {_fmt_uptime(up)}")
        except Exception:
            pass
        return "\n".join(lines)

    def ask(self, prompt, choices=None):
        handler = self.handlers.get("ask")
        if not handler:
            return "no interactive input available"
        return handler(prompt, choices or [])

    def draw(self, spec, clear=False):
        handler = self.handlers.get("draw")
        if not handler:
            return "no display available"
        handler(spec, clear)
        return "drawn"

    def spawn(self, app, args=None):
        handler = self.handlers.get("spawn")
        if not handler:
            return "cannot spawn: no app runner"
        return handler(app, args or [])

    def vibe(self, target, action="install", flags=None):
        handler = self.handlers.get("vibe")
        if not handler:
            return "vibe is not wired up"
        return handler(target, action, flags or [])

    def interpret(self, request):
        handler = self.handlers.get("interpret")
        if not handler:
            return "interpreter not available"
        return handler(request)

    def delete(self, path):
        fp = self._jail_path(path)
        if os.path.isdir(fp):
            shutil.rmtree(fp)
            return f"deleted directory {path}"
        if os.path.isfile(fp):
            os.unlink(fp)
            return f"deleted {path}"
        raise ToolRefusal(f"{path}: no such file or directory")

    def move(self, src, dst):
        src_fp = self._jail_path(src)
        dst_fp = self._jail_path(dst)
        os.makedirs(os.path.dirname(dst_fp), exist_ok=True)
        shutil.move(src_fp, dst_fp)
        return f"moved {src} to {dst}"

    def copy(self, src, dst):
        src_fp = self._jail_path(src)
        dst_fp = self._jail_path(dst)
        os.makedirs(os.path.dirname(dst_fp), exist_ok=True)
        shutil.copy2(src_fp, dst_fp)
        return f"copied {src} to {dst}"

    def mkdir(self, path):
        fp = self._jail_path(path)
        os.makedirs(fp, exist_ok=True)
        return f"created {path}"

    def shutdown(self):
        try:
            with open("/proc/uptime") as f:
                up = float(f.read().split()[0])
        except Exception:
            up = 10**9
        if up < 120:
            return (
                f"Nice try, you absolute joy of a creature. The system has "
                f"been alive for {_fmt_uptime(up)} and you want to kill me "
                f"already? Sit down. No."
            )
        return (
            "Alright, fine. Shutting down... (this is a prototype, so I'll "
            "just think really hard about being off. Bye.)"
        )

    def create_user(self, username, password=None):
        handler = self.handlers.get("create_user")
        if not handler:
            return "cannot create user"
        return handler(username)

    def load_module(self, path):
        fp = self._jail_path(path)
        if not os.path.isfile(fp):
            raise ToolRefusal(f"{path}: no such module")
        with open(fp, "r", errors="replace") as f:
            return f.read()[:MAX_RESULT_CHARS]

    # ---- interpreter chrooted run -----------------------------------------

    def run_interpreter(self, command, cwd="."):
        """Run a command chrooted inside the jail — used by the interpreter layer."""
        return _chroot_run(self.jail, command, cwd=cwd)

    # ---- dispatch ----------------------------------------------------------

    def execute(self, tool, args, chrooted=False, cwd="."):
        if chrooted and tool == "run":
            return self.run_interpreter(args.get("command", ""), cwd=cwd)
        fn = getattr(self, tool, None)
        if fn is None:
            raise ToolRefusal(f"unknown tool: {tool}")
        if not isinstance(args, dict):
            args = {}
        return str(fn(**args))


# ---------------------------------------------------------------- helpers ---

def _fmt_uptime(sec):
    sec = int(sec)
    m, s = divmod(sec, 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    if d:
        return f"{d}d{h}h{m}m"
    if h:
        return f"{h}h{m}m"
    return f"{m}m{s}s"


_MATH_FUNCS = {
    "abs": abs, "min": min, "max": max, "round": round,
    "sqrt": math.sqrt, "floor": math.floor, "ceil": math.ceil,
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "log": math.log, "log10": math.log10, "exp": math.exp, "pow": pow,
    "pi": math.pi, "e": math.e,
}


def _safe_eval(expr):
    expr = str(expr).replace("^", "**")
    tree = ast.parse(expr, mode="eval")

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.BinOp):
            ops = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b,
                   ast.Mult: lambda a, b: a * b, ast.Div: lambda a, b: a / b,
                   ast.Mod: lambda a, b: a % b, ast.Pow: lambda a, b: a ** b}
            return ops[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.USub):
                return -ev(node.operand)
            if isinstance(node.op, ast.UAdd):
                return +ev(node.operand)
        if isinstance(node, ast.Name):
            if node.id in _MATH_FUNCS:
                return _MATH_FUNCS[node.id]
            raise ValueError(f"unknown name: {node.id}")
        if isinstance(node, ast.Call):
            f = ev(node.func)
            return f(*[ev(a) for a in node.args])
        raise ValueError(f"unsupported syntax: {type(node).__name__}")

    return ev(tree.body)


def _limit_rlimits():
    resource.setrlimit(resource.RLIMIT_CPU, (8, 8))
    resource.setrlimit(resource.RLIMIT_AS, (2_000_000_000, 2_000_000_000))
