import json
import time

from .tools import SHELL_TOOLS, INTERPRETER_TOOLS, ToolExecutor


class Session:
    """One conversational context = one 'AI session' (a llama-server slot)."""

    MAX_TOOL_LOOPS = 16

    def __init__(self, engine, executor, system_prompt, slot=0, temp=0.15,
                 chaos=None, name="session", log=None, tools=None,
                 max_tokens=None, max_loops=None, time_budget=None,
                 layer="shell"):
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

    # ---- public ------------------------------------------------------------

    def inject(self, content):
        """Inject raw context (e.g. an imported module body)."""
        self.messages.append({"role": "user",
                              "content": f"[system context injection]\n{content}"})

    def reset(self):
        self.messages = [{"role": "system", "content": self.system_prompt}]

    def _request_messages(self):
        """Cache-friendly wire form of the history.

        Assistant tool-call messages are dropped: llama.cpp re-tokenizes a
        stored tool-call message differently on re-send, which breaks the
        prompt cache and forces a full prefill on the very next request
        (measured ~13s on the 2B). The tool RESULT is kept and tagged with
        the tool name so the model still knows what ran.
        """
        out = []
        for m in self.messages:
            if m["role"] == "assistant" and m.get("tool_calls"):
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

        # Emit thinking phase
        on_event({"type": "phase", "state": "thinking", "layer": self.layer})

        for i in range(self.max_loops):
            if self.time_budget and time.time() - started > self.time_budget:
                return (
                    f"(turn ran for over {int(self.time_budget)}s and gave up; "
                    f"try a smaller ask)"
                )
            events = []
            hook = lambda e: (events.append(e), on_event(e))
            msg = self.engine.chat(
                self._request_messages(), tools=self.tools, temp=self.temp,
                slot=self.slot, max_tokens=self.max_tokens, on_event=hook,
            )
            if not msg.get("tool_calls"):
                self.messages.append(msg)
                content = msg.get("content") or ""
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
                hook({"type": "tool", "name": tool, "args": args})
                result = self._exec_tool(tool, args)
                hook({"type": "tool-result", "name": tool, "result": result})
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", f"call_{i}"),
                    "content": result,
                    "_tool": tool,
                })
        return "(agent loop ran too long; giving up)"

    # ---- internals -----------------------------------------------------------

    def _apply_chaos(self, tool, args):
        if self.chaos and tool in ("list", "read", "run", "search"):
            return self.chaos.mutate(tool, args)
        return tool, args

    def _exec_tool(self, tool, args):
        try:
            return self.executor.execute(tool, args, chrooted=self._chrooted)
        except Exception as e:
            return f"[error] {e}"
