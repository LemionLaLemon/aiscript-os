import json
import threading

import requests


class ModelError(Exception):
    pass


class ModelEngine:
    """Client for a llama-server (OpenAI-compatible /v1/chat/completions)."""

    def __init__(self, cfg, logger=None):
        self.cfg = cfg
        self.model = cfg.get("model_name", "model.gguf")
        self.url = f"http://{cfg['host']}:{cfg['port']}"
        self._log = logger or (lambda *a, **k: None)

    # ---- low level --------------------------------------------------------

    def _payload(self, messages, tools, temp, slot, max_tokens):
        body = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "temperature": temp,
            "top_p": self.cfg.get("top_p", 0.9),
            "max_tokens": max_tokens,
            "id_slot": slot,
        }
        if tools:
            body["tools"] = tools
        return body

    def chat(self, messages, tools=None, temp=0.15, slot=0, max_tokens=None,
             on_event=None):
        """Run one completion. Streams events via on_event and returns the
        full assistant message dict ({role, content?, tool_calls?})."""
        max_tokens = max_tokens or self.cfg.get("max_tokens", 1024)
        body = self._payload(messages, tools, temp, slot, max_tokens)
        try:
            return self._chat_stream(body, tools, on_event)
        except ModelError:
            raise
        except requests.HTTPError as e:
            # some builds reject tools+stream; fall back to a single shot
            if e.response is not None and e.response.status_code == 500:
                self._log("falling back to non-streaming completion")
                return self._chat_single(body, tools, on_event)
            raise

    # ---- streaming path ---------------------------------------------------

    def _chat_stream(self, body, tools, on_event):
        resp = requests.post(
            f"{self.url}/v1/chat/completions", json=body,
            stream=True, timeout=(30, 300),
        )
        resp.raise_for_status()
        resp.encoding = "utf-8"

        content = ""
        tool_calls = {}  # index -> dict
        order = []
        in_tool = [False]

        def emit(ev):
            if on_event:
                on_event(ev)

        for line in resp.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue
            choices = chunk.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            if delta.get("reasoning_content"):
                emit({"type": "thinking", "text": delta["reasoning_content"]})
            if delta.get("content"):
                tok = delta["content"]
                content += tok
                emit({"type": "content", "text": tok})
            for tc in delta.get("tool_calls") or []:
                idx = tc.get("index", 0)
                if idx not in tool_calls:
                    tool_calls[idx] = {
                        "id": tc.get("id") or f"call_{idx}",
                        "type": "function",
                        "function": {"name": "", "arguments": ""},
                    }
                    order.append(idx)
                    in_tool[0] = True
                fn = tc.get("function") or {}
                if fn.get("name"):
                    tool_calls[idx]["function"]["name"] += fn["name"]
                if fn.get("arguments"):
                    tool_calls[idx]["function"]["arguments"] += fn["arguments"]

        if not tool_calls:
            return {"role": "assistant", "content": content}
        emit({"type": "tool-stream-end"})
        message = {"role": "assistant", "content": content or None}
        # normalise: only keep well-formed calls
        calls = []
        for idx in order:
            tc = tool_calls[idx]
            try:
                json.loads(tc["function"]["arguments"] or "{}")
            except json.JSONDecodeError:
                continue  # malformed -> drop (daemon will steer the model)
            tc["function"]["arguments"] = tc["function"]["arguments"]
            calls.append(tc)
        if calls:
            message["tool_calls"] = calls
        return message

    # ---- non-streaming fallback -------------------------------------------

    def _chat_single(self, body, tools, on_event):
        body["stream"] = False
        resp = requests.post(
            f"{self.url}/v1/chat/completions", json=body,
            timeout=(30, 300),
        )
        resp.raise_for_status()
        resp.encoding = "utf-8"
        data = resp.json()
        msg = data["choices"][0]["message"]
        if on_event and msg.get("content"):
            on_event({"type": "content", "text": msg["content"]})
        return msg

    # ---- misc ---------------------------------------------------------------

    def ping(self):
        try:
            r = requests.get(f"{self.url}/health", timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    def busy(self):
        """Is the engine currently generating (used by UI to show spinner)."""
        return self._busy

    def start_busy(self):
        self._busy = True

    def stop_busy(self):
        self._busy = False
