import datetime
import json
import tempfile
import unittest
from unittest.mock import patch

from daemon.model import ModelEngine, _separate_reasoning
from daemon.tools import ToolExecutor


class ModelOutputTests(unittest.TestCase):
    def test_close_only_reasoning_leak_is_separated(self):
        reasoning, answer = _separate_reasoning(
            "I should inspect the tool result first.</think>今日は2026年です。")
        self.assertEqual(reasoning, "I should inspect the tool result first.")
        self.assertEqual(answer, "今日は2026年です。")

    def test_tagged_reasoning_leak_is_separated(self):
        reasoning, answer = _separate_reasoning(
            "<think>private scratch</think>The answer is 2026.")
        self.assertEqual(reasoning, "private scratch")
        self.assertEqual(answer, "The answer is 2026.")

    def test_stream_never_emits_close_tag_or_scratch_as_content(self):
        class Response:
            encoding = None

            def raise_for_status(self):
                pass

            def iter_lines(self, decode_unicode=True):
                chunks = ["scratch reasoning", "</think>", "今日は2026年です。"]
                for chunk in chunks:
                    yield "data: " + json.dumps({
                        "choices": [{"delta": {"content": chunk}}]
                    })
                yield "data: [DONE]"

        engine = ModelEngine({"host": "127.0.0.1", "port": 1})
        events = []
        with patch("daemon.model.requests.post", return_value=Response()):
            message = engine._chat_stream({}, [], events.append)
        content = "".join(e["text"] for e in events
                          if e["type"] == "content")
        thinking = "".join(e["text"] for e in events
                           if e["type"] == "thinking")
        self.assertEqual(content, "今日は2026年です。")
        self.assertEqual(message["content"], content)
        self.assertEqual(thinking, "scratch reasoning")
        self.assertNotIn("</think>", content)

    def test_info_reports_current_date_not_kernel_build_date(self):
        with tempfile.TemporaryDirectory() as jail:
            executor = ToolExecutor({"daemon": {"jail": jail}})
            result = executor.info()
        today = datetime.datetime.now().astimezone().date().isoformat()
        self.assertIn(f"current local date: ", result)
        self.assertIn(today, result)
        self.assertNotIn("GNU/Linux", result)


if __name__ == "__main__":
    unittest.main()
