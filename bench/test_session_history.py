import json
import os
import tempfile
import unittest

from daemon.session import Session
from daemon.tools import ToolExecutor


class RecordingEngine:
    cfg = {}

    def __init__(self, answer="No match was found."):
        self.requests = []
        self.answer = answer

    def chat(self, messages, **kwargs):
        self.requests.append(messages)
        if len(self.requests) == 1:
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "search-123",
                    "type": "function",
                    "function": {
                        "name": "search",
                        "arguments": json.dumps({
                            "path": ".", "pattern": "needle.txt",
                        }),
                    },
                }],
            }
        return {"role": "assistant", "content": self.answer}


class Executor:
    jail = "/tmp"
    current_user = "demo"

    def execute(self, tool, args, chrooted=False, cwd="."):
        return "no matches"


class SessionHistoryTests(unittest.TestCase):
    def test_active_turn_keeps_complete_tool_call_and_matching_result(self):
        engine = RecordingEngine()
        session = Session(engine, Executor(), system_prompt="policy")
        answer = session.user_turn("needle.txt wa doko desu ka")
        self.assertEqual(answer, "No match was found.")

        wire = engine.requests[1]
        self.assertEqual([m["role"] for m in wire],
                         ["system", "user", "assistant", "tool"])
        call = wire[2]["tool_calls"][0]
        self.assertEqual(call["id"], "search-123")
        self.assertEqual(wire[3]["tool_call_id"], "search-123")
        self.assertEqual(wire[3]["content"], "[search] no matches")

    def test_completed_turn_drops_old_tool_mechanics(self):
        engine = RecordingEngine()
        session = Session(engine, Executor(), system_prompt="policy")
        session.user_turn("needle.txt wa doko desu ka")
        session.messages.append({"role": "user", "content": "thanks"})
        wire = session._request_messages()
        self.assertEqual([m["role"] for m in wire],
                         ["system", "user", "assistant", "user"])

    def test_filename_search_gets_answer_only_model_round(self):
        answer_text = ("ge-bwr5.txt exists at /home/demo/ge-bwr5.txt. "
                       "What would you like to do with it?")
        engine = RecordingEngine(answer=answer_text)

        class FilenameExecutor(Executor):
            def execute(self, tool, args, chrooted=False, cwd="."):
                return "filename matches:\n/home/demo/ge-bwr5.txt"

        session = Session(engine, FilenameExecutor(), system_prompt="policy")
        answer = session.user_turn("ge-bwr5.txt wa doko desu ka")
        self.assertEqual(answer, answer_text)
        self.assertEqual(len(engine.requests), 2)

    def test_unknown_language_is_not_forced_to_call_a_tool(self):
        self.assertEqual(Session._classify_turn("英語は話せません"), "auto")

    def test_old_direct_result_turn_is_closed_before_resumed_user(self):
        session = Session(RecordingEngine(), Executor(), system_prompt="policy")
        session.messages.extend([
            {"role": "user", "content": "where is note.txt"},
            {"role": "assistant", "content": None, "tool_calls": [{
                "id": "old-call", "type": "function",
                "function": {"name": "search", "arguments": "{}"},
            }]},
            {"role": "tool", "tool_call_id": "old-call",
             "content": "filename matches:\n/home/demo/note.txt",
             "_tool": "search"},
            {"role": "user", "content": "英語は話せません"},
        ])
        wire = session._request_messages()
        self.assertEqual([m["role"] for m in wire],
                         ["system", "user", "assistant", "user"])
        self.assertIn("/home/demo/note.txt", wire[2]["content"])

    def test_search_tool_forgives_filename_lookup(self):
        with tempfile.TemporaryDirectory() as jail:
            os.makedirs(os.path.join(jail, "home", "demo"))
            target = os.path.join(jail, "home", "demo", "ge-bwr5.txt")
            with open(target, "w") as f:
                f.write("facts that do not contain their own filename")
            executor = ToolExecutor({"daemon": {"jail": jail}})
            result = executor.search("/", "ge-bwr5.txt")
        self.assertEqual(result,
                         "filename matches:\n/home/demo/ge-bwr5.txt")


if __name__ == "__main__":
    unittest.main()
