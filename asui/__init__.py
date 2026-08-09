"""asui — tiny UI library that writes straight to the screen buffer.
Terminal backend for now; a framebuffer backend ships with the OS image."""

from .term import render_grid, clear_screen
from .fb import FbNotAvailable

try:
    from . import fb  # noqa: F401
except Exception:
    fb = None


class Screen:
    def __init__(self, width=80, height=24, backend="term"):
        self.width = width
        self.height = height
        self.backend = backend
        self.grid = [[" "] * width for _ in range(height)]

    # -- primitives ---------------------------------------------------------

    def set(self, x, y, ch):
        if 0 <= x < self.width and 0 <= y < self.height:
            self.grid[y][x] = ch

    def text(self, x, y, s):
        for i, c in enumerate(s):
            self.set(x + i, y, c)

    def rect(self, x, y, w, h):
        for i in range(w):
            self.set(x + i, y, "-")
            self.set(x + i, y + h - 1, "-")
        for j in range(h):
            self.set(x, y + j, "|")
            self.set(x + w - 1, y + j, "|")
        self.set(x, y, "+")
        self.set(x + w - 1, y, "+")
        self.set(x, y + h - 1, "+")
        self.set(x + w - 1, y + h - 1, "+")

    def fill(self, x, y, w, h, ch=" "):
        for j in range(h):
            for i in range(w):
                self.set(x + i, y + j, ch)

    def bar(self, x, y, w, frac):
        filled = max(0, min(w, int(w * max(0.0, min(1.0, frac)))))
        for i in range(w):
            self.set(x + i, y, "=" if i < filled else "-")

    def render(self):
        return render_grid(self.grid)

    def flip(self):
        print(self.render(), end="", flush=True)


def render_spec(spec, width=80, height=24):
    """Build a Screen from a declarative dict and return its rendered string.

    spec: {title, lines: [str], boxes: [{x,y,w,h}], bars: [{x,y,w,frac}],
           status: str}
    """
    s = Screen(width=width, height=height)
    title = spec.get("title") or ""
    status = spec.get("status") or ""
    s.rect(0, 0, min(width, len(title) + 4), min(height, 4))
    if title:
        s.text(2, 1, title)
    for box in spec.get("boxes") or []:
        s.rect(box.get("x", 0), box.get("y", 2), box.get("w", 20),
               box.get("h", 5))
    for bar in spec.get("bars") or []:
        s.bar(bar.get("x", 0), bar.get("y", 0), bar.get("w", 20),
              bar.get("frac", 0.5))
    for i, line in enumerate((spec.get("lines") or [])[: height - 6]):
        s.text(2, 3 + i, line[: width - 4])
    if status:
        s.rect(0, height - 3, width, 3)
        s.text(2, height - 2, status[: width - 4])
    return s.render()
