import os
import time

from .chaos import Chaos
from .model import ModelEngine
from .session import Session
from .session_store import SessionStore
from .tools import (SHELL_TOOLS, INTERPRETER_TOOLS, ToolExecutor, ToolRefusal)
from .prompt import build_shell_prompt, build_interpreter_prompt
from . import oobe


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
            "interpret": self._handle_interpret,
        })
        self.sessions = {}
        self._slot_counter = 0
        self.stream_out = []          # extra sinks for sub-session events
        self._current_user = None
        self.executor.current_user = None
        self.store = SessionStore(self.daemon_cfg["jail"])

    # ---- lifecycle -----------------------------------------------------------

    def start(self):
        if not self._wait_engine(timeout=30):
            raise RuntimeError(
                "llama-server is not reachable. Start it with scripts/start_as_shell.sh"
            )
        self._load_persisted_user()
        self.log(f"model engine alive: {self.llama_cfg['host']}:{self.llama_cfg['port']}")

    # ---- model management (ascOS image) --------------------------------------

    def active_model(self):
        """The model file currently selected on the data partition (or the
        config default if none is stored)."""
        try:
            with open(os.path.join(self.jail, "etc/as-os/model")) as f:
                name = f.read().strip()
            if name:
                return name
        except OSError:
            pass
        return self.llama_cfg.get("model_name", "LFM2.5-8B-A1B-Q4_K_M.gguf")

    def available_models(self):
        """Model files shipped in the image's models dir."""
        d = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "models")
        if not os.path.isdir(d):
            return []
        return sorted(f for f in os.listdir(d) if f.endswith(".gguf"))

    def set_model(self, name):
        """Persist a model choice to the data partition and restart the
        engine with it. Returns an error string, or None on success."""
        if "/" in name or not name.endswith(".gguf"):
            return "invalid model name"
        avail = self.available_models()
        if avail and name not in avail:
            return f"unknown model '{name}'. available: {', '.join(avail)}"
        cfg_dir = os.path.join(self.jail, "etc/as-os")
        os.makedirs(cfg_dir, exist_ok=True)
        with open(os.path.join(cfg_dir, "model"), "w") as f:
            f.write(name + "\n")
        self._restart_engine(name)
        return None

    def _restart_engine(self, name):
        """Kill the current llama-server and start one on the chosen model.
        The image's init also does this at boot; on a host, this is a no-op
        if no engine is running under our control."""
        import signal
        import subprocess as _sp
        # find and stop our engine
        try:
            pid = int(open("/tmp/as-os-engine.pid").read().strip())
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        except (OSError, ValueError):
            pass
        # start a new one in the background
        bin_dir = self.llama_cfg.get("bin_dir", "tools/llama.cpp/llama-b10333")
        model_path = os.path.join("models", name)
        port = int(self.llama_cfg.get("port", 8080))
        threads = int(self.llama_cfg.get("threads", 4))
        slots = int(self.llama_cfg.get("slots", 4))
        mask = self.llama_cfg.get("cpu_mask", "0,2,4,6")
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        bin_abs = os.path.join(root, bin_dir)
        cmd = [
            "taskset", "-c", mask,
            os.path.join(bin_abs, "llama-server"),
            "-m", os.path.join(root, model_path),
            "-c", str(8192 * slots), "-t", str(threads),
            "--parallel", str(slots),
            "-ctk", "q8_0", "-ctv", "q8_0",
            "--cache-prompt", "--cache-reuse", "64",
            "-rea", "on", "--reasoning-budget", "400",
            "--host", "127.0.0.1", "--port", str(port),
            "--temp", "0.2", "--top-k", "80", "--repeat-penalty", "1.05",
            "--no-webui", "--log-disable",
        ]
        self.log(f"restarting engine on model {name}")
        # CRITICAL: llama-server dlopens CPU backends relative to CWD — it
        # must run with cwd == bin_dir or it fails with "no backends loaded".
        proc = _sp.Popen(cmd, stdout=open("/tmp/as-os-engine.log", "a"),
                         stderr=_sp.STDOUT, cwd=bin_abs,
                         env={"LD_LIBRARY_PATH": bin_abs})
        with open("/tmp/as-os-engine.pid", "w") as f:
            f.write(str(proc.pid))
        self.engine = ModelEngine(self.llama_cfg, self.log)
        self._wait_engine(timeout=180)

    def _wait_engine(self, timeout=30):
        """Poll the engine health with backoff. The server can be briefly
        unreachable right after bind (still loading KV / under load), so a
        single ping is too brittle."""
        deadline = time.time() + timeout
        delay = 0.5
        while time.time() < deadline:
            if self.engine.ping():
                return True
            time.sleep(delay)
            delay = min(delay * 2, 3.0)
        return self.engine.ping()

    @property
    def current_user(self):
        return self._current_user

    @current_user.setter
    def current_user(self, value):
        self._current_user = value
        self.executor.current_user = value
        self.store.user = value

    @property
    def jail(self):
        return os.path.realpath(self.daemon_cfg["jail"])

    # ---- prompts ------------------------------------------------------------

    def shell_prompt(self):
        return build_shell_prompt(self.cfg, self.current_user)

    def interpreter_prompt(self):
        return build_interpreter_prompt(self.cfg, self.current_user)

    # ---- sessions ------------------------------------------------------------

    def new_session(self, name, temp=None, tools=None, system_prompt=None,
                    max_tokens=None, max_loops=None, time_budget=None,
                    layer="shell", keep_tool_msgs=False, tool_choice=None,
                    temp_session=False):
        engine = self.engine
        prompt = system_prompt or self.shell_prompt()
        toolset = tools if tools is not None else SHELL_TOOLS
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
            layer=layer,
            keep_tool_msgs=keep_tool_msgs,
            tool_choice=tool_choice,
            temp_session=temp_session,
        )
        self.sessions[name] = sess
        return sess

    def load_session(self, name, temp=None, max_tokens=None, slot=None):
        """Rebuild a Session object from a saved store entry. The system
        prompt is regenerated fresh so live data (uptime/apps/user) is
        current. Returns None if no such session is saved."""
        data = self.store.load(name)
        if data is None:
            return None
        if slot is None:
            nslots = int(self.llama_cfg["slots"])
            slot = self._slot_counter % nslots
            self._slot_counter += 1
        sess = Session.from_dict(
            data,
            self.engine,
            self.executor,
            system_prompt=self.shell_prompt(),
            slot=slot,
            chaos=self.chaos,
            name=name,
            log=self.log,
            tools=SHELL_TOOLS,
            max_tokens=max_tokens,
        )
        if temp is not None:
            sess.temp = temp
        self.sessions[name] = sess
        return sess

    def delete_session(self, name):
        self.sessions.pop(name, None)
        return self.store.delete(name)

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

    def run_oobe(self, ask_handler, on_event=None, force=False):
        if not force and os.path.exists(os.path.join(self.jail, "etc/as-os/configured")):
            return False
        self.log("running OOBE")
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

    def _handle_interpret(self, request):
        """Run a plain-English wish through the interpreter layer."""
        name = f"interp:{request[:30]}"
        sub = self.new_session(
            name,
            system_prompt=self.interpreter_prompt(),
            tools=INTERPRETER_TOOLS,
            temp=0.1,
            max_tokens=2048,
            max_loops=8,
            time_budget=120,
            layer="interpreter",
            tool_choice="required",
        )

        def sink(ev):
            for cb in self.stream_out:
                cb(("interpreter", name), ev)

        self.log(f"interpret: {request}")
        try:
            report = sub.user_turn(request, on_event=sink)
        except Exception as e:
            return f"[interpreter error] {e}"
        report = (report or "").strip()
        return report or "(interpreter produced no output)"

    def _handle_spawn(self, app, args):
        from aiscript import runner
        path = self._resolve_app(app)
        name = f"app:{os.path.basename(path)}"
        sub = self.new_session(
            name,
            system_prompt=self.interpreter_prompt(),
            tools=INTERPRETER_TOOLS,
            temp=0.1,
            max_tokens=2048,
            max_loops=32,
            time_budget=600,
            layer="interpreter",
            tool_choice="required",
        )

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
