"""ComputerCraft-style virtual terminal for aiscript TUI apps.

Implements the term API surface from https://tweaked.cc/module/term.html
plus one ascOS addition (pull: wait for a keypress). The screen is a
buffer of (char, fg, bg) cells with a cursor and 16 CC palette colors.
Frames are serialized and streamed to the shell, which renders them.
"""
import json
import shutil

# CC palette index -> xterm-256 color.
_ANSI256 = [
    15,    # 0 white
    214,   # 1 orange
    201,   # 2 magenta
    153,   # 3 lightBlue
    226,   # 4 yellow
    46,    # 5 lime
    218,   # 6 pink
    244,   # 7 gray
    245,   # 8 lightGray
    51,    # 9 cyan
    129,   # 10 purple
    27,    # 11 blue
    130,   # 12 brown
    28,    # 13 green
    160,   # 14 red
    16,    # 15 black
]

_COLOR_NAMES = {
    "white": 0, "orange": 1, "magenta": 2, "lightblue": 3, "light_blue": 3,
    "yellow": 4, "lime": 5, "pink": 6, "gray": 7, "grey": 7,
    "lightgray": 8, "lightgrey": 8, "cyan": 9, "purple": 10, "blue": 11,
    "brown": 12, "green": 13, "red": 14, "black": 15,
}


def _color(v, default):
    """Coerce a color given as int / digit / hex char / name to 0-15."""
    if v is None or v == "":
        return default
    if isinstance(v, bool):
        return default
    if isinstance(v, (int, float)):
        return max(0, min(15, int(v)))
    s = str(v).strip().lower().lstrip("#")
    if s in _COLOR_NAMES:
        return _COLOR_NAMES[s]
    if len(s) == 1 and s in "0123456789abcdef":
        return int(s, 16)
    try:
        return max(0, min(15, int(s)))
    except ValueError:
        return default


