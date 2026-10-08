"""Deterministic terminal editor for the essential notepad app.

The model decides to launch the app and can perform semantic edits on request,
but it never owns the key-by-key event loop or framebuffer.
"""

import os
import shutil
import sys
import termios
import tty


BG = "\033[48;5;235m"
HEADER = "\033[1;37;48;5;24m"
STATUS = "\033[30;48;5;250m"
GUTTER = "\033[38;5;245;48;5;235m"
TEXT = "\033[38;5;252;48;5;235m"
RESET = "\033[0m"


class EditorBuffer:
    def __init__(self, text=""):
        self.lines = text.split("\n") or [""]
        self.row = 0
        self.col = 0
        self.dirty = False

    def clamp(self):
        self.row = max(0, min(self.row, len(self.lines) - 1))
        self.col = max(0, min(self.col, len(self.lines[self.row])))

    def insert(self, text):
        line = self.lines[self.row]
        self.lines[self.row] = line[:self.col] + text + line[self.col:]
        self.col += len(text)
        self.dirty = True

    def newline(self):
        line = self.lines[self.row]
        self.lines[self.row] = line[:self.col]
        self.lines.insert(self.row + 1, line[self.col:])
        self.row += 1
        self.col = 0
        self.dirty = True

    def backspace(self):
        if self.col:
            line = self.lines[self.row]
            self.lines[self.row] = line[:self.col - 1] + line[self.col:]
            self.col -= 1
            self.dirty = True
        elif self.row:
            previous = self.lines[self.row - 1]
            self.col = len(previous)
            self.lines[self.row - 1] = previous + self.lines.pop(self.row)
            self.row -= 1
            self.dirty = True

    def delete(self):
        line = self.lines[self.row]
        if self.col < len(line):
            self.lines[self.row] = line[:self.col] + line[self.col + 1:]
            self.dirty = True
        elif self.row < len(self.lines) - 1:
            self.lines[self.row] += self.lines.pop(self.row + 1)
            self.dirty = True

    def move(self, key, page=10):
        if key == "left":
            if self.col:
                self.col -= 1
            elif self.row:
                self.row -= 1
                self.col = len(self.lines[self.row])
        elif key == "right":
            if self.col < len(self.lines[self.row]):
                self.col += 1
            elif self.row < len(self.lines) - 1:
                self.row += 1
                self.col = 0
        elif key == "up":
            self.row -= 1
        elif key == "down":
            self.row += 1
        elif key == "home":
            self.col = 0
        elif key == "end":
            self.col = len(self.lines[self.row])
        elif key == "pageup":
            self.row -= page
        elif key == "pagedown":
            self.row += page
        self.clamp()

    def text(self):
        return "\n".join(self.lines)


def resolve_path(daemon, args):
    jail = os.path.realpath(daemon.jail)
    user = daemon.current_user or "demo"
    home = os.path.join(jail, "home", user)
    raw = str(args[0]).strip() if args else "~/Documents/notes.txt"
    if raw == "~":
        candidate = home
    elif raw.startswith("~/"):
        candidate = os.path.join(home, raw[2:])
    elif raw.startswith("/"):
        candidate = os.path.join(jail, raw.lstrip("/"))
    else:
        home_candidate = os.path.join(home, raw)
        docs_candidate = os.path.join(home, "Documents", raw)
        candidate = home_candidate if "/" in raw or os.path.exists(home_candidate) \
            else docs_candidate
    real = os.path.realpath(candidate)
    try:
        inside = os.path.commonpath((jail, real)) == jail
    except ValueError:
        inside = False
    if not inside:
        raise ValueError("file path escapes the as-os filesystem")
    if os.path.isdir(real):
        raise ValueError("notepad needs a file, not a directory")
    return real


def _fit(text, width):
    text = str(text).replace("\t", "    ").replace("\r", "")
    if len(text) > width:
        return text[:max(0, width - 1)] + ("…" if width else "")
    return text + " " * (width - len(text))


def _virtual_path(daemon, path):
    return "/" + os.path.relpath(path, daemon.jail).replace(os.sep, "/")


