import json
import os
import re
import time

from .tools import SHELL_TOOLS, INTERPRETER_TOOLS, ToolExecutor
from .model import ContextOverflow


class Session:
    """One conversational context = one 'AI session' (a llama-server slot)."""

    MAX_TOOL_LOOPS = 16

    def __init__(self, engine, executor, system_prompt, slot=0, temp=0.15,
                 chaos=None, name="session", log=None, tools=None,
                 max_tokens=None, max_loops=None, time_budget=None,
                 layer="shell", keep_tool_msgs=False, tool_choice=None,
                 temp_session=False, cwd=None):
        self.engine = engine
        self.executor = executor
        self.system_prompt = system_prompt
        self.slot = slot
        self.temp = temp
        self.chaos = chaos
        self.name = name
        self._log = log or (lambda *a, **k: None)
        self.tools = tools if tools is not None else SHELL_TOOLS
        self.max_tokens = max_tokens
        self.max_loops = max_loops or self.MAX_TOOL_LOOPS
        self.time_budget = time_budget
        self.messages = [{"role": "system", "content": system_prompt}]
        self.layer = layer  # "shell" or "interpreter"
        self._chrooted = (layer == "interpreter")
        self.keep_tool_msgs = keep_tool_msgs
        # None = classify per turn (shell); "required"/"auto" = force for all
        self.tool_choice = tool_choice
        self.temp_session = temp_session
        self.name_locked = False
        self._auto_name_turns = 0
        # working directory (jail-relative, e.g. "home/demo/Documents")
        self.cwd = cwd or self._default_cwd()

    # ---- public ------------------------------------------------------------

    def inject(self, content):
        """Inject raw context (e.g. an imported module body)."""
        self.messages.append({"role": "user",
                              "content": f"[system context injection]\n{content}"})

    def reset(self):
        self.messages = [{"role": "system", "content": self.system_prompt}]

    # ---- serialization -------------------------------------------------------

    def turn_count(self):
        """Number of user turns in this session."""
        return sum(1 for m in self.messages if m["role"] == "user")

    def est_tokens(self):
        """Rough context-length estimate (words * 1.3 tokens/word, plus one
        token per zero-width char, which the tokenizer really does count)."""
        total = 0
        for m in self.messages:
            c = str(m.get("content") or "")
            total += len(c.split()) * 1.3
            total += len(re.findall(r"[\u200b-\u200d\ufeff]", c))
        return int(total)

    def to_dict(self):
        return {
            "name": self.name,
            "temp": self.temp,
            "layer": self.layer,
            "temp_session": self.temp_session,
            "name_locked": self.name_locked,
            "cwd": self.cwd,
            "messages": self.messages,
        }

    @classmethod
    def from_dict(cls, data, engine, executor, system_prompt, slot=0,
                  chaos=None, log=None, tools=None, max_tokens=None,
                  max_loops=None, time_budget=None, tool_choice=None,
                  name=None):
        sess = cls(
            engine, executor, system_prompt,
            slot=slot, temp=data.get("temp", 0.15), chaos=chaos,
            name=name or data.get("name", "session"), log=log,
            tools=tools, max_tokens=max_tokens, max_loops=max_loops,
            time_budget=time_budget, layer=data.get("layer", "shell"),
            tool_choice=tool_choice,
            temp_session=data.get("temp_session", False),
            cwd=data.get("cwd"),
        )
        sess.messages = list(data.get("messages", []))
        if not sess.messages or sess.messages[0]["role"] != "system":
            sess.messages.insert(0, {"role": "system", "content": system_prompt})
        else:
            # System prompt is rebuilt fresh (uptime/apps are live).
            sess.messages[0] = {"role": "system", "content": system_prompt}
        sess.name_locked = bool(data.get("name_locked", False))
        return sess

    # ---- tool_choice classification -------------------------------------------

    _ACTION_HINT_RE = re.compile(
        r'\b(install|uninstall|list|ls|cat|less|run|spawn|vibe|interpret|'
        r'write|create|make|build|download|fetch|read|show me|open|cowsay|'
        r'search|find|cd|man|add|delete|remove|copy|move|rename|chmod|mkdir|'
        r'login|create_user|save|store|downloads|desktop|documents|directory|'
        r'folder)\b',
        re.IGNORECASE)

    _WHAT_IN_RE = re.compile(
        r"^what('s| is| are)\s+in\b",
        re.IGNORECASE)

    _QUESTION_RE = re.compile(
        r'^(why|explain|describe|define|what is|what are|how does|how do|'
        r'what does|tell me about|do you think|is it)\b',
        re.IGNORECASE)

    _TRIVIAL_RE = re.compile(
        r'^(hi|hello|hey|yo|sup|thanks|thank you|ok|okay|good|bye|'
        r'welcome back|morning|afternoon|night|whats up|what\'s up|'
        r'how are you|how r u)[!.]?$',
        re.IGNORECASE)

    @classmethod
    def _classify_turn(cls, text):
        """Classify a user turn as a pure QUESTION (tool_choice=auto, may
        answer without calling a tool) or an ACTION (tool_choice=required,
        must emit a structured tool call)."""
        t = (text or "").strip()
        if not t:
            return "auto"
        if cls._TRIVIAL_RE.match(t):
            return "auto"
        if cls._ACTION_HINT_RE.search(t):
            return "required"
        if cls._WHAT_IN_RE.match(t):
            return "required"
        if cls._QUESTION_RE.match(t) or t.endswith("?"):
            return "auto"
        return "required"

    def _effective_tool_choice(self, text):
        if self.tool_choice:
            return self.tool_choice
        return self._classify_turn(text)

    # ---- working directory --------------------------------------------------

    def _default_cwd(self):
        """The user's home as a jail-relative path (e.g. home/demo)."""
        base = "home"
        user = getattr(self.executor, "current_user", None) or "user"
        return f"{base}/{user}" if user else base

    def _display_cwd(self):
        """cwd for humans: '~' at home, '~/Documents' inside Documents."""
        home = self._default_cwd()
        if self.cwd == home:
            return "~"
        if self.cwd.startswith(home + "/"):
            return "~/" + self.cwd[len(home) + 1:]
        return self.cwd

    def resolve_path(self, path):
        """Resolve a tool path against the session cwd.
        Rules: '.'/'' -> cwd; '~/x' -> home; '/x' -> jail root; else cwd/x.
        Returns a jail-relative path (no leading slash)."""
        if not path or path == ".":
            return self.cwd
        path = str(path)
        if path == "~":
            return self._default_cwd()
        if path.startswith("~/"):
            return self._default_cwd() + "/" + path[2:]
        if path.startswith("/"):
            return path.lstrip("/")
        return self.cwd + "/" + path

    def _exec_cd(self, path):
        """Handle the cd tool: validate the target dir and update cwd."""
        target = self.resolve_path(path)
        real = os.path.join(self.executor.jail, target)
        real = os.path.realpath(real)
        if not real.startswith(os.path.realpath(self.executor.jail) + os.sep) \
                and real != os.path.realpath(self.executor.jail):
            return f"[cd] {path}: escapes the sandbox"
        if not os.path.isdir(real):
            return f"[cd] {target}: not a directory"
        self.cwd = os.path.normpath(target)
        return f"now in {self._display_cwd()}"

    def _request_messages(self):
        """Cache-friendly wire form of the history.

        Assistant tool-call messages are dropped (unless keep_tool_msgs is
        set): llama.cpp re-tokenizes a stored tool-call message differently
        on re-send, which breaks the prompt cache and forces a full prefill
        on the very next request (measured ~13s on the 2B). The tool RESULT
        is kept and tagged with the tool name so the model still knows what
        ran. Sessions that need the model to see its own prior actions
        (e.g. OOBE) pass keep_tool_msgs=True and eat the cache cost.
        """
        out = []
        # Preempt context overflow: if history is getting long, compact it
        # before sending (keeps the prefill small too). The engine context
        # is 8192; the response needs up to max_tokens more, so keep the
        # prompt comfortably below the window.
        max_tokens = self.max_tokens or 2048
        limit = 8192 - max_tokens - 512
        if self.est_tokens() > limit:
            self._compact_history(target=limit - 512)
        for m in self.messages:
            if m["role"] == "assistant" and m.get("tool_calls"):
                if not self.keep_tool_msgs:
                    continue
            if m["role"] == "tool":
                nm = dict(m)
                name = m.get("_tool")
                if name:
                    nm["content"] = f"[{name}] {nm['content']}"
                out.append(nm)
            else:
                out.append(m)
        return out
    def _compact_history(self, target=5200):
        """Drop the oldest tool/assistant messages so the history fits the
        context window again. Always keeps the system prompt and the most
        recent turns. Call this when the engine reports a context overflow
        (or to keep the prefill small)."""
        # Cheap estimate: words * 1.3 ≈ tokens (+ zero-width chars).
        while len(self.messages) > 4:
            if self.est_tokens() <= target:
                break
            # drop the oldest non-system message
            for idx in range(1, len(self.messages)):
                m = self.messages[idx]
                if m["role"] in ("tool", "assistant"):
                    del self.messages[idx]
                    break
            else:
                del self.messages[1]

    def user_turn(self, text, on_event=None, tool_choice=None):
        """Run a full agent loop for a user message, streaming events."""
        self.messages.append({"role": "user", "content": text})
        if tool_choice is not None:
            self.tool_choice = tool_choice
        return self._loop(on_event)

    def continue_turn(self, text, on_event=None, tool_choice=None):
        """Same as user_turn but the message is tagged as a continuation
        (used by the aiscript runner)."""
        self.messages.append({"role": "user", "content": f"<continuing> {text}"})
        if tool_choice is not None:
            self.tool_choice = tool_choice
        return self._loop(on_event)

    # ---- core loop ----------------------------------------------------------

    def _loop(self, on_event):
        started = time.time()
        recent_calls = []
        on_event = on_event or (lambda e: None)
        all_events = []

        # Decide tool_choice for this turn from the latest user message.
        last_user = ""
        for m in reversed(self.messages):
            if m["role"] == "user":
                last_user = m.get("content") or ""
                break
        tool_choice = self._effective_tool_choice(last_user)

        # Emit thinking phase
        on_event({"type": "phase", "state": "thinking", "layer": self.layer})

        for i in range(self.max_loops):
            if self.time_budget and time.time() - started > self.time_budget:
                return (
                    f"(turn ran for over {int(self.time_budget)}s and gave up; "
                    f"try a smaller ask)"
                )
            events = []
            hook = lambda e: (events.append(e), all_events.append(e), on_event(e))
            try:
                msg = self.engine.chat(
                    self._request_messages(), tools=self.tools, temp=self.temp,
                    slot=self.slot, max_tokens=self.max_tokens, on_event=hook,
                    tool_choice=tool_choice,
                )
            except ContextOverflow:
                self._log("context overflow — compacting history and retrying")
                self._compact_history()
                msg = self.engine.chat(
                    self._request_messages(), tools=self.tools, temp=self.temp,
                    slot=self.slot, max_tokens=self.max_tokens, on_event=hook,
                    tool_choice=tool_choice,
                )
            if not msg.get("tool_calls"):
                # The model sometimes writes a tool call as plain text (e.g.
                # `spawn(app="cowsay")`) instead of emitting a structured
                # tool_calls response. If content contains a valid call to a
                # known tool, execute it instead of showing the text. It can
                # also emit a hallucinated JSON 'agent command' blob; catch
                # that too.
                content = msg.get("content") or ""
                text_call = self._extract_text_tool_call(content)
                if text_call is None:
                    text_call = self._extract_xml_tool_call(content)
                if text_call is None:
                    text_call = self._extract_json_command_call(content)
                if text_call:
                    tool, args = text_call
                    msg = {"role": "assistant", "content": None,
                           "tool_calls": [{
                               "id": f"textcall_{i}",
                               "type": "function",
                               "function": {"name": tool,
                                            "arguments": json.dumps(args)},
                           }]}
                    self.messages.append(msg)
                    on_event({"type": "phase", "state": "running"})
                    recent_calls.append((tool, args))
                    if len(recent_calls) > 4:
                        recent_calls.pop(0)
                    self._run_tool(tool, args, i, recent_calls, hook)
                    continue
                self.messages.append(msg)
                content = msg.get("content") or ""
                # Strip LFM reasoning-chain leakage from content
                content = self._strip_reasoning(content)
                # If content is empty but tools were called, use last tool result
                if not content.strip() and all_events:
                    last_result = None
                    for e in reversed(all_events):
                        if e.get("type") == "tool-result":
                            last_result = e.get("result", "")
                            break
                    if last_result:
                        content = last_result
                if content.strip():
                    on_event({"type": "phase", "state": "answering",
                              "layer": self.layer})
                    return content
                # The model went quiet: nudge it once and retry instead of
                # giving up silently.
                nudge = ("[system] You produced no action and no answer. "
                         "Respond now: either call a tool to do the task, or "
                         "if you are unsure how, read the manual with "
                         "spawn(app=\"man\", args=[\"tools\"]) and then act. "
                         "Never return empty.")
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": f"quiet_{i}",
                    "content": nudge,
                    "_tool": "system",
                })
                if i + 1 < self.max_loops:
                    continue
                on_event({"type": "phase", "state": "answering",
                          "layer": self.layer})
                return "(kernel-2 went quiet. Try asking differently, or say 'man' to read the manual.)"
            self.messages.append(msg)
            # Emit running phase before tool exec
            on_event({"type": "phase", "state": "running"})
            for tc in msg["tool_calls"]:
                fn = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                tool, args = self._apply_chaos(fn, args)
                recent_calls.append((tool, args))
                if len(recent_calls) > 4:
                    recent_calls.pop(0)
                exact_repeat = recent_calls.count((tool, args)) > 1
                stuck_on_tool = (len(recent_calls) >= 3
                                 and all(t == tool for t, _ in recent_calls[-3:]))
                if exact_repeat or stuck_on_tool:
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", f"call_{i}"),
                        "content": (
                            "[repeated call] you are repeating "
                            + ("exactly this call" if exact_repeat
                               else f"{tool} over and over")
                            + ". Use the results you already have and move on, "
                            "or call something different. Do not repeat it."
                        ),
                        "_tool": tool,
                    })
                    continue
                result = self._run_tool(tool, args, i, recent_calls, hook)
        return "(agent loop ran too long; giving up)"

    # ---- internals -----------------------------------------------------------

    def _run_tool(self, tool, args, idx, recent_calls, hook=None):
        """Execute a parsed tool call, emitting events and recording the
        tool result message. Returns the result string."""
        hook = hook or (lambda e: None)
        hook({"type": "tool", "name": tool, "args": args})
        result = self._exec_tool(tool, args)
        hook({"type": "tool-result", "name": tool, "result": result})
        self.messages.append({
            "role": "tool",
            "tool_call_id": f"call_{idx}",
            "content": result,
            "_tool": tool,
        })
        return result

    _REASONING_PATTERNS = [
        re.compile(r'^The user asks?:', re.IGNORECASE),
        re.compile(r'^We (need|can|should|must|have|are|want)', re.IGNORECASE),
        re.compile(r'^However,', re.IGNORECASE),
        re.compile(r'^So (we|the|I)', re.IGNORECASE),
        re.compile(r'^The (previous|current|assistant|system)', re.IGNORECASE),
        re.compile(r'^But (note|we|the)', re.IGNORECASE),
        re.compile(r'^Now (we|the|I)', re.IGNORECASE),
        re.compile(r'^Let me', re.IGNORECASE),
        re.compile(r'^First,', re.IGNORECASE),
        re.compile(r'^\d+\.\s', re.IGNORECASE),
    ]

    @classmethod
    def _strip_reasoning(cls, content):
        """Remove LFM's reasoning-chain preamble that leaks into content tokens."""
        if not content:
            return ""
        lines = content.split("\n")
        clean = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                clean.append(line)
                continue
            if any(p.match(stripped) for p in cls._REASONING_PATTERNS):
                continue
            clean.append(line)
        return "\n".join(clean).strip()

    def _apply_chaos(self, tool, args):
        if self.chaos and tool in ("list", "read", "run", "search"):
            return self.chaos.mutate(tool, args)
        return tool, args

    _TEXT_CALL_RE = re.compile(
        r'(?<![\w"])'
        r'(list|read|write|append|run|search|calc|info|ask|draw|spawn|vibe|'
        r'interpret|delete|move|copy|mkdir|shutdown|create_user)\s*\(',
        re.IGNORECASE)

    # `[run] mkdir path`, `[mkdir] path`, `[spawn] cowsay hello` bracket
    # directive the model sometimes emits instead of a structured call.
    _BRACKET_CALL_RE = re.compile(
        r'^\s*[-*_> ]*\[(list|read|write|append|run|search|calc|info|ask|'
        r'draw|spawn|vibe|interpret|delete|move|copy|mkdir|shutdown|'
        r'create_user)\]\s*([^\n]*)',
        re.IGNORECASE | re.MULTILINE)

    def _extract_text_tool_call(self, content):
        """If the model wrote a tool call as plain text (e.g.
        `spawn(app="cowsay", args=[])`) instead of emitting tool_calls,
        parse the last such invocation into (tool, args). Returns None if
        the content is not primarily a tool call."""
        if not content:
            return None
        # Must look like a call, not prose mentioning a tool name.
        m = self._TEXT_CALL_RE.search(content)
        if not m:
            # Fall back to a `[tool] arg` bracket directive (e.g.
            # "[run] mkdir home/user/Documents/asm-calc").
            return self._extract_bracket_tool_call(content)
        tool = m.group(1).lower()
        known = {t["function"]["name"] for t in self.tools}
        if tool not in known:
            return None
        # Find the balanced paren after the tool name.
        open_idx = content.find("(", m.start())
        depth, end = 0, -1
        for j in range(open_idx, len(content)):
            if content[j] == "(":
                depth += 1
            elif content[j] == ")":
                depth -= 1
                if depth == 0:
                    end = j
                    break
        if end < 0:
            return None
        args_str = content[open_idx + 1:end]
        args = self._parse_text_args(args_str)
        if args is None:
            return None
        # Only treat it as a tool call if a real call dominates the content
        # (i.e. the line is a call, possibly wrapped in brackets/markdown).
        line = content[m.start():end + 1].strip()
        if not line:
            return None
        return tool, args

    # `<function-call>toolname(args)</function-call>` — the XML-ish wrapper
    # some models emit. The body is the same toolname(args) syntax.
    _XML_CALL_RE = re.compile(
        r'<function-call>\s*(.*?)\s*</function-call>',
        re.IGNORECASE | re.DOTALL)

    def _extract_xml_tool_call(self, content):
        """Parse a `<function-call>toolname(args)</function-call>` wrapper
        into (tool, args). The model sometimes emits this instead of a
        structured tool_calls response. Returns None if not a valid call."""
        if not content:
            return None
        m = self._XML_CALL_RE.search(content)
        if not m:
            return None
        body = m.group(1).strip()
        # body may be "toolname(args)" or a JSON blob; reuse existing parsers
        inner = self._extract_text_tool_call(body)
        if inner:
            return inner
        inner = self._extract_json_command_call(body)
        if inner:
            return inner
        return None

    def _extract_bracket_tool_call(self, content):
        """Parse a `[tool] arg` bracket directive like
        `[run] mkdir home/user/Documents/asm-calc` into (tool, args).
        Returns None if content is not primarily such a directive."""
        if not content:
            return None
        m = self._BRACKET_CALL_RE.search(content)
        if not m:
            return None
        tool = m.group(1).lower()
        known = {t["function"]["name"] for t in self.tools}
        if tool not in known:
            return None
        rest = m.group(2).strip().strip("`\"").strip()
        # no-arg tools like info/shutdown may appear as a bare `[info]`
        if not rest:
            if tool in ("info", "shutdown"):
                return tool, {}
            return None
        # `[run] <cmd...>` -> run with the full command
        if tool == "run":
            return tool, {"command": rest}
        if tool in ("list", "read", "mkdir", "delete", "search"):
            return tool, {"path": rest}
        if tool in ("calc",):
            return tool, {"expr": rest}
        if tool in ("info",):
            return tool, {}
        # spawn/vibe/interpret need structured args. The rest may be
        # comma-separated (`app="cowsay", args=[]`) or space-separated
        # (`app="cowsay" args=[]`); pick the split by what's actually there.
        if tool == "vibe":
            parts = rest.split()
            if len(parts) >= 2:
                return tool, {"action": parts[0], "target": parts[1],
                              "flags": parts[2:]}
            return None
        sep = "," if "," in rest else None
        args = self._parse_text_args(rest, sep=sep)
        if args:
            return tool, args
        return None

    def _parse_text_args(self, args_str, sep=","):
        """Parse `key="value"` / `key=value` comma-separated args into a dict.
        Lists like args=[] or args=["a","b"] become real lists. When sep is
        None, split on runs of whitespace instead of commas."""
        args = {}
        for part in (args_str.split(sep) if sep else args_str.split()):
            part = part.strip()
            if not part:
                continue
            if "=" in part:
                k, _, v = part.partition("=")
                k = k.strip()
                v = v.strip()
                if v.startswith("[") and v.endswith("]"):
                    inner = v[1:-1].strip()
                    if not inner:
                        args[k] = []
                    else:
                        args[k] = [x.strip().strip("\"'")
                                   for x in inner.split(",")]
                elif (v.startswith('"') and v.endswith('"')) or \
                     (v.startswith("'") and v.endswith("'")):
                    args[k] = v[1:-1]
                else:
                    args[k] = v
            else:
                # positional: use as "value" (e.g. list(".") -> path)
                args.setdefault("value", part.strip().strip("\"'"))
        return args

    def _extract_json_command_call(self, content):
        """Detect a hallucinated JSON 'agent command' blob like
        {"analysis": ..., "commands": [{"keystrokes": "ls\\n", ...}], ...}
        and turn it into a real run() call. Returns (tool, args) or None.
        This catches the model drifting into a terminal-agent JSON format
        instead of emitting a structured tool_calls response."""
        if not content:
            return None
        # Try to find a JSON object in the content
        start = content.find("{")
        end = content.rfind("}")
        if start < 0 or end <= start:
            return None
        blob = content[start:end + 1]
        try:
            data = json.loads(blob)
        except Exception:
            return None
        if not isinstance(data, dict):
            return None
        # shape: {"tool": "name", "args": {...}} — a direct tool+args object
        tool_name = data.get("tool") or data.get("name") or data.get("function")
        if tool_name and isinstance(tool_name, str):
            tool_name = tool_name.strip().lower()
            known = {t["function"]["name"] for t in self.tools}
            if tool_name in known:
                args = data.get("args") or data.get("arguments") or {}
                if isinstance(args, dict):
                    return tool_name, args
        cmds = data.get("commands") or data.get("command")
        if not cmds:
            return None
        if isinstance(cmds, dict):
            cmds = [cmds]
        if not isinstance(cmds, list):
            return None
        keystrokes = []
        for c in cmds:
            if isinstance(c, dict):
                ks = c.get("keystrokes") or c.get("command") or c.get("cmd")
                if isinstance(ks, str) and ks.strip():
                    keystrokes.append(ks.strip())
        if not keystrokes:
            return None
        # Join multi-line into a single run command (newlines -> ;)
        command = " ; ".join(
            k.replace("\n", " ; ") for k in keystrokes if k.strip()
        )
        if not command:
            return None
        return "run", {"command": command}

    def _exec_tool(self, tool, args):
        try:
            args = args or {}
            # cwd-aware tools
            if tool == "cd":
                return self._exec_cd(args.get("path") or ".")
            if tool == "pwd":
                return self._display_cwd()
            # Resolve path/src/dst args against the session cwd.
            if tool in ("list", "read", "write", "append", "search", "delete",
                        "mkdir"):
                if args.get("path"):
                    args = dict(args)
                    args["path"] = self.resolve_path(args["path"])
            elif tool in ("move", "copy"):
                args = dict(args)
                if args.get("src"):
                    args["src"] = self.resolve_path(args["src"])
                if args.get("dst"):
                    args["dst"] = self.resolve_path(args["dst"])
            # run always executes inside the chrooted jail — never on the
            # host. There is no host shell to escape to (ascOS ships none).
            if tool == "run":
                return self.executor.execute(tool, args, chrooted=True,
                                             cwd=self.cwd)
            return self.executor.execute(tool, args, chrooted=self._chrooted)
        except Exception as e:
            return f"[error] {e}"