class TermState:
    """The virtual screen: w x h cells, cursor (1-based, CC-style), colors."""

    ACTIONS = (
        "write", "blit", "render", "clear", "clear_line", "scroll",
        "set_cursor", "get_cursor", "set_fg", "set_bg", "get_fg", "get_bg",
        "get_size", "current", "save", "restore", "pull",
    )
    # actions that change the screen and should emit a frame
    MUTATING = {"write", "blit", "render", "clear", "clear_line", "scroll",
                "set_cursor", "set_fg", "set_bg", "restore"}

    def __init__(self, w=None, h=None):
        if not w or not h:
            size = shutil.get_terminal_size(fallback=(80, 24))
            w = w or size.columns
            h = h or size.lines
        self.w = max(20, min(int(w), 200))
        self.h = max(4, min(int(h), 80))
        self.x, self.y = 1, 1
        self.fg, self.bg = 0, 15          # CC default: white on black
        self._saved = None
        self._reset_lines()

    def _blank_line(self):
        return {"t": " " * self.w,
                "fg": "0" * self.w,
                "bg": "f" * self.w}

    def _reset_lines(self):
        self.lines = [self._blank_line() for _ in range(self.h)]

    # ---- primitives ---------------------------------------------------------

    def _scroll(self, n=1):
        n = max(1, int(n))
        for _ in range(n):
            self.lines.pop(0)
            self.lines.append(self._blank_line())
        self.y = min(self.y, self.h)

    def _advance(self, n=1):
        """Move cursor forward n cells with wrapping and scrolling."""
        for _ in range(n):
            self.x += 1
            if self.x > self.w:
                self.x = 1
                self.y += 1
                if self.y > self.h:
                    self._scroll(1)
                    self.y = self.h

    def _put(self, ch, fg, bg):
        ln = self.lines[self.y - 1]
        i = self.x - 1
        ln["t"] = ln["t"][:i] + ch + ln["t"][i + 1:]
        ln["fg"] = ln["fg"][:i] + fg + ln["fg"][i + 1:]
        ln["bg"] = ln["bg"][:i] + bg + ln["bg"][i + 1:]
        self._advance(1)

    def _newline(self):
        self.x = 1
        self.y += 1
        if self.y > self.h:
            self._scroll(1)
            self.y = self.h

    # ---- actions ---------------------------------------------------------------

    def do(self, action, args):
        """Run a term action. Returns the result string for the model."""
        a = str(action or "").lower().strip().replace("-", "_")
        args = args or {}
        if a not in self.ACTIONS:
            raise ValueError(f"unknown action {action!r}; one of {', '.join(self.ACTIONS)}")
        if a == "write":
            text = str(args.get("text") if args.get("text") is not None else "")
            self.fg = _color(args.get("fg"), self.fg)
            self.bg = _color(args.get("bg"), self.bg)
            fg, bg = "%x" % self.fg, "%x" % self.bg
            for ch in text:
                if ch == "\n":
                    self._newline()
                elif ch == "\t":
                    for _ in range(4):
                        self._put(" ", fg, bg)
                elif ch >= " ":
                    self._put(ch, fg, bg)
            return f"wrote {len(text)} chars at {self.x},{self.y}"
        if a == "blit":
            text = str(args.get("text") or "")
            fgs = str(args.get("fg") or "")
            bgs = str(args.get("bg") or "")
            fgs = (fgs + "%x" % self.fg * self.w)[:len(text)]
            bgs = (bgs + "%x" % self.bg * self.w)[:len(text)]
            for i, ch in enumerate(text):
                if ch == "\n":
                    self._newline()
                    continue
                if ch < " ":
                    continue
                if self.x > self.w:
                    self.x = 1
                    self.y += 1
                    if self.y > self.h:
                        self._scroll(1)
                        self.y = self.h
                self._put(ch,
                          "%x" % _color(fgs[i], self.fg),
                          "%x" % _color(bgs[i], self.bg))
            return f"blitted {len(text)} chars at {self.x},{self.y}"
        if a == "render":
            # Declarative whole-screen update. AI-interpreted apps should use
            # this instead of spending one model round per cursor/write call.
            rows = args.get("lines") or []
            if not isinstance(rows, list):
                raise ValueError("render lines must be an array of strings")
            self.fg = _color(args.get("fg"), self.fg)
            self.bg = _color(args.get("bg"), self.bg)
            fg, bg = "%x" % self.fg, "%x" % self.bg
            self.lines = []
            for i in range(self.h):
                text = str(rows[i]) if i < len(rows) else ""
                text = text[:self.w].ljust(self.w)
                self.lines.append({"t": text, "fg": fg * self.w,
                                   "bg": bg * self.w})
            self.x = max(1, min(self.w, int(args.get("x", 1))))
            self.y = max(1, min(self.h, int(args.get("y", 1))))
            return f"rendered {min(len(rows), self.h)} rows"
        if a == "clear":
            blank = self._blank_line()
            self.lines = [
                {"t": blank["t"],
                 "fg": "%x" % self.fg * self.w,
                 "bg": "%x" % self.bg * self.w}
                for _ in range(self.h)
            ]
            return "screen cleared"
        if a == "clear_line":
            ln = self._blank_line()
            ln["bg"] = "%x" % self.bg * self.w
            self.lines[self.y - 1] = ln
            return f"line {self.y} cleared"
        if a == "scroll":
            self._scroll(args.get("n", 1))
            return f"scrolled; cursor {self.x},{self.y}"
        if a == "set_cursor":
            self.x = max(1, min(self.w, int(args.get("x", 1))))
            self.y = max(1, min(self.h, int(args.get("y", 1))))
            return f"cursor at {self.x},{self.y}"
        if a == "get_cursor":
            return json.dumps({"x": self.x, "y": self.y})
        if a == "set_fg":
            self.fg = _color(args.get("fg", args.get("color")), self.fg)
            return f"foreground is now {self.fg}"
        if a == "set_bg":
            self.bg = _color(args.get("bg", args.get("color")), self.bg)
            return f"background is now {self.bg}"
        if a == "get_fg":
            return str(self.fg)
        if a == "get_bg":
            return str(self.bg)
        if a == "get_size":
            return json.dumps({"w": self.w, "h": self.h})
        if a == "current":
            ln = self.lines[self.y - 1]
            return json.dumps({"line": self.y, "t": ln["t"].rstrip(),
                               "fg": ln["fg"], "bg": ln["bg"]})
        if a == "save":
            self._saved = [dict(l) for l in self.lines]
            return "screen saved"
        if a == "restore":
            if self._saved is None:
                return "nothing saved yet"
            self.lines = [dict(l) for l in self._saved]
            return "screen restored"
        if a == "pull":
            # intercepted by Session._exec_term (needs the input handler);
            # reaching here means the session did not route it.
            raise ValueError("pull requires a terminal input handler")
        raise ValueError(f"unhandled action {action!r}")

    def serialize(self):
        return {
            "w": self.w, "h": self.h,
            "cursor": [self.x, self.y],
            "fg": self.fg, "bg": self.bg,
            "lines": self.lines,
        }
