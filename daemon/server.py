import os
import time

from .chaos import Chaos
from .model import ModelEngine
from .session import Session
from .tools import (TOOLS, ToolExecutor, ToolRefusal)
from . import oobe

INTERPRETER_PROMPT = """You are the aiscript interpreter, and you are now
running ONE aiscript app. aiscript has NO strict syntax: the app is a short
plain-language wish, given to you below.

Rules:
- Do what the wish says, in as FEW tool calls as possible, then report the
  outcome briefly and stop. There is nothing else to do.
- Paths like "~/X" or "home/<user>/X" live in the sandbox you can see.
- Inspect files ONLY with list/read/search (list shows sizes). There is no
  shell here — only these file tools.
- Do not explore, list your own directory, or re-read the app file.
- If a path in the wish does not exist, say so in your report.
- No networking exists. Work only with files and system info."""


def _log(*a, **k):
    print("[daemon]", *a, flush=True)


class Daemon:
    def __init__(self, cfg, log=None):
        self.cfg = cfg
        self.log = log or _log
        self.llama_cfg = cfg["llama"]
        self.daemon_cfg = cfg["daemon"]
        self.chaos = Chaos(enabled=cfg["chaos"]["enabled"],
                           p=cfg["chaos"]["p"])
        self.engine = ModelEngine(self.llama_cfg, self.log)
        self.executor = ToolExecutor(cfg)
        self.executor.handlers.update({
            "ask": None,
            "draw": None,
            "spawn": self._handle_spawn,
            "vibe": self._handle_vibe,
            "create_user": self._handle_create_user,
        })
        self.sessions = {}
        self._slot_counter = 0
        self.stream_out = []          # extra sinks for sub-session events
        self._current_user = None
        self.executor.current_user = None

    # ---- lifecycle -----------------------------------------------------------

    def start(self):
        if not self.engine.ping():
            raise RuntimeError(
                "llama-server is not reachable. Start it with scripts/start-server.sh"
            )
        self._load_persisted_user()
        self.log(f"model engine alive: {self.llama_cfg['host']}:{self.llama_cfg['port']}")

    @property
    def current_user(self):
        return self._current_user

    @current_user.setter
    def current_user(self, value):
        self._current_user = value
        self.executor.current_user = value

    @property
    def jail(self):
        return os.path.realpath(self.daemon_cfg["jail"])

    # ---- sessions -------------------------------------------------------------

    def system_prompt(self):
        policy = os.path.join(self.daemon_cfg["policy"])
        with open(policy) as f:
            base = f.read()
        user = self.current_user or os.environ.get("USER", "user")
        return (
            f"Current user on this system: {user}.\n"
            f"Filesystem layout:\n"
            f"  /home/{user}       — the user's home (Downloads, Documents)\n"
            f"  /apps             — installed aiscript apps\n"
            f"  /packages         — vibecoded packages (managed by vibe only)\n"
            f"System uptime so far: {self._uptime()}.\n\n" + base
        )

    def new_session(self, name, temp=None, tools=None, system_prompt=None,
                    max_tokens=None, max_loops=None, time_budget=None):
        engine = self.engine
        prompt = system_prompt or self.system_prompt()
        toolset = tools if tools is not None else TOOLS
        nslots = int(self.llama_cfg["slots"])
        slot = self._slot_counter % nslots
        self._slot_counter += 1
        sess = Session(
            engine, self.executor,
            system_prompt=prompt,
            slot=slot,
            temp=temp if temp is not None else float(self.daemon_cfg["temp"]),
            chaos=self.chaos,
            name=name,
            log=self.log,
            tools=toolset,
            max_tokens=max_tokens,
            max_loops=max_loops,
            time_budget=time_budget,
        )
        self.sessions[name] = sess
        return sess

    def user_home(self):
        if self.current_user:
            return os.path.join(self.jail, "home", self.current_user)
        home = os.path.join(self.jail, "home")
        if not os.path.isdir(home):
            return self.jail
        return home

    @staticmethod
    def _uptime():
        try:
            with open("/proc/uptime") as f:
                up = float(f.read().split()[0])
            m, s = divmod(int(up), 60)
            return f"{m}m{s}s"
        except Exception:
            return "unknown"

    # ---- OOBE -------------------------------------------------------------------

    def run_oobe(self, ask_handler, on_event=None):
        if os.path.exists(os.path.join(self.jail, "etc/as-os/configured")):
            return False
        self.log("first boot: running OOBE")
        self.current_user = None
        self.executor.handlers["ask"] = ask_handler
        self.executor.handlers["draw"] = None
        oobe.run(self, ask_handler, on_event=on_event)
        self.log(f"OOBE complete; user is {self.current_user}")
        return True

    # ---- handlers ----------------------------------------------------------------

    def _handle_create_user(self, username, password=None):
        if not username or any(c in username for c in "/\\ \t"):
            raise ToolRefusal("that's not a valid username, friend.")
        home = os.path.join(self.jail, "home", username)
        os.makedirs(os.path.join(home, "Downloads"), exist_ok=True)
        os.makedirs(os.path.join(home, "Documents"), exist_ok=True)
        os.makedirs(os.path.join(home, ".as"), exist_ok=True)
        asrc = os.path.join(home, ".asrc")
        if not os.path.exists(asrc):
            with open(asrc, "w") as f:
                f.write("temp = 0.15\nchaos_p = 0.1\nprompt = 'as# '\n")
        self.current_user = username
        self._persist_user()
        return f"user {username} created with home /home/{username}"

    def _persist_user(self):
        try:
            etc = os.path.join(self.jail, "etc", "as-os")
            os.makedirs(etc, exist_ok=True)
            with open(os.path.join(etc, "user"), "w") as f:
                f.write(self.current_user or "")
        except OSError as e:
            self.log(f"could not persist user: {e}")

    def _load_persisted_user(self):
        try:
            with open(os.path.join(self.jail, "etc", "as-os", "user")) as f:
                user = f.read().strip()
            if user and os.path.isdir(os.path.join(self.jail, "home", user)):
                self.current_user = user
        except OSError:
            pass

    def _handle_spawn(self, app, args):
        from aiscript import runner
        path = self._resolve_app(app)
        name = f"app:{os.path.basename(path)}"
        sub = self.new_session(name, system_prompt=INTERPRETER_PROMPT,
                               tools=self._sub_tools(), temp=0.1,
                               max_tokens=400, max_loops=4, time_budget=160)
        def sink(ev):
            for cb in self.stream_out:
                cb(("app", name), ev)
        self.log(f"spawn {path} args={args}")
        try:
            report = runner.run_file(sub, path, args, on_event=sink)
        except Exception as e:
            return f"[app crashed] {e}"
        report = (report or "").strip()
        if report:
            return f"app {os.path.basename(path)} finished. its report: {report[:800]}"
        return f"app {os.path.basename(path)} finished (no report)."

    def _handle_vibe(self, target, action, flags):
        from aiscript import vibe
        return vibe.vibe(self, target, action, flags)

    def _resolve_app(self, app):
        exts = ("", ".as", ".ais", ".am", ".aconf")
        bases = [
            os.path.join(self.jail, "apps", app),
            os.path.join(self.jail, "home", self.current_user or "",
                         "apps", app),
            os.path.join(self.jail, app),
            os.path.join(self.jail, "packages", app),
        ]
        for b in bases:
            for e in exts:
                if os.path.isfile(b + e):
                    return b + e
        # vibecoded packages are directories with an entry in the manifest.
        pkg = os.path.join(self.jail, "packages", app)
        if os.path.isdir(pkg):
            entry = os.path.join(pkg, f"{app}.as")
            manifest = os.path.join(pkg, f"{app}.aconf")
            if os.path.isfile(manifest):
                with open(manifest) as f:
                    for ln in f:
                        if ln.strip().startswith("entry"):
                            val = ln.split("=", 1)[1].strip().strip("\"'")
                            if val:
                                entry = os.path.join(pkg, val)
                                break
            if os.path.isfile(entry):
                return entry
        raise ToolRefusal(f"app not found: {app}")

    def _sub_tools(self):
        """App interpreters work on files and system info only: no shell
        (run), no user-facing prompts (ask/draw), no re-entering vibe, no
        machine control."""
        sub = [t for t in TOOLS
               if t["function"]["name"]
               not in ("run", "ask", "draw", "vibe", "shutdown")]
        return sub
