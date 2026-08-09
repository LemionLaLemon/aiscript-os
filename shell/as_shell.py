import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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


class Shell:
    def __init__(self, cfg):
        self.cfg = cfg
        self.daemon = Daemon(cfg)
        self.daemon.stream_out.append(self._sub_event)

    # ---- event rendering --------------------------------------------------

    def _main_event(self, ev):
        t = ev["type"]
        if t == "content":
            sys.stdout.write(ev["text"])
            sys.stdout.flush()
        elif t == "thinking":
            sys.stdout.write(f"\033[2m{ev['text']}\033[0m")
            sys.stdout.flush()
        elif t == "tool":
            args = ", ".join(f"{k}={v}" for k, v in ev["args"].items())
            sys.stdout.write(f"\n\033[36m⟳ {ev['name']}({args})\033[0m\n")
            sys.stdout.flush()

    def _sub_event(self, tag, ev):
        t = ev["type"]
        if t == "content":
            sys.stdout.write(f"\033[2m[{tag}] {ev['text']}\033[0m")
            sys.stdout.flush()
        elif t == "tool":
            args = ", ".join(f"{k}={v}" for k, v in ev["args"].items())
            sys.stdout.write(f"\n\033[35m[{tag}] ⟳ {ev['name']}({args})\033[0m\n")
            sys.stdout.flush()

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
            "shell", temp=self.temp, max_tokens=512, tier="fast")
        self.big_session = None
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
                if self.big_session:
                    self.big_session.reset()
                print("session reset")
                continue

            self.session.escalated = None
            out = self.session.user_turn(line, on_event=self._main_event)
            if self.session.escalated:
                self._escalate(line, self.session.escalated)
            else:
                print(out)
            print()

    def _escalate(self, line, reason):
        if not self.big_session:
            self.big_session = self.daemon.new_session(
                "big", temp=self.temp, max_tokens=512, max_loops=12,
                time_budget=240)
        print(f"\033[2m(handing off to the big brain: {reason})\033[0m")
        out = self.big_session.user_turn(line, on_event=self._main_event)
        print(out)

    def _help(self):
        print(
            "builtins:  help  status  chaos on|off|p <n>  temp <0-1>  reset  exit\n"
            "everything else is interpreted by kernel-2, the AI.\n"
            "reserved word: 'vibe' is package management (e.g. 'vibe install fastfetch')."
        )

    def _status(self):
        print(self.daemon.chaos.stats())
        print(f"temp: {self.session.temp}")
        print(f"user: {self.daemon.current_user}")
        print(f"slots: {len(self.daemon.sessions)} sessions")

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


def main():
    cfg = load_cfg()
    Shell(cfg).start()


if __name__ == "__main__":
    main()
