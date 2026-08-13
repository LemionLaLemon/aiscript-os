import os
import re
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import readline
import tomllib

from daemon.server import Daemon
import asui

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

AUTONAME_EVERY = 5
LONG_TURNS = 40
LONG_TOKENS = 6000


def load_cfg():
    with open(os.path.join(ROOT, "config.toml"), "rb") as f:
        return tomllib.load(f)


def read_profile(path):
    prof = {}
    if path and os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, _, v = line.partition("=")
                    v = v.strip().strip("\"'")
                    try:
                        prof[k.strip()] = float(v) if "." in v else int(v)
                    except ValueError:
                        prof[k.strip()] = v
    return prof


# ANSI color codes
_SHELL_COLOR = "\033[36m"       # cyan
_INTERP_COLOR = "\033[35m"      # magenta
_DIM = "\033[2m"
_RESET = "\033[0m"
_TOOL_COLOR = "\033[36m"        # cyan for ⟳


class Shell:
    def __init__(self, cfg):
        self.cfg = cfg
        self.daemon = Daemon(cfg)
        self.daemon.stream_out.append(self._sub_event)
        self._out = threading.Lock()
        self.show_thinking = cfg.get("daemon", {}).get("show_thinking", "on")
        self._content_started = False

    # ---- event rendering --------------------------------------------------

    def _write(self, text):
        with self._out:
            sys.stdout.write(text)
            sys.stdout.flush()

    def _clear_line(self):
        self._write("\r\033[K")

    def _main_event(self, ev):
        t = ev["type"]
        if t == "phase":
            self._handle_phase(ev)
        elif t == "content":
            if not self._content_started:
                self._clear_line()
                self._content_started = True
            self._write(ev["text"])
        elif t == "thinking":
            layer = ev.get("layer", "shell")
            if self.show_thinking == "on":
                color = _SHELL_COLOR if layer == "shell" else _INTERP_COLOR
                self._write(f"{_DIM}{color}{ev['text']}{_RESET}")
        elif t == "tool-delta":
            self._write(f"\r\033[K{_TOOL_COLOR}\u27f3 {ev['name']}({ev['args']}){_RESET}")
        elif t == "tool":
            if self.show_thinking == "on":
                args = ", ".join(f"{k}={v}" for k, v in ev["args"].items())
                self._write(f"\r\033[K{_TOOL_COLOR}\u27f3 {ev['name']}({args}){_RESET}\n")
            elif self.show_thinking == "off":
                self._write("running tasks...\n")

    def _handle_phase(self, ev):
        state = ev.get("state", "")
        layer = ev.get("layer", "shell")
        if self.show_thinking == "silent":
            return
        if self.show_thinking == "off":
            label = f"{layer} is thinking..." if state == "thinking" else \
                    "running tasks..." if state == "running" else \
                    "forming an answer..." if state == "answering" else \
                    f"{layer} is working..."
            self._write(f"{label}\n")
        elif self.show_thinking == "on":
            if state == "thinking":
                color = _SHELL_COLOR if layer == "shell" else _INTERP_COLOR
                self._write(f"{_DIM}{color}{layer} is thinking...{_RESET}\n")

    def _sub_event(self, tag, ev):
        t = ev["type"]
        # Show vibe install status
        if "vibe:" in str(tag) and t == "content":
            pkg = str(tag).replace("vibe:", "").replace("app:", "").strip()
            if "vibecoded" in str(ev.get("text", "")).lower():
                self._write(f"\033[32m✓ {pkg} installed\033[0m\n")
        if t == "content":
            self._write(f"{_DIM}[{tag}] {ev['text']}{_RESET}")
        elif t == "tool-delta":
            self._write(f"\r\033[K\033[35m[{tag}] \u27f3 {ev['name']}({ev['args']}){_RESET}")
        elif t == "tool":
            if self.show_thinking == "on":
                args = ", ".join(f"{k}={v}" for k, v in ev["args"].items())
                self._write(f"\r\033[K\033[35m[{tag}] \u27f3 {ev['name']}({args}){_RESET}\n")

    # ---- interactive handlers ------------------------------------------------

    def ask_handler(self, prompt, choices):
        print()
        print(f"\033[1;33m? {prompt}\033[0m")
        if choices:
            for i, c in enumerate(choices, 1):
                print(f"  \033[36m{i})\033[0m {c}")
            print("  (enter a number, or type your own answer)")
        try:
            ans = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            ans = ""
        if ans.isdigit() and choices:
            i = int(ans)
            if 1 <= i <= len(choices):
                return choices[i - 1]
        return ans

    def draw_handler(self, spec, clear):
        print(asui.render_spec(spec))

    # ---- lifecycle -------------------------------------------------------------

    def start(self):
        self.daemon.start()
        self.daemon.executor.handlers["ask"] = self.ask_handler
        self.daemon.executor.handlers["draw"] = self.draw_handler

        print("\033[1;36m" + r"""     _    ____      
     / \  / ___|    
    / _ \ \___ \   
   / ___ \ ___) |  
  /_/   \_\____/   
""" + "\033[0m")
        print("as-os — the OS whose soul is a local AI. booting…\n")

        did_oobe = self.daemon.run_oobe(self.ask_handler, on_event=self._main_event)
        if did_oobe:
            print("\n\033[1;32mWelcome. The system is yours now.\033[0m\n")

        self._load_profile()

        self.session = None
        self._session_seq = 0
        latest = self.daemon.store.latest()
        if latest:
            self.session = self.daemon.load_session(
                latest, temp=self.temp, max_tokens=2048)
        if self.session is None:
            self._new_session()
        else:
            print(f"\033[2mresumed session: {self.session.name}"
                  f" ({self.session.turn_count()} turns)\033[0m")
        self._repl()

    # ---- REPL -------------------------------------------------------------------

    def _repl(self):
        while True:
            try:
                prompt = self._prompt()
                line = input(f"\033[1;32m{prompt}\033[0m")
            except EOFError:
                print()
                self._save_current()
                break
            except KeyboardInterrupt:
                print()
                continue
            line = line.strip()
            if not line:
                continue
            if line in ("exit", "quit", ":q"):
                self._save_current()
                break
            if line == "help":
                self._help()
                continue
            if line == "clear":
                self._clear_screen()
                continue
            if line == "status":
                self._status()
                continue
            if line.startswith("chaos"):
                self._chaos(line)
                continue
            if line.startswith("temp "):
                try:
                    self.temp = float(line.split()[1])
                    self.session.temp = self.temp
                    print(f"temperature -> {self.temp}")
                except (IndexError, ValueError):
                    print("usage: temp <0-1>")
                continue
            if line in ("new", "new temp"):
                self._new_session(temp=("temp" in line.split()))
                continue
            if line == "reoobe":
                self._reoobe()
                continue
            if line.startswith("model"):
                self._model_cmd(line)
                continue
            if line == "sessions":
                self._sessions()
                continue
            if line == "history":
                self._history()
                continue
            if line.startswith("session "):
                self._session_cmd(line)
                continue
            if line == "reset":
                self.session.reset()
                print("session reset")
                continue
            if line == "apps":
                self._apps()
                continue
            if line == "pkgs":
                self._pkgs()
                continue
            # bare word matching an installed app/package -> spawn directly
            if self._try_app_spawn(line):
                continue

            streamed = [False]
            stop = threading.Event()
            self._content_started = False

            def spinner():
                dots = 0
                while not stop.wait(0.4):
                    dots += 1
                    if stop.is_set():
                        break
                    self._write(f"\r\033[K{_DIM}thinking{'…' * (dots % 3 + 1)}{_RESET}")

            def on_event(ev):
                stop.set()
                if ev["type"] == "content" and not streamed[0]:
                    self._clear_line()
                    streamed[0] = True
                self._main_event(ev)

            threading.Thread(target=spinner, daemon=True).start()
            try:
                out = self.session.user_turn(line, on_event=on_event)
            except Exception as e:
                self._write(f"\r\033[K\033[33m(model error: {e})\033[0m\n")
                out = ""
            finally:
                stop.set()

            if streamed[0]:
                if out and not out.endswith("\n"):
                    self._write("\n")
            else:
                self._clear_line()
                if out:
                    print(out)
            print()

            self._maybe_autoname()
            self._autosave()
            self._warn_if_long()

    def _help(self):
        print(
            "everything you type is interpreted by kernel-2, the AI.\n"
            "\n"
            "builtins (typed as-is):\n"
            "  help        show this help\n"
            "  status      show session state (temp, user, thinking mode)\n"
            "  apps        list installed apps and packages\n"
            "  pkgs        list installed packages (same as 'vibe list')\n"
            "  chaos on|off|p <n>   toggle/set the chaos probability\n"
            "  temp <0-1>           set the AI temperature\n"
            "  history     how many turns and how much context this session has\n"
            "  reset       forget this conversation, keep the session\n"
            "  clear       clear the terminal screen\n"
            "  reoobe      re-run first-boot onboarding\n"
            "  model       show/choose the AI brain (model list / model set)\n"
            "  exit / quit / :q     leave the shell\n"
            "\n"
            "sessions (this shell keeps a history of sessions):\n"
            "  new                      start a fresh session (old one is saved)\n"
            "  new temp                 start a temporary session (not saved)\n"
            "  sessions                 list saved sessions\n"
            "  session switch <name>    resume a saved session\n"
            "  session rename <name> <new>  rename (locks auto-naming)\n"
            "  session delete <name>    delete a saved session\n"
            "\n"
            "apps and packages (installed by default):\n"
            "  man <topic>   read the manual (e.g. 'man shell', 'man tools')\n"
            "  notepad <file>  edit a text file\n"
            "  sysinfo       system info    find-big   biggest files\n"
            "  search-files  search text\n"
            "\n"
            "reserved word: 'vibe' is package management ('vibe install X').\n"
            "everything else — like 'cd Documents' or 'ls' — is handled by the AI."
        )

    def _status(self):
        print(self.daemon.chaos.stats())
        print(f"temp: {self.session.temp}")
        print(f"user: {self.daemon.current_user}")
        print(f"slots: {len(self.daemon.sessions)} sessions")
        print(f"thinking: {self.show_thinking}")
        print(f"current session: {self.session.name or '(unnamed)'}")
        print(f"model: {self.daemon.active_model()}")

    def _clear_screen(self):
        """Clear the terminal (a shell builtin — never sends this to the AI)."""
        self._write("\033[2J\033[H")

    def _reoobe(self):
        """Re-run first-boot onboarding (username, chaos, machine name)."""
        print("re-running OOBE...")
        did = self.daemon.run_oobe(self.ask_handler, on_event=self._main_event,
                                   force=True)
        if did:
            print("\n\033[1;32mOnboarding done. The system is yours again.\033[0m\n")
            self._load_profile()
        else:
            print("OOBE did not run.")

    def _load_profile(self):
        """(Re)load user profile settings after OOBE."""
        import os as _os
        profile = read_profile(
            _os.path.join(self.daemon.user_home(), ".asrc"))
        self.temp = profile.get("temp", self.cfg["daemon"]["temp"])
        self.chaos_p = profile.get("chaos_p", self.cfg["chaos"]["p"])
        self.prompt = profile.get("prompt", self.cfg["shell"]["prompt"])
        self.daemon.chaos.p = self.chaos_p

    def _model_cmd(self, line):
        """model / model list / model set <name> — choose the AI's brain."""
        parts = line.split()
        if len(parts) == 1 or parts[1] == "list":
            avail = self.daemon.available_models()
            print(f"current model: {self.daemon.active_model()}")
            if avail:
                print("available:")
                for m in avail:
                    print(f"  {m}")
            return
        if len(parts) >= 3 and parts[1] in ("set", "use"):
            name = parts[2]
            print(f"switching to {name}... (engine restarting)")
            err = self.daemon.set_model(name)
            if err:
                print(err)
            else:
                print(f"now running {self.daemon.active_model()}")
            return
        print("usage: model | model list | model set <name>")

    def _history(self):
        s = self.session
        turns = s.turn_count()
        tokens = s.est_tokens()
        print(f"session: {s.name or '(unnamed)'}")
        print(f"turns: {turns}")
        print(f"est context tokens: {tokens}")
        if turns >= LONG_TURNS or tokens >= LONG_TOKENS:
            print(f"\033[33m(!) session is getting long — type 'new' for a fresh one\033[0m")

    def _warn_if_long(self):
        s = self.session
        if s.temp_session:
            return
        if s.turn_count() >= LONG_TURNS or s.est_tokens() >= LONG_TOKENS:
            print(f"\033[2m(!) this session is getting long — type 'new' to start fresh\033[0m")

    def _new_session(self, temp=False):
        """Start a fresh (or temporary) session, saving the current one."""
        if self.session is not None:
            self._save_current()
        self._session_seq += 1
        placeholder = f"session-{self._session_seq}"
        self.session = self.daemon.new_session(
            placeholder, temp=self.temp, max_tokens=2048,
            temp_session=temp)
        self.daemon.sessions.pop(placeholder, None)
        self.session.name = None
        self.session.name_locked = False
        self.session._auto_name_turns = 0
        if temp:
            print("temporary session started (won't be saved)")
        else:
            print("new session started")

    def _autosave(self):
        """Persist the current session if it's nameable and not temporary."""
        s = self.session
        if s.temp_session or not s.name:
            return
        self.daemon.store.save(s)

    def _prompt(self):
        """Prompt showing the current directory: as/~# at home,
        as/~/Documents# inside Documents."""
        base = self.prompt.rstrip().rstrip("#").rstrip() or "as"
        cwd = getattr(self.session, "_display_cwd", lambda: "~")()
        return f"{base}/{cwd}# "

    def _save_current(self):
        """Finalize the current session: auto-name it, then save if saved-able."""
        if self.session is None:
            return
        self._maybe_autoname(force=True)
        self._autosave()

    def _sessions(self):
        items = self.daemon.store.list()
        if not items:
            print("no saved sessions")
            return
        cur = self.session.name if self.session else None
        for it in items:
            mark = "*" if it["name"] == cur else " "
            print(f" {mark} {it['name']:40} {it['turns']} turns")

    def _session_cmd(self, line):
        parts = line.split(None, 2)
        if len(parts) < 2:
            print("usage: session switch|rename|delete <name>")
            return
        cmd = parts[1]
        if cmd == "list":
            self._sessions()
        elif cmd == "switch":
            if len(parts) < 3:
                print("usage: session switch <name>")
                return
            self._session_switch(parts[2])
        elif cmd == "rename":
            if len(parts) < 3:
                print("usage: session rename <name> <new name>")
                return
            self._session_rename(parts[2])
        elif cmd == "delete":
            if len(parts) < 3:
                print("usage: session delete <name>")
                return
            self._session_delete(parts[2])
        else:
            print(f"unknown session command: {cmd}")

    def _session_switch(self, name):
        self._save_current()
        sess = self.daemon.load_session(name, temp=self.temp, max_tokens=2048)
        if sess is None:
            print(f"no saved session: {name}")
            return
        self.session = sess
        print(f"switched to session: {name}")

    def _session_rename(self, name, new_name=None):
        if new_name is None:
            new_name = name
        ok, err = self.daemon.store.rename(name, new_name)
        if not ok:
            print(err)
            return
        if self.session is not None and self.session.name == name:
            self.session.name = new_name
            self.session.name_locked = True
            self.daemon.sessions.pop(name, None)
            self.daemon.sessions[new_name] = self.session
        elif name in self.daemon.sessions:
            other = self.daemon.sessions[name]
            other.name = new_name
            self.daemon.sessions.pop(name, None)
            self.daemon.sessions[new_name] = other
        print(f"renamed '{name}' -> '{new_name}' (name locked)")

    def _session_delete(self, name):
        if self.session is not None and self.session.name == name:
            print("can't delete the active session; switch or start a new one first")
            return
        if self.daemon.delete_session(name):
            print(f"deleted session: {name}")
        else:
            print(f"no saved session: {name}")

    def _derive_name(self, text):
        """Extractive session name from the first non-trivial user line."""
        text = (text or "").strip()
        text = re.sub(r"^<continuing>\s*", "", text)
        line = text.splitlines()[0].strip() if text else ""
        if not line:
            return None
        if len(line) > 48:
            line = line[:48].rstrip() + "…"
        return line

    def _maybe_autoname(self, force=False):
        """Auto-name the session from its first user message, and re-name it
        every AUTONAME_EVERY turns (unless the user locked a name)."""
        s = self.session
        if s is None or s.temp_session or s.name_locked:
            return
        turns = s.turn_count()
        if turns < 1:
            return
        if not force and not (turns == 1 or turns % AUTONAME_EVERY == 0):
            return
        last_user = None
        for m in reversed(s.messages):
            if m["role"] == "user":
                last_user = m.get("content", "")
                break
        cand = self._derive_name(last_user)
        if not cand:
            return
        if s.name == cand:
            return
        old = s.name
        new = self._unique_name(cand)
        s.name = new
        if old:
            self.daemon.store.rename(old, new)
            self.daemon.sessions.pop(old, None)
        self.daemon.sessions[new] = s

    def _unique_name(self, base):
        existing = {it["name"] for it in self.daemon.store.list()}
        existing.discard(self.session.name if self.session else None)
        if base not in existing:
            return base
        n = 2
        while f"{base} ({n})" in existing:
            n += 1
        return f"{base} ({n})"

    def _chaos(self, line):
        parts = line.split()
        if len(parts) == 2 and parts[1] == "on":
            self.daemon.chaos.enabled = True
            print("chaos engaged")
        elif len(parts) == 2 and parts[1] == "off":
            self.daemon.chaos.enabled = False
            print("chaos disengaged")
        elif len(parts) == 3 and parts[1] == "p":
            self.daemon.chaos.p = float(parts[2])
            print(f"chaos probability -> {self.daemon.chaos.p}")
        else:
            print(self.daemon.chaos.stats())

    def _apps(self):
        apps_dir = os.path.join(self.daemon.jail, "apps")
        pkgs_dir = os.path.join(self.daemon.jail, "packages")
        found = []
        if os.path.isdir(apps_dir):
            for f in sorted(os.listdir(apps_dir)):
                name, ext = os.path.splitext(f)
                if ext in (".as", ".ais"):
                    found.append(f"  {name}")
        if os.path.isdir(pkgs_dir):
            for d in sorted(os.listdir(pkgs_dir)):
                if os.path.isdir(os.path.join(pkgs_dir, d)):
                    found.append(f"  {d} (package)")
        if found:
            print("available apps:\n" + "\n".join(found))
        else:
            print("no apps installed. try: vibe install <something>")

    def _try_app_spawn(self, line):
        """If the user's line starts with an installed app/package name
        (optionally followed by args, e.g. "cowsay Hello, World!" or "man
        vibe"), spawn it directly (deterministic, no model guesswork).
        Returns True if handled."""
        line = line.strip()
        if not line:
            return False
        parts = line.split(None, 1)
        word = parts[0]
        try:
            path = self.daemon._resolve_app(word)
        except Exception:
            return False
        args = []
        if len(parts) == 2:
            rest = parts[1]
            # "man vibe" -> args ["vibe"]; "cowsay Hello, World!" -> ["Hello,", "World!"]
            args = rest.split()
        self._write(f"\033[32mspawn {word}...\033[0m\n")
        result = self.daemon._handle_spawn(word, args)
        print(result)
        return True

    def _pkgs(self):
        result = self.daemon._handle_vibe(None, "list", [])
        print(result)


def main():
    cfg = load_cfg()
    Shell(cfg).start()


if __name__ == "__main__":
    main()
