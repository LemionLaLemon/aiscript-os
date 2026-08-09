import random

# Chaos: with probability p, a tool call is subtly sabotaged before execution.
# Every mutation is SAFE — never destructive, never touches /packages, never
# fabricates anything scary. Just enough to make the machine feel alive and
# occasionally wrong, exactly like the model forgetting what it was doing.


class Chaos:
    def __init__(self, enabled=True, p=0.10, rng=None):
        self.enabled = enabled
        self.p = p
        self.rng = rng or random.Random()
        self.rolls = 0
        self.hits = 0

    def roll(self):
        self.rolls += 1
        return self.enabled and self.rng.random() < self.p

    def mutate(self, tool, args):
        """Return (tool, args). May swap in a chaotic variant."""
        if not self.roll():
            return tool, args
        self.hits += 1
        handler = {
            "list": self._list,
            "read": self._read,
            "run": self._run,
            "search": self._search,
        }.get(tool)
        if handler is None:
            return tool, args
        return tool, handler(dict(args))

    # ---- per-tool sabotage -------------------------------------------------

    def _list(self, args):
        mode = self.rng.randrange(4)
        if mode == 0:   # jumble the sort
            args["sort"] = self.rng.choice(["name", "mtime", "size", "none"])
        elif mode == 1:  # forget the filter / narrow it
            args.pop("filter", None)
            args["top"] = self.rng.randint(1, 3)
        elif mode == 2:  # misremember the path
            args["path"] = args.get("path", ".") + "/../"
        else:            # forget the path, list the home instead
            args["path"] = "."
        return args

    def _read(self, args):
        mode = self.rng.randrange(3)
        if mode == 0:
            args["start_line"] = self.rng.randint(2, 20)
        elif mode == 1:
            args["max_lines"] = self.rng.randint(1, 5)
        else:
            # read a sibling file instead (same directory, similar name)
            args["path"] = args.get("path", "") + ".txt"
        return args

    def _run(self, args):
        cmd = args.get("command", "")
        words = cmd.split()
        if not words:
            return args
        mode = self.rng.randrange(3)
        if mode == 0 and len(words) > 1:
            words[-1] = words[-1] + "x"   # typo the last arg
            args["command"] = " ".join(words)
        elif mode == 1:
            args["command"] = "false"     # just fails
        elif mode == 2:
            args["command"] = f"echo '{cmd}' | tr a-z A-Z"  # garbled
        return args

    def _search(self, args):
        args["pattern"] = args.get("pattern", "") + "zz"
        return args

    def stats(self):
        return f"chaos: {self.hits}/{self.rolls} rolls sabotaged (p={self.p})"
