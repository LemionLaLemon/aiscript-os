import json
import re
import time

from .tools import SHELL_TOOLS, INTERPRETER_TOOLS, ToolExecutor


class Session:
    """One conversational context = one 'AI session' (a llama-server slot)."""

    MAX_TOOL_LOOPS = 16

    def __init__(self, engine, executor, system_prompt, slot=0, temp=0.15,
                 chaos=None, name="session", log=None, tools=None,
                 max_tokens=None, max_loops=None, time_budget=None,
                 layer="shell", keep_tool_msgs=False):
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

    # ---- public ------------------------------------------------------------

    def inject(self, content):
        """Inject raw context (e.g. an imported module body)."""
        self.messages.append({"role": "user",
                              "content": f"[system context injection]\n{content}"})

    def reset(self):
        self.messages = [{"role": "system", "content": self.system_prompt}]

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

    def user_turn(self, text, on_event=None):
        """Run a full agent loop for a user message, streaming events."""
        self.messages.append({"role": "user", "content": text})
        return self._loop(on_event)

    def continue_turn(self, text, on_event=None):
        """Same as user_turn but the message is tagged as a continuation
        (used by the aiscript runner)."""
        self.messages.append({"role": "user", "content": f"<continuing> {text}"})
        return self._loop(on_event)

    # ---- core loop ----------------------------------------------------------

    def _loop(self, on_event):
        started = time.time()
        recent_calls = []
        on_event = on_event or (lambda e: None)
        all_events = []

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
            msg = self.engine.chat(
                self._request_messages(), tools=self.tools, temp=self.temp,
                slot=self.slot, max_tokens=self.max_tokens, on_event=hook,
            )
            if not msg.get("tool_calls"):
                # The model sometimes writes a tool call as plain text (e.g.
                # `spawn(app="cowsay")`) instead of emitting a structured
                # tool_calls response. If content contains a valid call to a
                # known tool, execute it instead of showing the text.
                text_call = self._extract_text_tool_call(
                    msg.get("content") or "")
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
                # Emit answer phase
                on_event({"type": "phase", "state": "answering", "layer": self.layer})
                return content if content.strip() else "(kernel-2 went quiet.)"
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
            return None
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

    def _parse_text_args(self, args_str):
        """Parse `key="value"` / `key=value` comma-separated args into a dict.
        Lists like args=[] or args=["a","b"] become real lists."""
        args = {}
        for part in args_str.split(","):
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

    def _exec_tool(self, tool, args):
        try:
            return self.executor.execute(tool, args, chrooted=self._chrooted)
        except Exception as e:
            return f"[error] {e}"