def run(shell, args):
    if not sys.stdin.isatty():
        return "notepad needs an interactive terminal"
    if isinstance(args, str):
        args = [args]
    path = resolve_path(shell.daemon, args)
    try:
        with open(path, "r", errors="replace") as f:
            initial = f.read(1024 * 1024 + 1)
    except FileNotFoundError:
        initial = ""
    if len(initial) > 1024 * 1024:
        return "notepad refuses files larger than 1 MiB"

    editor = EditorBuffer(initial)
    top = left = 0
    message = "Ready"
    command_mode = False
    command = ""
    quit_armed = saved_once = False
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)

    def save():
        nonlocal saved_once, message
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(editor.text())
        editor.dirty = False
        saved_once = True
        message = f"Saved {_virtual_path(shell.daemon, path)}"

    def render():
        nonlocal top, left
        size = shutil.get_terminal_size(fallback=(80, 24))
        width, height = max(30, size.columns), max(6, size.lines)
        body_h = height - 2
        gutter_w = max(4, len(str(len(editor.lines))) + 1)
        text_w = max(1, width - gutter_w)
        if editor.row < top:
            top = editor.row
        elif editor.row >= top + body_h:
            top = editor.row - body_h + 1
        if editor.col < left:
            left = editor.col
        elif editor.col >= left + text_w:
            left = editor.col - text_w + 1
        dirty = " *" if editor.dirty else ""
        title = f" notepad — {_virtual_path(shell.daemon, path)}{dirty} "
        out = ["\033[?25l", f"\033[1;1H{HEADER}{_fit(title, width)}{RESET}"]
        for screen_row in range(body_h):
            line_no = top + screen_row
            out.append(f"\033[{screen_row + 2};1H{BG}")
            if line_no < len(editor.lines):
                number = str(line_no + 1).rjust(gutter_w - 1) + " "
                visible = editor.lines[line_no].replace("\t", "    ")[left:left + text_w]
                out.append(f"{GUTTER}{number}{TEXT}{_fit(visible, text_w)}")
            else:
                out.append(f"{GUTTER}{_fit('~', gutter_w)}{TEXT}{' ' * text_w}")
            out.append(RESET)
        status = f" AI edit> {command}" if command_mode else \
            f" ^S Save  ^Q Quit  ^O AI edit | {message}"
        out.append(f"\033[{height};1H{STATUS}{_fit(status, width)}{RESET}")
        if command_mode:
            cursor_x, cursor_y = min(width, len(" AI edit> ") + len(command) + 1), height
        else:
            cursor_x = gutter_w + (editor.col - left) + 1
            cursor_y = (editor.row - top) + 2
        out.append(f"\033[{cursor_y};{cursor_x}H\033[?25h")
        shell._write("".join(out))

    shell._native_ui = True
    shell._in_alt = True
    shell._write("\033[?1049h\033[2J\033[H")
    try:
        tty.setraw(fd)
        while True:
            render()
            ev = shell._decode_key(fd) or {}
            kind, key = ev.get("event"), ev.get("key")
            if command_mode:
                if kind == "char":
                    command += ev.get("char", "")
                elif key == "backspace":
                    command = command[:-1]
                elif key == "escape":
                    command_mode, command, message = False, "", "AI edit cancelled"
                elif key == "enter":
                    request = command.strip()
                    command_mode, command = False, ""
                    if request:
                        if editor.dirty:
                            save()
                        message = "AI is editing…"
                        render()
                        virtual = _virtual_path(shell.daemon, path)
                        report = shell.daemon._handle_interpret(
                            f"Edit {virtual} according to this request: {request}. "
                            "Read that file, write the complete revised text back to "
                            "the same file, and do not change any other file.")
                        try:
                            with open(path, "r", errors="replace") as f:
                                editor = EditorBuffer(f.read(1024 * 1024))
                            message = str(report).replace("\n", " ")[:120]
                        except OSError as exc:
                            message = f"Could not reload file: {exc}"
                continue
            if kind == "char":
                editor.insert(ev.get("char", ""))
            elif key == "enter":
                editor.newline()
            elif key == "backspace":
                editor.backspace()
            elif key == "delete":
                editor.delete()
            elif key in ("left", "right", "up", "down", "home", "end", "pageup", "pagedown"):
                editor.move(key, page=max(1, shutil.get_terminal_size().lines - 3))
            elif key == "tab":
                editor.insert("    ")
            elif key == "ctrl+s":
                save()
            elif key == "ctrl+o":
                command_mode, command = True, ""
                message = "Describe the change, then press Enter"
            elif key in ("ctrl+q", "ctrl+c", "escape"):
                if editor.dirty and not quit_armed:
                    quit_armed = True
                    message = "Unsaved changes — press Ctrl-Q again to discard"
                    continue
                break
            if key not in ("ctrl+q", "ctrl+c", "escape"):
                quit_armed = False
    finally:
        try:
            termios.tcsetattr(fd, termios.TCSANOW, old)
        finally:
            shell._native_ui = False
            shell._leave_alt()
    state = "saved" if saved_once and not editor.dirty else "closed"
    return f"notepad {state} {_virtual_path(shell.daemon, path)}"
