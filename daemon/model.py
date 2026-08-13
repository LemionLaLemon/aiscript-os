import json
import re
import threading

import requests


_INVISIBLE_RE = re.compile(
    r"[\u200b-\u200d\u2060\u2062\u2063\ufeff\u00ad]")


def _strip_invisible(text):
    """Remove zero-width / invisible padding characters the model emits."""
    if not text:
        return text
    return _INVISIBLE_RE.sub("", text)


def _detect_repetition(content, recent, window=200):
    """Return True if the tail of `content` looks like a degenerate
    repetition loop (the model repeating a short phrase over and over).
    `recent` is a list of recently-emitted text chunks."""
    tail = content[-window:]
    if len(tail) < 40:
        return False
    # count how much of the tail is covered by its most common line
    lines = [l for l in tail.splitlines() if l.strip()]
    if not lines:
        return False
    unique = set(lines)
    if len(unique) <= 2 and len(lines) >= 6:
        return True
    # also flag a repeating character pattern (e.g. the same line twice)
    if len(lines) >= 4 and len(unique) * 2 <= len(lines):
        return True
    # Block repetition: a long content line repeats at intervals with short
    # separator lines (e.g. "...ANSWER\\n</think>\\n" wedged between repeats
    # of the real sentence). Count how often any long line repeats.
    long_lines = [l for l in lines if len(l) >= 15]
    if len(long_lines) >= 3:
        from collections import Counter
        counts = Counter(long_lines)
        if counts.most_common(1)[0][1] >= 3:
            return True
    return False


def _trim_repetition(content, window=200):
    """Cut the degenerate repetition tail out of the content so it isn't
    stored in the session history (which would fill the context window)."""
    if not content:
        return content
    lines = content.splitlines(keepends=True)
    # (1) exact consecutive chunk repetition (3+ identical 3-line chunks)
    n = len(lines)
    for i in range(n - 3):
        chunk = lines[i:i + 3]
        joined = "".join(chunk)
        if len(joined) < 4:
            continue
        repeat = 0
        j = i + 3
        while j + 3 <= n and "".join(lines[j:j + 3]) == joined:
            repeat += 1
            j += 3
        if repeat >= 3:
            return "".join(lines[:i]).rstrip()
    # (2) block repetition: a long content line appears 3+ times with short
    # separator lines between (e.g. "...?ANSWER\n</think>\n" wedged between
    # repeats). Keep the FIRST occurrence of the line (the real answer) and
    # cut from the second occurrence onward.
    from collections import Counter
    text_lines = [ln for ln in lines if ln.strip()]
    long_lines = [ln for ln in text_lines if len(ln.strip()) >= 15]
    if len(long_lines) >= 3:
        counts = Counter(long_lines)
        top = counts.most_common(1)[0]
        if top[1] >= 3:
            cut = top[0].strip()
            seen = 0
            for idx, ln in enumerate(lines):
                if ln.strip() == cut:
                    seen += 1
                    if seen == 2:
                        # keep through the first occurrence (end of that line)
                        kept = "".join(lines[:idx]).rstrip()
                        return _strip_tail_markers(kept)
    return content


def _strip_tail_markers(text):
    """Remove reasoning/repetition markers that leak onto the tail of an
    answer: 'ANSWER', '</think>', '```', stray separators."""
    import re as _re
    t = text
    prev = None
    while prev != t:
        prev = t
        # 'ANSWER' glued to the end of the last word (e.g. "...?ANSWER")
        t = _re.sub(r"(?i)answer$", "", t)
        t = t.replace("</think>", "")
        t = _re.sub(r"(?m)^\s*answer\s*$", "", t)
        t = _re.sub(r"\n{3,}", "\n\n", t)
        t = t.rstrip()
    return t


class ModelError(Exception):
    pass


class ContextOverflow(ModelError):
    """The request exceeded the server's context window. The session should
    compact its history and retry (or tell the user to start a fresh one)."""
    pass


class ModelEngine:
    """Client for a llama-server (OpenAI-compatible /v1/chat/completions)."""

    def __init__(self, cfg, logger=None):
        self.cfg = cfg
        self.model = cfg.get("model_name", "model.gguf")
        self.url = f"http://{cfg['host']}:{cfg['port']}"
        self._log = logger or (lambda *a, **k: None)

    # ---- low level --------------------------------------------------------

    def _payload(self, messages, tools, temp, slot, max_tokens, tool_choice):
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
        if tool_choice:
            body["tool_choice"] = tool_choice
        return body

    def chat(self, messages, tools=None, temp=0.15, slot=0, max_tokens=None,
             on_event=None, tool_choice="auto"):
        """Run one completion. Streams events via on_event and returns the
        full assistant message dict ({role, content?, tool_calls?})."""
        max_tokens = max_tokens or self.cfg.get("max_tokens", 1024)
        body = self._payload(messages, tools, temp, slot, max_tokens,
                             tool_choice)
        try:
            return self._chat_stream(body, tools, on_event)
        except ModelError:
            raise
        except requests.HTTPError as e:
            # some builds reject tools+stream; fall back to a single shot
            if e.response is not None and e.response.status_code == 500:
                self._log("falling back to non-streaming completion")
                return self._chat_single(body, tools, on_event)
            if e.response is not None and e.response.status_code == 400:
                err = (e.response.text or "").lower()
                if "exceed_context_size_error" in err or \
                   "exceeds the available context" in err:
                    raise ContextOverflow(
                        "context window exceeded — compacting history and "
                        "retrying"
                    )
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
                # The model pads its answers with zero-width spaces (\u200b).
                # Each one is a real token, so left alone they (a) stream as
                # invisible noise and (b) blow up the stored history — the
                # tokenizer counts 2000 of them as 2000 tokens. Drop them so
                # the answer and the history stay clean.
                tok = _strip_invisible(tok)
                if tok:
                    content += tok
                    emit({"type": "content", "text": tok})
                    # Degenerate repetition loop: the model repeats a short
                    # phrase forever instead of stopping. Cut the stream so
                    # we don't wait out the whole generation.
                    if _detect_repetition(content, None):
                        self._log("repetition loop detected — truncating")
                        break
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
                    tool_calls[idx]["function"]["name"] += _strip_invisible(fn["name"])
                if fn.get("arguments"):
                    tool_calls[idx]["function"]["arguments"] += _strip_invisible(
                        fn["arguments"])
                if tool_calls[idx]["function"]["name"]:
                    emit({
                        "type": "tool-delta",
                        "index": idx,
                        "name": tool_calls[idx]["function"]["name"],
                        "args": tool_calls[idx]["function"]["arguments"],
                    })

        if not tool_calls:
            return {"role": "assistant", "content": _trim_repetition(content)}
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
        if resp.status_code == 400:
            err = (resp.text or "").lower()
            if "exceed_context_size_error" in err or \
               "exceeds the available context" in err:
                raise ContextOverflow(
                    "context window exceeded — compacting history and retrying"
                )
        resp.raise_for_status()
        resp.encoding = "utf-8"
        data = resp.json()
        msg = data["choices"][0]["message"]
        if msg.get("content"):
            msg["content"] = _strip_invisible(msg["content"])
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
