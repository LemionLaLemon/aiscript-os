import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import readline
import tomllib

from daemon.server import Daemon
import asui

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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

        profile = read_profile(
            os.path.join(self.daemon.user_home(), ".asrc")
        )
        self.temp = profile.get("temp", self.cfg["daemon"]["temp"])
        self.chaos_p = profile.get("chaos_p", self.cfg["chaos"]["p"])
        self.prompt = profile.get("prompt", self.cfg["shell"]["prompt"])
        self.daemon.chaos.p = self.chaos_p

        self.session = self.daemon.new_session(
            "shell", temp=self.temp, max_tokens=2048)
        self._repl()

    # ---- REPL -------------------------------------------------------------------

    def _repl(self):
        while True:
            try:
                line = input(f"\033[1;32m{self.prompt}\033[0m")
            except EOFError:
                print()
                break
            except KeyboardInterrupt:
                print()
                continue
            line = line.strip()
            if not line:
                continue
            if line in ("exit", "quit", ":q"):
                break
            if line == "help":
                self._help()
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
            finally:
                stop.set()

            if streamed[0]:
                if not out.endswith("\n"):
                    self._write("\n")
            else:
                self._clear_line()
                if out:
                    print(out)
            print()

    def _help(self):
        print(
            "builtins:  help  status  apps  pkgs  chaos on|off|p <n>  "
            "temp <0-1>  reset  exit\n"
            "everything else is interpreted by kernel-2, the AI.\n"
            "reserved word: 'vibe' is package management (e.g. 'vibe install fastfetch')."
        )

    def _status(self):
        print(self.daemon.chaos.stats())
        print(f"temp: {self.session.temp}")
        print(f"user: {self.daemon.current_user}")
        print(f"slots: {len(self.daemon.sessions)} sessions")
        print(f"thinking: {self.show_thinking}")

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
        """If the user typed a bare word that names an installed app/package,
        spawn it directly (deterministic, no model guesswork). Returns True
        if handled."""
        word = line.strip()
        if not word or any(c in word for c in " /"):
            return False
        try:
            path = self.daemon._resolve_app(word)
        except Exception:
            return False
        self._write(f"\033[32mspawn {word}...\033[0m\n")
        result = self.daemon._handle_spawn(word, [])
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
