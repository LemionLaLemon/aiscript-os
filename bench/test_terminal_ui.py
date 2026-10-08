import threading
import unittest
from unittest.mock import patch

from shell.as_shell import Shell
from shell.native_notepad import EditorBuffer


class TerminalUiTests(unittest.TestCase):
    def shell(self):
        shell = Shell.__new__(Shell)
        shell._out = threading.Lock()
        shell._in_alt = False
        shell._native_ui = False
        shell._turn_stop = None
        shell._tool_previews = set()
        shell._sub_at_line_start = {}
        shell.show_thinking = "on"
        shell.output = []
        shell._write = shell.output.append
        return shell

    def test_cumulative_tool_delta_is_one_preview(self):
        shell = self.shell()
        tag = ("app", "app:notepad.as")
        for args in ("{", '{"path"', '{"path":"/home/demo/note.txt"}'):
            shell._sub_event(tag, {
                "type": "tool-delta", "name": "read", "args": args,
                "index": 0,
            })
        shell._sub_event(tag, {
            "type": "tool", "name": "read",
            "args": {"path": "/home/demo/note.txt"}, "index": 0,
        })
        rendered = "".join(shell.output)
        self.assertEqual(rendered.count("read…"), 1)
        self.assertEqual(rendered.count("\n"), 1)
        self.assertNotIn("('app'", rendered)

    def test_term_frame_paints_without_default_background_erase(self):
        shell = self.shell()
        with patch("shell.as_shell.shutil.get_terminal_size") as size:
            size.return_value.columns = 20
            size.return_value.lines = 4
            shell._render_term({
                "lines": [{"t": "hello", "fg": "00000", "bg": "fffff"}],
                "cursor": [1, 1],
            })
        rendered = "".join(shell.output)
        self.assertNotIn("\033[J", rendered)
        self.assertNotIn("\033[K", rendered)
        self.assertEqual(rendered.count("\033[48;5;16m"), 4)

    def test_editor_buffer_handles_normal_editing(self):
        buf = EditorBuffer("one\ntwo")
        buf.move("end")
        buf.insert("!")
        buf.newline()
        buf.insert("three")
        buf.backspace()
        buf.delete()
        self.assertEqual(buf.text(), "one!\nthretwo")
        self.assertTrue(buf.dirty)


if __name__ == "__main__":
    unittest.main()
